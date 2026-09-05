"""Request-bound, append-only receipts for evidence returned to a model."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from threading import Lock
from typing import Literal
from uuid import uuid4

from pex_protocol.supervisor import (
    MAX_EVIDENCE_OBSERVATION_BYTES,
    MAX_EVIDENCE_OBSERVATIONS,
    SupervisorEvidenceObservation,
    SupervisorRequest,
    supervisor_request_digest,
)

_OUTPUT_LIMIT = 8_000
_ARGUMENTS_LIMIT = 4_096
_LIMIT_REFUSAL = '{"error":"evidence_observation_limit_reached"}'


def _canonical_json(value: object, *, sort_keys: bool = False) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=sort_keys,
        separators=(",", ":"),
    )


def _bounded_preview_json(
    rendered: str,
    *,
    limit_bytes: int,
    prefix: dict[str, object] | None = None,
) -> str:
    """Return a JSON object whose final UTF-8 encoding fits the byte limit."""

    fixed = dict(prefix or {})
    fixed["truncated"] = True
    low = 0
    high = len(rendered)
    best = _canonical_json(fixed, sort_keys=True)
    while low <= high:
        middle = (low + high) // 2
        candidate = _canonical_json(
            {**fixed, "preview": rendered[:middle]},
            sort_keys=True,
        )
        if len(candidate.encode("utf-8")) <= limit_bytes:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return best


def canonical_arguments(value: dict[str, object]) -> str:
    """Render bounded tool arguments as a canonical JSON object."""

    rendered = _canonical_json(value, sort_keys=True)
    if len(rendered.encode("utf-8")) <= _ARGUMENTS_LIMIT:
        return rendered
    return _bounded_preview_json(rendered, limit_bytes=_ARGUMENTS_LIMIT)


class EvidenceObservationCollector:
    """Record only the exact sanitized bytes a request-scoped tool returns."""

    def __init__(
        self,
        request: SupervisorRequest,
        *,
        stage: Literal["main", "verifier"],
        invocation_id: str,
    ) -> None:
        self.stage = stage
        self.invocation_id = invocation_id
        self.request_digest = supervisor_request_digest(request)
        self.session_id = request.session.id
        self.goal_id = request.goal.id if request.goal else None
        self.event_id = request.event.event_id
        self.observations: list[SupervisorEvidenceObservation] = []
        self._used_bytes = 0
        self._lock = Lock()

    def record(
        self,
        *,
        tool_name: str,
        arguments_json: str,
        value: object,
    ) -> str:
        """Return a receipt-bearing output or a content-free budget refusal."""

        with self._lock:
            if len(self.observations) >= MAX_EVIDENCE_OBSERVATIONS:
                return _LIMIT_REFUSAL
            observation_id = f"pexobs_{uuid4().hex}"
            if isinstance(value, dict):
                envelope = {**value, "pex_observation_id": observation_id}
            else:
                envelope = {"pex_observation_id": observation_id, "result": value}
            output = _canonical_json(envelope)
            if len(output.encode("utf-8")) > _OUTPUT_LIMIT:
                output = _bounded_preview_json(
                    output,
                    limit_bytes=_OUTPUT_LIMIT,
                    prefix={"pex_observation_id": observation_id},
                )
            observation = SupervisorEvidenceObservation(
                observation_id=observation_id,
                invocation_id=self.invocation_id,
                stage=self.stage,
                request_digest=self.request_digest,
                session_id=self.session_id,
                goal_id=self.goal_id,
                event_id=self.event_id,
                observed_at=datetime.now(UTC),
                tool_name=tool_name,
                arguments_json=arguments_json,
                output=output,
                output_sha256=hashlib.sha256(output.encode("utf-8")).hexdigest(),
            )
            candidate_bytes = len(
                observation.model_dump_json().encode("utf-8")
            )
            if self._used_bytes + candidate_bytes > MAX_EVIDENCE_OBSERVATION_BYTES:
                return _LIMIT_REFUSAL
            self.observations.append(observation)
            self._used_bytes += candidate_bytes
            return output
