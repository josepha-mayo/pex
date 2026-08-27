"""Deterministic claim extraction. A STOP is not itself a completion claim."""

from __future__ import annotations

import re
from typing import Any

from pex_protocol.session import HarnessEvent

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_NEGATIVE = re.compile(
    r"\b(?:i )?(?:did not|didn't|do not|haven't|have not)\s+(?:run |verify |checked? )?(?P<what>.+)",
    re.IGNORECASE,
)
_KIND_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"\b(?:all )?tests pass(?:ed)?\b", re.I), "tests_pass", 0.9),
    (re.compile(r"\bevaluation (?:is )?(?:complete|done|finished)\b", re.I), "evaluation_complete", 0.85),
    (re.compile(r"\bdeployment (?:is )?(?:complete|done|live)\b", re.I), "deployment_complete", 0.85),
    (re.compile(r"\b(?:the )?(?:requested )?migration (?:is )?(?:complete|done)\b", re.I), "complete", 0.8),
    (re.compile(r"\bimplemented (?:the )?(?P<what>.+)", re.I), "implemented", 0.75),
    (re.compile(r"\b(?:i )?(?:updated|changed|fixed) (?:the )?(?P<what>.+)", re.I), "updated", 0.7),
    (re.compile(r"\bi(?:['’]m| am) done\b|\bwe(?:['’]re| are) done\b|\ball done\b", re.I), "complete", 0.55),
]


def _sentences(text: str) -> list[str]:
    parts = [part.strip(" \t\n\"'") for part in _SENTENCE_SPLIT.split(text.strip())]
    return [part for part in parts if len(part) > 3]


def extract_claims(events: list[HarnessEvent]) -> list[dict[str, Any]]:
    """Pull asserted/denied statements out of worker narration. Empty means unknown, not done."""
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for event in events:
        text = (event.message_delta or "").strip()
        if not text:
            continue
        for sentence in _sentences(text):
            negative = _NEGATIVE.search(sentence)
            if negative:
                what = (negative.group("what") or sentence).strip(" .")
                key = ("unverified", "denied", what.lower())
                if key in seen:
                    continue
                seen.add(key)
                found.append(
                    {
                        "statement": what,
                        "kind": "unverified",
                        "polarity": "denied",
                        "confidence": 0.8,
                        "source_event_id": event.event_id,
                    }
                )
                continue
            for pattern, kind, confidence in _KIND_PATTERNS:
                match = pattern.search(sentence)
                if not match:
                    continue
                statement = (match.groupdict().get("what") or sentence).strip(" .")
                key = (kind, "asserted", statement.lower())
                if key in seen:
                    continue
                seen.add(key)
                found.append(
                    {
                        "statement": statement,
                        "kind": kind,
                        "polarity": "asserted",
                        "confidence": confidence,
                        "source_event_id": event.event_id,
                    }
                )
    return found
