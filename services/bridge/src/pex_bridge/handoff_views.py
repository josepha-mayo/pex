from __future__ import annotations

import hashlib
import json
from typing import Any

from pex_protocol.actions import InterventionType
from pex_protocol.context import ContextBundle
from pex_protocol.intervention import Intervention


def _bundle_digest(bundle: ContextBundle) -> str:
    payload = json.dumps(
        bundle.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def handoff_bundle_receipt(intervention: Intervention) -> dict[str, Any] | None:
    """Return a content-free reference for one typed handoff payload."""

    if intervention.proposed_action.type != InterventionType.FRESH_HANDOFF:
        return None
    raw_bundle = intervention.proposed_action.payload.get("bundle")
    if not isinstance(raw_bundle, dict):
        return None
    bundle = ContextBundle.model_validate(raw_bundle)
    effect_id = intervention.metadata.get("operator_effect_id")
    return {
        "schema": "pex.handoff-bundle-receipt.v1",
        "operator_effect_id": effect_id if isinstance(effect_id, str) else None,
        "bundle_digest": _bundle_digest(bundle),
        "context_item_ids": [item.id for item in bundle.items],
        "item_count": len(bundle.items),
        "token_estimate": bundle.token_estimate,
        "detail_authority": (
            "operator_effects.payload_json.bundle" if isinstance(effect_id, str) else None
        ),
    }


def public_intervention(intervention: Intervention) -> dict[str, Any]:
    """Serialize an intervention without duplicating handoff context content."""

    payload = intervention.model_dump(mode="json")
    receipt = handoff_bundle_receipt(intervention)
    if receipt is not None:
        payload["proposed_action"]["payload"] = {"bundle_receipt": receipt}
    return payload


def intervention_audit_action_payload(intervention: Intervention) -> dict[str, Any]:
    """Keep exact handoff lineage in audit rows without repeating bundle text."""

    receipt = handoff_bundle_receipt(intervention)
    if receipt is None:
        return intervention.proposed_action.payload
    return {"bundle_receipt": receipt}
