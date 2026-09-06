"""Live selected-thread observations; history never becomes synthetic activity.

Worker effects remain disabled until the same-connection delivery/intent fence
is implemented. This adapter is a connection milestone, not the finished PEX loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime

from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import AdapterMessageResult, HarnessAdapter, bounded_observed_text
from pex_bridge.adapters.codex import CodexAdapter
from pex_bridge.adapters.codex_shared import (
    SharedCodexDeliveryUncertainError,
    SharedCodexTextAcknowledgement,
    SharedCodexTextDispatchRejected,
)
from pex_bridge.adapters.codex_subscription import (
    MAX_NOTIFICATIONS_PER_DRAIN,
    CodexExistingThreadSubscription,
    CodexObservationInterrupted,
    CodexObservedRecord,
    CodexSubscriptionError,
    shared_live_event_id,
)
from pex_bridge.codex_correction import (
    CORRECTION_SCHEMA,
    CodexCorrectionMultiplicityError,
    canonical,
)
from pex_bridge.codex_input_baseline import (
    BASELINE_SCHEMA,
    CodexInputBaseline,
    CodexInputBaselineSnapshot,
)
from pex_bridge.codex_input_provenance import CodexInputClassification, CodexInputProvenance
from pex_bridge.workspace_binding import WorkspaceAuthorityError

MAX_PENDING_EVENTS = 256
MAX_USER_ITEMS = 4096
DISCONNECT_INGEST_TIMEOUT_SECONDS = 2
RETENTION_INGEST_TIMEOUT_SECONDS = 10
# Reconciliation combines pre- and post-read live drains; ordinary streaming
# can additionally have one queue plus one in-flight event from a prior batch.
MAX_UNDELIVERED_EVENTS = max(
    2 * MAX_NOTIFICATIONS_PER_DRAIN, MAX_PENDING_EVENTS + MAX_NOTIFICATIONS_PER_DRAIN + 1
)


def _runtime_status(value: str, flags: tuple[str, ...] = ()) -> SessionStatus:
    if value == "active" and flags:
        if "waitingOnApproval" in flags:
            return SessionStatus.BLOCKED
        # A new vendor flag is not positive evidence of productive work.
        return SessionStatus.DISCOVERED
    return {
        "active": SessionStatus.WORKING,
        "idle": SessionStatus.IDLE,
        "systemError": SessionStatus.ERROR,
        "notLoaded": SessionStatus.DISCOVERED,
    }.get(value, SessionStatus.DISCOVERED)


class CodexSharedAdapter(HarnessAdapter):
    name = "codex"

    def __init__(self, subscription: CodexExistingThreadSubscription) -> None:
        state = subscription.state
        if state is None or not state.active:
            raise ValueError("shared Codex requires an authorized active subscription")
        selected = state.selected
        self._selected = selected
        if selected.pex_session_id != f"codex:{selected.thread_id}":
            raise ValueError("shared Codex session identity is not canonical")
        self.subscription = subscription
        self.transport = subscription.transport
        self._token = self.transport.connection_token()
        self._subscription_id = state.receipt.authorization_id
        self._normalizer = CodexAdapter()
        self._pump_task: asyncio.Task | None = None
        self.last_pump_error: str | None = None
        self.input_revision = 0
        self.ingress_sequence = 0
        self.last_ingested_sequence = 0
        self._ingesting = False
        self._ingesting_observation: tuple[HarnessEvent, HarnessSession] | None = None
        # Freeze an entire bounded batch before queue backpressure can yield.
        # This includes queued, enqueueing and in-flight events until ACKed.
        self._undelivered: dict[str, tuple[HarnessEvent, HarnessSession]] = {}
        self._retaining_observations: tuple[tuple[HarnessEvent, HarnessSession], ...] | None = None
        self._retaining_session: HarnessSession | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._retention_state = "not_attempted"
        self._retention_error: str | None = None
        self._retained_count = 0
        self._last_retained_sequence = 0
        self._received_interrupted_batch = None
        self._enqueueing = False
        self.active_turn_id: str | None = None
        self._user_items: set[tuple[str, str]] = set()
        self._correction_vendor_items: dict[str, tuple[str, str]] = {}
        self._input_provenance: CodexInputProvenance | None = None
        self._input_baseline: CodexInputBaseline | None = None
        self._input_baselines: dict[str, CodexInputBaselineSnapshot] = {}
        self._provenance_required = False
        self._input_bootstrap_complete = False
        self._correction_items: dict[str, str] = {}
        self._pending: asyncio.Queue[tuple[HarnessEvent, HarnessSession]] = asyncio.Queue(
            maxsize=MAX_PENDING_EVENTS
        )
        self._initial = state.reconciliation_records
        self._invalid = False
        self.session = HarnessSession(
            id=selected.pex_session_id,
            harness_type=HarnessType.CODEX,
            vendor_session_id=selected.thread_id,
            project_id=selected.project_id,
            cwd=selected.cwd,
            model=selected.model,
            status=_runtime_status(state.runtime_status, state.runtime_flags),
            last_activity=None,
            metadata={
                "existing_session": True,
                "connection_kind": "codex_shared",
                "subscription_receipt": asdict(state.receipt),
                "history_replayed_as_live": False,
                "delivery_proven": False,
                "observation_coverage": self._coverage("observing"),
            },
        )
        self.sessions = {self.session.id: self.session}
        self._normalizer.sessions[self.session.id] = self.session

    def _coverage(self, state: str, *, reason: str | None = None) -> dict:
        return {
            "schema": "pex.codex-observation-coverage.v1",
            "state": state,
            "scope": "selected_lifecycle_notifications",
            "raw_stream_complete": False,
            "history_replayed_as_live": False,
            "durable_before_ingest": False,
            "last_observed_live_sequence": self.ingress_sequence,
            "last_ingested_live_sequence": self.last_ingested_sequence,
            "pending_normalized_events": len(self._undelivered),
            "disconnect_retention_state": self._retention_state,
            "disconnect_retention_error": self._retention_error,
            "retained_after_disconnect_count": self._retained_count,
            "last_retained_live_sequence": self._last_retained_sequence,
            "unobserved_event_count": None,
            "reason": reason,
        }

    def _connected(self) -> bool:
        state = self.subscription.state
        return bool(
            not self._invalid
            and self.transport.initialized
            and self.transport.connection_token() == self._token
            and state is not None
            and state.active
        )

    async def probe(self) -> AdapterCapabilities:
        connected = self._connected()
        pumping = connected and self._pump_task is not None and not self._pump_task.done()
        return AdapterCapabilities(
            observe_messages=pumping,
            observe_tool_calls=False,
            observe_shell=pumping,
            observe_file_edits=pumping,
            observe_session_status=connected,
            support_label=(
                AdapterSupportLabel.OBSERVE_ONLY if connected else AdapterSupportLabel.UNAVAILABLE
            ),
            trust_level=0.7 if pumping else 0.4 if connected else 0,
            notes=(
                "Explicit existing-thread shared subscription. Live item/turn observations only; "
                "history is not replayed. Worker delivery, approvals and configuration changes "
                "are disabled pending current-intent/transport fencing. Observation is a "
                "lifecycle subset, not complete raw capture; disconnect/crash can lose "
                "buffered events."
                if connected
                else "Shared Codex observation lost; explicit reattachment required."
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if not self._connected():
            self.session.status = SessionStatus.DETACHED
        self.session.capabilities = (await self.probe()).model_dump(mode="json")
        # Discovery never invents a last-activity timestamp or reconnects a worker.
        return [self.session.model_copy(deep=True)]

    async def _dispatch_claimed_text(
        self,
        *,
        correction_json: str,
        attribution_records: tuple[str, ...],
        accepted_baseline: CodexInputBaselineSnapshot,
        final_authority_check: Callable[[], None],
    ) -> AdapterMessageResult:
        """Dispatch one Store-claimed correction without enabling generic control.

        Attribution is classification evidence only. The caller's mandatory
        synchronous callback remains the final Store/policy/control-grant
        authority, and the transport independently fences received wire state
        immediately before enqueue.
        """

        def refuse(message: str, cause: BaseException | None = None):
            error = SharedCodexTextDispatchRejected(message)
            if cause is None:
                raise error
            raise error from cause

        try:
            from pex_bridge.adapters.strict_json import strict_json_loads

            correction = strict_json_loads(correction_json)
            if (
                type(correction_json) is not str
                or type(correction) is not dict
                or canonical(correction) != correction_json
                or set(correction) != {
                    "schema", "event_id", "effect_id", "intervention_id",
                    "client_message_id", "content", "session_id", "thread_id",
                    "root_session_id", "vendor_project_id", "project_binding",
                    "workspace_binding", "subscription_receipt",
                }
                or correction.get("schema") != CORRECTION_SCHEMA
                or type(correction.get("content")) is not list
                or len(correction["content"]) != 1
                or type(correction["content"][0]) is not dict
                or set(correction["content"][0]) != {"type", "text", "text_elements"}
                or correction["content"][0].get("type") != "text"
                or correction["content"][0].get("text_elements") != []
            ):
                raise ValueError("correction is not the exact canonical Store shape")
            state = self.subscription.state
            receipt = asdict(state.receipt) if state is not None else None
            selected = self._selected
            if (
                not self._connected()
                or state is None
                or not state.active
                or receipt != self.session.metadata.get("subscription_receipt")
                or correction.get("subscription_receipt") != receipt
                or correction.get("session_id") != self.session.id
                or correction.get("thread_id") != self.session.vendor_session_id
                or correction.get("root_session_id") != selected.root_session_id
                or correction.get("vendor_project_id") != selected.vendor_project_id
                or receipt.get("authorization_id") != self._subscription_id
                or receipt.get("endpoint_identity") != self._token[0]
                or receipt.get("connection_generation") != self._token[1]
                or receipt.get("pex_session_id") != self.session.id
                or receipt.get("thread_id") != self.session.vendor_session_id
                or receipt.get("project_id") != self.session.project_id
                or receipt.get("cwd") != self.session.cwd
                or not callable(final_authority_check)
            ):
                raise ValueError("correction does not match the selected subscription")
            if (
                type(accepted_baseline) is not CodexInputBaselineSnapshot
                or accepted_baseline.schema != BASELINE_SCHEMA
                or accepted_baseline.complete is not True
                or type(accepted_baseline.digest) is not str
                or len(accepted_baseline.digest) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in accepted_baseline.digest
                )
                or accepted_baseline.pending_count != 0
                or accepted_baseline.reason is not None
            ):
                raise ValueError("accepted input baseline is incomplete")
            installed = CodexInputProvenance.from_store_records(
                attribution_records,
                session_id=self.session.id,
                thread_id=self.session.vendor_session_id,
            )
            attempted = False
            for record_json in attribution_records:
                record = strict_json_loads(record_json)
                if canonical(record.get("correction")) == correction_json:
                    attempted = True
                    break
            if not attempted:
                raise ValueError("current correction has no exact attempted attribution")
            baseline = self._input_baseline
            if (
                not self._input_bootstrap_complete
                or baseline is None
                or self._input_provenance is None
            ):
                raise ValueError("live input ledger is unavailable")

            # This publication boundary is deliberately synchronous: the
            # receiver cannot classify a new item against an older index in
            # between the adapter field and ledger replacement.
            baseline.replace_provenance(installed)
            installed = baseline._provenance
            self._input_provenance = installed
        except SharedCodexTextDispatchRejected:
            raise
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            refuse("claimed text dispatch binding was refused", exc)

        try:
            control = await self.subscription.refresh_control_snapshot()
            state = self.subscription.state
            current = baseline.snapshot()
            entries = strict_json_loads(control.user_inputs_json)
            external = installed.external_snapshot(entries)
            if (
                not self._connected()
                or state is None
                or not state.active
                or control.receipt != state.receipt
                or asdict(control.receipt) != receipt
                or control.read.connection_token != self._token
                or self._input_baseline is not baseline
                or self._input_provenance is not installed
                or baseline._provenance is not installed
                or current.complete is not True
                or current.pending_count != 0
                or current.reason is not None
                or external.complete is not True
                or control.user_inputs_digest
                != hashlib.sha256(control.user_inputs_json.encode("utf-8")).hexdigest()
                or current.digest != accepted_baseline.digest
                or external.digest != accepted_baseline.digest
            ):
                raise ValueError("fresh Codex input authority differs from acceptance")
        except asyncio.CancelledError:
            raise
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            refuse("claimed text dispatch fresh-read fence was refused", exc)
        except Exception as exc:
            refuse("claimed text dispatch control read was refused", exc)

        ledger_revision = current.revision
        ledger_digest = current.digest

        def final_check() -> None:
            checked = final_authority_check()
            if inspect.isawaitable(checked):
                if inspect.iscoroutine(checked):
                    checked.close()
                raise ValueError("claimed dispatch authority callback must be synchronous")
            if checked is not None:
                raise ValueError("claimed dispatch authority callback must return None")
            latest_state = self.subscription.state
            latest = baseline.snapshot()
            if (
                not self._connected()
                or latest_state is None
                or not latest_state.active
                or latest_state.receipt != control.receipt
                or asdict(latest_state.receipt) != receipt
                or self.transport.connection_token() != self._token
                or self._input_baseline is not baseline
                or self._input_provenance is not installed
                or baseline._provenance is not installed
                or latest.complete is not True
                or latest.pending_count != 0
                or latest.reason is not None
                or latest.revision != ledger_revision
                or latest.digest != ledger_digest
                or latest.digest != accepted_baseline.digest
            ):
                raise ValueError("claimed dispatch authority changed before enqueue")

        acknowledgement = await self.transport._dispatch_text(
            thread_id=self.session.vendor_session_id,
            text=correction["content"][0]["text"],
            client_user_message_id=correction["client_message_id"],
            expected_connection_token=self._token,
            expected_received_revision=control.read.received_envelope_revision,
            expected_received_chunk_revision=control.read.received_chunk_revision,
            expected_turn_id=control.active_turn_id,
            final_authority_check=final_check,
        )
        if (
            type(acknowledgement) is not SharedCodexTextAcknowledgement
            or acknowledgement.thread_id != self.session.vendor_session_id
            or acknowledgement.client_user_message_id != correction["client_message_id"]
            or acknowledgement.connection_token != self._token
            or acknowledgement.method
            != ("turn/steer" if control.active_turn_id is not None else "turn/start")
            or (
                control.active_turn_id is not None
                and acknowledgement.turn_id != control.active_turn_id
            )
        ):
            raise SharedCodexDeliveryUncertainError(
                "claimed text dispatch returned no exact turn acknowledgement"
            )
        return AdapterMessageResult(
            accepted=True,
            vendor_session_id=self.session.vendor_session_id,
            vendor_turn_id=acknowledgement.turn_id,
        )

    def _event(self, record: CodexObservedRecord) -> HarnessEvent | None:
        if record.source != "live_notification" or record.live_sequence is None:
            raise CodexSubscriptionError("history cannot enter the shared live event pump")
        envelope = record.payload()
        params = envelope["params"]
        self.ingress_sequence = record.live_sequence
        observed_at = datetime.now(UTC)
        method = record.method
        metadata = {
            "raw_method": method,
            "source": "codex_shared_live_notification",
            "observed_at": observed_at.isoformat(),
            "timestamp_kind": "pex_receipt_time",
            "connection_generation": self._token[1],
            "endpoint_identity": self._token[0],
            "subscription_id": self._subscription_id,
            "vendor_turn_id": record.turn_id or None,
            "ingress_sequence": record.live_sequence,
            "sequence_scope": "retained_lifecycle_records_not_raw_frames",
            "delivery_proven": False,
        }
        if record.item_id is not None:
            metadata["vendor_item_id"] = record.item_id
        event_type = EventType.STATUS
        phase = EventPhase.DURING
        error = None
        event = None
        correction_item_json = None
        if method.startswith("item/"):
            item = params["item"]
            if self._input_baseline is not None:
                self._input_baseline.observe_item(
                    turn_id=record.turn_id, item=item, completed=method == "item/completed",
                )
            is_user = item.get("type") == "userMessage"
            classification = (
                self._input_provenance.classify_item(
                    session_id=self.session.id, thread_id=self.session.vendor_session_id,
                    turn_id=record.turn_id, item=item, completed=method == "item/completed",
                )
                if is_user and self._input_provenance is not None else None
            )
            exact_correction = classification is not None and classification.kind == "exact_pex"
            if exact_correction:
                key = (record.turn_id, str(record.item_id))
                client_id = item["clientId"]
                previous = self._correction_vendor_items.get(client_id)
                if previous is not None and previous != key:
                    # One attempted correction cannot establish ownership of
                    # multiple vendor inputs. Match the history classifier's
                    # uncertainty rule; preserve evidence and revoke the fence.
                    classification = CodexInputClassification(
                        "uncertain", reason="duplicate correction correlation",
                    )
                    exact_correction = False
                else:
                    self._correction_vendor_items[client_id] = key
            if method == "item/started" and not is_user:
                return None
            if method == "item/started":
                # Revoke a future delivery fence immediately, but do not mistake
                # partial user content for the authoritative completed prompt.
                if classification is None or classification.kind != "uncertain":
                    self.input_revision += 1
                metadata["human_input_pending"] = True
            elif is_user:
                key = (record.turn_id, str(record.item_id))
                if key in self._user_items:
                    return None
                if len(self._user_items) >= MAX_USER_ITEMS:
                    raise CodexSubscriptionError("shared human input retention bound reached")
                self._user_items.add(key)
                if not exact_correction:
                    self.input_revision += 1
            if exact_correction:
                from pex_bridge.adapters.strict_json import strict_json_loads

                correction = strict_json_loads(classification.correction_json)
                correction_item_json = canonical(item)
                metadata["pex_correction_observation"] = {
                    "schema": "pex.codex-correction-observation.v1",
                    "effect_id": correction["effect_id"],
                    "client_message_id": correction["client_message_id"],
                    "vendor_item_id": item["id"],
                    "input_sha256": hashlib.sha256(
                        classification.entry_json.encode("utf-8")
                    ).hexdigest(),
                }
            elif method == "item/completed":
                event = self._normalizer.normalize_item(
                    self.session,
                    item,
                    event_suffix=record.stable_id,
                    vendor_turn_id=record.turn_id,
                )
                if event is not None and classification is not None and classification.kind in {
                    "uncertain", "incomplete",
                }:
                    # Keep visible evidence and stale-action fencing, but never
                    # let a conflicting correction ID mint human override intent.
                    event.metadata["content_status"] = "uncertain_input_provenance"
        elif method == "turn/started":
            self.active_turn_id = record.turn_id
            self.session.status = SessionStatus.WORKING
        elif method == "turn/completed":
            turn = params["turn"]
            status = turn.get("status")
            raw_error = turn.get("error")
            error = bounded_observed_text(
                raw_error.get("message") if isinstance(raw_error, dict) else raw_error,
                field="Codex turn error",
            )
            metadata["turn_status"] = status
            # Another turn may already have started before this terminal
            # notification arrives. Keep that newer turn's observation; even
            # a matching completion is not, by itself, a fresh idle grant.
            if self.active_turn_id == record.turn_id:
                self.active_turn_id = None
            event_type, phase = EventType.STOP, EventPhase.TERMINAL
            # A failed turn isn't a failed thread. Retain independently observed
            # thread runtime status rather than deriving it from the turn error.
            # Keep the preceding runtime observation. The coordinator may have
            # drained later status records already; using its final batch state
            # here would apply a future observation to this earlier event.
        elif method == "thread/status/changed":
            thread = params.get("thread") if isinstance(params.get("thread"), dict) else {}
            status = params.get("status", thread.get("status"))
            if not isinstance(status, dict):
                raise CodexSubscriptionError("shared runtime status is malformed")
            flags = status.get("activeFlags", [])
            if not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags):
                raise CodexSubscriptionError("shared runtime flags are malformed")
            self.session.status = _runtime_status(status.get("type", "unknown"), tuple(flags))
            metadata["runtime_status"] = dict(status)
        elif method != "thread/started":
            return None
        metadata["human_input_revision"] = self.input_revision
        shared_event_id = shared_live_event_id(
            subscription_id=self._subscription_id,
            endpoint_identity=self._token[0],
            connection_generation=self._token[1],
            stable_id=record.stable_id,
        )
        if event is None:
            event = HarnessEvent(
                event_id=shared_event_id,
                ts=observed_at,
                harness_type=HarnessType.CODEX,
                session_id=self.session.id,
                project_id=self.session.project_id,
                event_type=event_type,
                phase=phase,
                raw_event_ref=(
                    CodexAdapter._raw_event_ref(self.session, turn_id=record.turn_id)
                    if method == "turn/completed"
                    else None
                ),
                error=error,
            )
        else:
            event.ts = observed_at
        event.event_id = shared_event_id
        event.metadata = {**event.metadata, **metadata}
        if self._input_baseline is not None:
            self._input_baselines[event.event_id] = self._input_baseline.snapshot()
        if correction_item_json is not None:
            self._correction_items[event.event_id] = correction_item_json
        if method not in ("thread/status/changed", "thread/started"):
            self.session.last_activity = observed_at
        self.session.metadata["observation_coverage"] = self._coverage("observing")
        return event

    def _prepare_records(
        self, records: tuple[CodexObservedRecord, ...]
    ) -> tuple[tuple[HarnessEvent, HarnessSession], ...]:
        prepared = []
        for record in records:
            if len(self._undelivered) >= MAX_UNDELIVERED_EVENTS:
                raise CodexSubscriptionError("shared undelivered observation bound reached")
            event = self._event(record)
            if event is not None:
                observation = (event, self.session.model_copy(deep=True))
                self._undelivered[event.event_id] = observation
                prepared.append(observation)
        return tuple(prepared)

    async def _receive(self) -> None:
        records = self._initial
        self._initial = ()
        while True:
            prepared = self._prepare_records(records)
            if not self._connected():
                raise CodexSubscriptionError("shared Codex connection continuity lost")
            for observation in prepared:
                self._enqueueing = True
                await self._pending.put(observation)
                self._enqueueing = False
            try:
                batch = await self.subscription.drain_live()
            except CodexObservationInterrupted as exc:
                # Already invalidated: retain provenance, never re-enter the
                # live consumer or authorize semantic/worker effects.
                self._received_interrupted_batch = exc.batch
                self._prepare_records(exc.batch.records)
                raise
            records = batch.records
            if not records:
                await asyncio.sleep(0.025)

    async def _receive_with_provenance(self, loader) -> None:
        if loader is not None:
            records = await loader(self.session.model_copy(deep=True))
            if not self._connected():
                raise CodexSubscriptionError("connection lost during input provenance bootstrap")
            self._input_provenance = CodexInputProvenance.from_store_records(
                records, session_id=self.session.id, thread_id=self.session.vendor_session_id,
            )
            self._input_baseline = CodexInputBaseline.from_selected(
                self._selected, self._input_provenance,
            )
        self._input_bootstrap_complete = True
        await self._receive()

    async def _consume(self, ingest) -> None:
        while True:
            if not self._connected():
                raise CodexSubscriptionError("shared connection lost before event dequeue")
            event, session = await self._pending.get()
            self._ingesting = True
            self._ingesting_observation = (event, session)
            if not self._connected():
                raise CodexSubscriptionError("shared connection lost before event ingestion")
            while True:
                if not self._connected():
                    raise CodexSubscriptionError("shared connection lost during event ingestion")
                try:
                    # Keep the exact event and receipt time across a transient
                    # Store/pipeline failure; its durable acceptance is idempotent.
                    await ingest(event, session)
                    self.last_ingested_sequence = max(
                        self.last_ingested_sequence, event.metadata["ingress_sequence"]
                    )
                    self._undelivered.pop(event.event_id, None)
                    self._correction_items.pop(event.event_id, None)
                    self._input_baselines.pop(event.event_id, None)
                    self._ingesting = False
                    self._ingesting_observation = None
                    self.last_pump_error = None
                    break
                except asyncio.CancelledError:
                    raise
                except WorkspaceAuthorityError as exc:
                    # Authority loss is not transient Store unavailability.
                    # Let the owned pump finalizer retain the untouched pending
                    # observations after joining both consumers and producers.
                    self.last_pump_error = exc.code
                    raise
                except CodexCorrectionMultiplicityError:
                    # A fresh attachment may not have seen the first vendor
                    # item. Store's durable conflict cannot become valid by
                    # retrying; close and disclose the observation gap.
                    raise
                except Exception as exc:
                    self.last_pump_error = type(exc).__name__
                    await asyncio.sleep(0.1)

    async def _retain_pending(self, retention_ingest) -> None:
        if not self._undelivered:
            self._retention_state = "not_needed"
            return
        self._retention_state = "pending"
        self._retaining_observations = tuple(self._undelivered.values())
        self._retaining_session = self.session.model_copy(deep=True)

        async def attempt() -> None:
            if retention_ingest is None:
                raise ValueError("dedicated observer retention sink is unavailable")
            while True:
                try:
                    await retention_ingest(self._retaining_observations, self._retaining_session)
                    return
                except ValueError:
                    # Revoked identity or conflicting content cannot be retried
                    # into authority. Leave retained objects and disclose failure.
                    raise
                except Exception as exc:
                    self._retention_error = type(exc).__name__
                    await asyncio.sleep(0.05)

        try:
            await asyncio.wait_for(attempt(), timeout=RETENTION_INGEST_TIMEOUT_SECONDS)
        except Exception as exc:
            self._retention_state = "failed"
            self._retention_error = type(exc).__name__
            self.last_pump_error = f"observation_retention_{type(exc).__name__}"
        else:
            self._last_retained_sequence = max(
                event.metadata["ingress_sequence"] for event, _ in self._retaining_observations
            )
            self.last_ingested_sequence = max(
                self.last_ingested_sequence, self._last_retained_sequence
            )
            self._retained_count = len(self._retaining_observations)
            self._undelivered.clear()
            self._correction_items.clear()
            self._input_baselines.clear()
            while not self._pending.empty():
                self._pending.get_nowait()
            self._ingesting = False
            self._ingesting_observation = None
            self._enqueueing = False
            self._retention_state = "retained"
            self._retention_error = None
        finally:
            self._retaining_observations = None
            self._retaining_session = None

    async def pump_into_pipeline(
        self, ingest, *, lifecycle_ingest=None, retention_ingest=None, provenance_loader=None
    ) -> None:
        self._provenance_required = provenance_loader is not None
        # The owned receiver bootstrap preserves the no-await publication/bind
        # boundary and shares ordinary pump cancellation/cleanup ownership.
        receiver = asyncio.create_task(self._receive_with_provenance(provenance_loader))
        consumer = asyncio.create_task(self._consume(ingest))
        try:
            done, _ = await asyncio.wait((receiver, consumer), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_pump_error = type(exc).__name__
        finally:
            self._invalid = True
            for task in (receiver, consumer):
                task.cancel()
            self._cleanup_task = asyncio.create_task(
                self._finish_observation(receiver, consumer, lifecycle_ingest, retention_ingest)
            )
            cancelled = False
            while not self._cleanup_task.done():
                try:
                    await asyncio.shield(self._cleanup_task)
                except asyncio.CancelledError:
                    cancelled = True
            self._cleanup_task.result()
            if cancelled:
                raise asyncio.CancelledError

    async def _finish_observation(self, receiver, consumer, lifecycle_ingest, retention_ingest):
        await asyncio.gather(receiver, consumer, return_exceptions=True)
        # No pump can mutate the pending ledger after this join.
        interrupted = self.subscription.interrupted_batch
        if (
            interrupted is not None and interrupted is not self._received_interrupted_batch
            and not (self._provenance_required and not self._input_bootstrap_complete)
        ):
            self._received_interrupted_batch = interrupted
            try:
                self._prepare_records(interrupted.records)
            except Exception as exc:
                # Preserve any already-normalized prefix and disclose the gap.
                self.last_pump_error = f"observation_normalization_{type(exc).__name__}"
        await self.transport.close()
        self.session.status = SessionStatus.DETACHED
        self.session.capabilities = (await self.probe()).model_dump(mode="json")
        state = self.subscription.state
        reason = (
            (state.invalidation_reason if state is not None else None)
            or self.last_pump_error
            or "observation_stopped"
        )
        await self._retain_pending(retention_ingest)
        coverage = self._coverage("disconnected", reason=reason)
        self.session.metadata["observation_coverage"] = coverage
        # Separate local receipt, not a vendor STOP or worker-completion claim.
        disconnected = HarnessEvent(
            event_id=f"codex-shared-disconnected:{self._subscription_id}",
            ts=datetime.now(UTC),
            harness_type=HarnessType.CODEX,
            session_id=self.session.id,
            project_id=self.session.project_id,
            event_type=EventType.STATUS,
            metadata={
                "source": "pex_observer_lifecycle",
                "timestamp_kind": "pex_receipt_time",
                "subscription_id": self._subscription_id,
                "observation_coverage": coverage,
                "worker_stopped": False,
                "delivery_proven": False,
            },
        )
        try:
            if lifecycle_ingest is None:
                raise RuntimeError("dedicated observer lifecycle sink is unavailable")
            await asyncio.wait_for(
                lifecycle_ingest(disconnected, self.session.model_copy(deep=True)),
                timeout=DISCONNECT_INGEST_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            # Store unavailability cannot be reported as durable gap capture.
            self.last_pump_error = f"disconnect_receipt_{type(exc).__name__}"

    def start_pipeline_pump(
        self, ingest, *, lifecycle_ingest=None, retention_ingest=None, provenance_loader=None
    ) -> asyncio.Task:
        if self._pump_task is None:
            self._provenance_required = provenance_loader is not None
            self._pump_task = asyncio.create_task(
                self.pump_into_pipeline(
                    ingest, lifecycle_ingest=lifecycle_ingest, retention_ingest=retention_ingest,
                    provenance_loader=provenance_loader,
                ),
                name="codex-shared-pipeline-pump",
            )
        return self._pump_task
