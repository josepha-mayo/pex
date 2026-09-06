"""Bound oversized selected command observations without inventing test evidence."""

from __future__ import annotations

import hashlib
import re

from pex_bridge.adapters.base import (
    MAX_OBSERVED_VALUE_CHARS,
    bounded_adapter_id,
    bounded_observed_mapping,
)

OUTPUT_WITHHELD_KEY = "pex_output_unavailable"
OUTPUT_WITHHELD_SCHEMA = "pex.codex-command-output-withheld.v1"
OUTPUT_WITHHELD_NOTICE = (
    "Command output exceeded the observation limit; test evidence is unavailable."
)


def _exact_id(value: object) -> bool:
    try:
        return value == bounded_adapter_id(value, field="Codex command identity")
    except ValueError:
        return False


def bounded_shared_command_params(
    message: dict, *, thread_id: str, received_bytes_journaled: bool = False,
) -> dict | None:
    """Prepare one already-journaled, frame-bounded shared notification.

    Only a selected, idless command item may withhold its oversized output. The
    ordinary mapping bounds still apply to every other value. Raw receive bytes
    remain in the transport journal; no prefix or suffix is mistaken for a full
    test result. Reserved annotations are never accepted from the vendor.
    """

    params = message.get("params")
    if not isinstance(params, dict):
        return None
    item = params.get("item")
    if isinstance(item, dict) and any(
        not isinstance(key, str) or key.startswith("pex_output_") for key in item
    ):
        return None
    output = item.get("aggregatedOutput") if isinstance(item, dict) else None
    if not isinstance(output, str) or len(output) <= MAX_OBSERVED_VALUE_CHARS:
        return bounded_observed_mapping(params)
    if (
        not received_bytes_journaled
        or set(message) not in ({"method", "params"}, {"jsonrpc", "method", "params"})
        or ("jsonrpc" in message and message["jsonrpc"] != "2.0")
        or message.get("method") not in ("item/started", "item/completed")
        or params.get("threadId") != thread_id
        or not _exact_id(params.get("threadId"))
        or not _exact_id(params.get("turnId"))
        or not _exact_id(item.get("id"))
        or item.get("type") != "commandExecution"
        or "\x00" in output
    ):
        return None
    if "itemId" in params and params["itemId"] != item["id"]:
        return None
    if "itemId" in item and item["itemId"] != item["id"]:
        return None
    # Alternate/nested turn identities are unnecessary for the documented item
    # shape. Reject rather than normalize an ambiguous parent into authority.
    if "turn" in params:
        return None
    if "turnId" in item and item["turnId"] != params["turnId"]:
        return None
    if "threadId" in item and item["threadId"] != thread_id:
        return None
    if not isinstance(item.get("status"), str) or item["status"] not in {
        "inProgress", "completed", "failed", "declined",
    }:
        return None
    try:
        output_digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
    except UnicodeEncodeError:
        return None
    prepared_item = {
        **item,
        "aggregatedOutput": OUTPUT_WITHHELD_NOTICE,
        OUTPUT_WITHHELD_KEY: {
            "schema": OUTPUT_WITHHELD_SCHEMA,
            "characters": len(output),
            "sha256": output_digest,
        },
    }
    return bounded_observed_mapping({**params, "item": prepared_item})


def command_output_is_withheld(item: dict) -> bool:
    """Validate the ingress annotation; malformed annotations never allow evidence."""

    if OUTPUT_WITHHELD_KEY not in item:
        return False
    marker = item[OUTPUT_WITHHELD_KEY]
    if (
        not isinstance(marker, dict)
        or set(marker) != {"schema", "characters", "sha256"}
        or marker.get("schema") != OUTPUT_WITHHELD_SCHEMA
        or type(marker.get("characters")) is not int
        or marker["characters"] <= MAX_OBSERVED_VALUE_CHARS
        or not isinstance(marker.get("sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", marker["sha256"]) is None
        or item.get("aggregatedOutput") != OUTPUT_WITHHELD_NOTICE
    ):
        raise ValueError("Codex command output annotation is malformed")
    return True
