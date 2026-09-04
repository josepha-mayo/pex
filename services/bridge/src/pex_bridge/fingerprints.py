"""Evidence-backed AgentFingerprint projection for the command deck.

Build spec §9.7 lists strengths, failure modes, rates, and overlays.
Those fields are populated only from persisted STOP verification and overlay
rows. Unmeasured spec fields stay null instead of invented personality.
"""

from __future__ import annotations

import re
from typing import Any

_EVIDENCE_BEFORE_DONE = "evidence-before-done"
_MIN_PREMATURE_SESSIONS_FOR_RECOMMENDATION = 2
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STORE_COHORT_AUTHORITY = object()


def seal_store_fingerprint_cohort(bucket: dict[str, Any]) -> dict[str, Any]:
    """Mark a validated Store result without serializable/copyable authority."""

    return {**bucket, "_store_cohort_authority": _STORE_COHORT_AUTHORITY}


def _count(bucket: dict[str, Any], key: str) -> int:
    value = bucket.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _is_authoritative_cohort(bucket: dict[str, Any]) -> bool:
    """Require complete Store-owned provenance before influencing a score."""

    model = bucket.get("model")
    settings_hash = bucket.get("model_settings_hash")
    models = bucket.get("models")
    if (
        bucket.get("_store_cohort_authority") is not _STORE_COHORT_AUTHORITY
        or bucket.get("cohort_scoped") is not True
        or bucket.get("cohort_history_immutable") is not True
        or bucket.get("settings_identity_verified") is not True
        or bucket.get("project_binding_typed") is not True
        or not isinstance(model, str)
        or not model
        or not isinstance(settings_hash, str)
        or _SHA256.fullmatch(settings_hash) is None
        or models != [model]
    ):
        return False
    observed = bucket.get("observed_sessions")
    premature = bucket.get("premature_stop_sessions")
    verified = bucket.get("verified_stop_sessions")
    overlays = bucket.get("overlay_sessions")
    inspected = bucket.get("inspected_stop_sessions")
    counts = (observed, premature, verified, overlays, inspected)
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts):
        return False
    return bool(
        observed >= inspected
        and observed >= overlays
        and inspected >= premature
        and inspected >= verified
    )


def decorate_agent_fingerprint(bucket: dict[str, Any]) -> dict[str, Any]:
    observed = _count(bucket, "observed_sessions")
    premature = _count(bucket, "premature_stop_sessions")
    verified = _count(bucket, "verified_stop_sessions")
    overlays = _count(bucket, "overlay_sessions")
    inspected = _count(bucket, "inspected_stop_sessions")
    if inspected <= 0:
        inspected = verified + premature

    strengths: list[str] = []
    if verified:
        noun = "STOP" if verified == 1 else "STOPs"
        strengths.append(f"{verified} inspected {noun} supported by the verifier")

    failure_modes: list[str] = []
    if premature:
        noun = "STOP" if premature == 1 else "STOPs"
        failure_modes.append(f"{premature} inspected {noun} contradicted or left an acceptance gap")

    recommended = (
        [_EVIDENCE_BEFORE_DONE]
        if _is_authoritative_cohort(bucket)
        and premature >= _MIN_PREMATURE_SESSIONS_FOR_RECOMMENDATION
        else []
    )

    return {
        "harness": bucket["harness"],
        "model": bucket.get("model"),
        "observed_sessions": observed,
        "models": list(bucket.get("models") or []),
        "premature_stop_sessions": premature,
        "verified_stop_sessions": verified,
        "overlay_sessions": overlays,
        "inspected_stop_sessions": inspected,
        "premature_stop_rate": (premature / observed) if observed else 0.0,
        "verified_success_rate": (verified / inspected) if inspected else 0.0,
        "strengths": strengths,
        "failure_modes": failure_modes,
        "recommended_overlays": recommended,
        "token_efficiency": None,
        "repeated_tool_rate": None,
        "context_degradation_profile": None,
        "approval_behavior": None,
        "model_settings_hash": bucket.get("model_settings_hash"),
        "project_class": bucket.get("project_class"),
        "sample_count": inspected,
        "confidence": min(1.0, inspected / 5.0),
        "cohort_scoped": bucket.get("cohort_scoped") is True,
    }


def fingerprint_score_features(bucket: dict[str, Any]) -> dict[str, Any]:
    if not _is_authoritative_cohort(bucket):
        return {
            "recommended_overlays": [],
            "gap_stop_sessions": 0,
            "inspected_stop_sessions": 0,
            "verified_stop_sessions": 0,
            "fingerprint_model": None,
            "fingerprint_model_settings_hash": None,
            "fingerprint_project_class": None,
            "fingerprint_sample_count": 0,
            "fingerprint_confidence": 0.0,
        }
    pretty = decorate_agent_fingerprint(bucket)
    return {
        "recommended_overlays": pretty["recommended_overlays"],
        "gap_stop_sessions": pretty["premature_stop_sessions"],
        "inspected_stop_sessions": pretty["inspected_stop_sessions"],
        "verified_stop_sessions": pretty["verified_stop_sessions"],
        "fingerprint_model": pretty["model"],
        "fingerprint_model_settings_hash": pretty["model_settings_hash"],
        "fingerprint_project_class": pretty["project_class"],
        "fingerprint_sample_count": pretty["sample_count"],
        "fingerprint_confidence": pretty["confidence"],
    }


def decorate_agent_fingerprints(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [decorate_agent_fingerprint(row) for row in rows]
