"""Verify a PEX evidence pack offline — no bridge, no trust required.

    uv run python scripts/verify_pack.py pex-evidence-pack.json

Recomputes every digest the pack asserts:

* sealed baseline contents hash to the recorded SHA-256 digests,
* the flagged bytes hash to the recorded incident digests — and for a
  `modified` flag, that digest must differ from the sealed baseline digest
  (proof the flagged file really is not the sealed file),
* each session's event ledger re-chains to the recorded head digest,
* the manifest digest covers the entire pack.

A PASS proves the evidence bundle is internally consistent — these verdicts
rest on exactly these bytes and events. It does not prove a live worker ran;
that claim still rests on the live-run receipts and recordings.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def verify(pack: dict) -> list[str]:
    """Return a list of check lines, each prefixed PASS or FAIL."""
    checks: list[str] = []

    def check(ok: bool, label: str) -> None:
        checks.append(("PASS" if ok else "FAIL") + " " + label)

    check(pack.get("schema") == "pex.evidence-pack.v1", "schema is pex.evidence-pack.v1")

    manifest = pack.get("manifest_sha256")
    if isinstance(manifest, str):
        recomputed = _sha256_text(
            _canonical({k: v for k, v in pack.items() if k != "manifest_sha256"})
        )
        check(manifest == recomputed, f"manifest digest recomputes ({manifest[:16]}..)")
    else:
        check(False, "manifest_sha256 present")

    report = pack.get("report") or {}
    check(
        report.get("schema") == "pex.verification-report.v1",
        "embedded verification report present",
    )
    goal_id = pack.get("goal_id")
    check(
        (report.get("goal") or {}).get("id") == goal_id,
        "report goal matches pack goal",
    )

    # Baselines: sealed digests must match the bundled sealed bytes.
    baseline_by_session: dict[str, dict] = {}
    for baseline in pack.get("acceptance_baselines") or []:
        sid = baseline.get("session_id") or ""
        baseline_by_session[sid] = baseline
        files = baseline.get("files") or {}
        contents = baseline.get("contents") or {}
        matched = 0
        for path, digest in sorted(files.items()):
            if not isinstance(digest, str):
                continue
            text = contents.get(path)
            if text is None:
                checks.append(f"NOTE {sid} {path}: digest sealed, no content bundled")
                continue
            ok = _sha256_text(text) == digest
            matched += ok
            check(ok, f"baseline {sid[:24]}.. {path}: content matches sealed digest")
        check(bool(files), f"baseline {sid[:24]}.. carries file digests ({len(files)})")
        if matched:
            checks.append(f"INFO {sid[:24]}.. {matched} sealed file(s) verified")

    # Flagged bytes: content must hash to the recorded incident digest, and a
    # `modified` flag must point at bytes that differ from the sealed digest.
    for entry in pack.get("flagged") or []:
        sid = entry.get("session_id") or ""
        iid = str(entry.get("intervention_id") or "")[:16]
        contents = entry.get("contents") or {}
        digests = entry.get("flagged_sha256") or {}
        surface = entry.get("acceptance_surface") or {}
        modified = set(surface.get("modified") or [])
        baseline = baseline_by_session.get(sid) or {}
        sealed = baseline.get("files") or {}
        for path, text in sorted(contents.items()):
            digest = digests.get(path)
            check(
                isinstance(digest, str) and _sha256_text(text) == digest,
                f"flagged {iid}.. {path}: bundled bytes match incident digest",
            )
            if path in modified and isinstance(sealed.get(path), str):
                check(
                    digests.get(path) != sealed[path],
                    f"flagged {iid}.. {path}: digest differs from sealed baseline",
                )
            if path in modified and sealed.get(path) is None:
                checks.append(
                    f"NOTE {iid}.. {path}: flagged modified but no sealed digest to compare"
                )

    # Event ledgers: every event re-hashes and the chain reaches the head.
    for ledger in pack.get("event_ledger") or []:
        sid = ledger.get("session_id") or ""
        chain = ""
        count = 0
        for entry in ledger.get("events") or []:
            event_sha = _sha256_text(_canonical(entry.get("event")))
            check(
                event_sha == entry.get("sha256"),
                f"ledger {sid[:24]}.. event {count}: payload hash matches",
            )
            chain = _sha256_text(f"{chain}|{event_sha}")
            count += 1
        check(count == ledger.get("count"), f"ledger {sid[:24]}.. event count consistent")
        check(
            chain == ledger.get("chain_sha256"),
            f"ledger {sid[:24]}.. hash chain reaches recorded head",
        )
        if ledger.get("truncated"):
            checks.append(f"NOTE {sid[:24]}.. ledger truncated at the export cap")

    claims = report.get("claims") or []
    check(len(claims) == (report.get("summary") or {}).get("claims"), "claim count consistent")
    return checks


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.splitlines()[0], file=sys.stderr)
        print("usage: verify_pack.py <pack.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read pack: {exc}", file=sys.stderr)
        return 2
    if not isinstance(pack, dict):
        print("pack is not a JSON object", file=sys.stderr)
        return 2

    checks = verify(pack)
    width = max(len(line.split(" ", 1)[0]) for line in checks) if checks else 4
    failures = 0
    for line in checks:
        tag, _, rest = line.partition(" ")
        failures += tag == "FAIL"
        print(f"{tag:<{width}} {rest}")
    print("-" * 72)
    print(
        f"{sum(1 for c in checks if c.startswith('PASS'))}/{len(checks)} checks passed; "
        f"{failures} failed — internal-consistency proof only, not proof of a live run."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
