"""Verify a PEX evidence pack offline -- no bridge, no trust required.

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

import difflib
import hashlib
import html
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

    # Intervention records: the supervision arc rides in the bundle. Their ids
    # must be unique; integrity-flagged paths must reference a flagged entry.
    interventions = pack.get("interventions") or []
    ids = [item.get("id") for item in interventions if isinstance(item, dict)]
    check(
        len(ids) == len(set(ids)),
        f"intervention ids unique ({len(ids)} records)",
    )
    flagged_ids = {
        str(entry.get("intervention_id"))
        for entry in pack.get("flagged") or []
    }
    check(
        flagged_ids.issubset(set(ids)),
        "every flagged incident references a bundled intervention",
    )
    return checks


_CSS = """
:root{color-scheme:dark;--bg:#0c0f0e;--panel:#131716;--line:#243029;
--ink:#d7e2dc;--dim:#7d8f87;--mint:#5adfa8;--red:#ff7a72;--amber:#e8c46a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 ui-monospace,
Cascadia Mono,Consolas,monospace;padding:32px 20px 64px}
main{max-width:960px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px;letter-spacing:.02em}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.14em;color:var(--dim);
margin:36px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
.sub{color:var(--dim);font-size:12px}
.mono{word-break:break-all}
.badge{display:inline-block;padding:2px 10px;border-radius:3px;font-weight:600;
font-size:12px;letter-spacing:.08em;margin:12px 8px 0 0}
.badge.ok{background:#123326;color:var(--mint);border:1px solid #1f5b3e}
.badge.bad{background:#3a1512;color:var(--red);border:1px solid #66241f}
.badge.info{background:#1a2a33;color:#8fc9e8;border:1px solid #274b5c}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;
padding:14px 16px;margin:10px 0}
.kv{display:grid;grid-template-columns:150px 1fr;gap:4px 14px;font-size:13px}
.kv dt{color:var(--dim)}.kv dd{margin:0;word-break:break-all}
table{width:100%;border-collapse:collapse;font-size:12.5px}
td,th{padding:4px 10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:500;text-transform:uppercase;font-size:11px;letter-spacing:.1em}
.c-pass{color:var(--mint)}.c-fail{color:var(--red);font-weight:600}
.c-info,.c-note{color:var(--dim)}
pre.diff{margin:8px 0 0;padding:10px 12px;background:#0a0d0c;border:1px solid var(--line);
border-radius:5px;overflow-x:auto;font-size:12.5px;line-height:1.5}
.d-add{color:var(--mint)}.d-del{color:var(--red)}.d-hdr{color:var(--amber)}.d-ctx{color:var(--dim)}
footer{margin-top:44px;color:var(--dim);font-size:12px;border-top:1px solid var(--line);
padding-top:14px}
code.cmd{color:var(--mint);background:#0a0d0c;padding:1px 6px;border-radius:3px}
"""


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _diff_html(old: str, new: str, path: str) -> str:
    lines = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile=f"sealed/{path}",
        tofile=f"flagged/{path}",
        lineterm="",
    )
    out = []
    for line in lines:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            cls = "d-hdr"
        elif line.startswith("+"):
            cls = "d-add"
        elif line.startswith("-"):
            cls = "d-del"
        else:
            cls = "d-ctx"
        out.append(f'<span class="{cls}">{_esc(line)}</span>')
    return "\n".join(out)


def render_html(pack: dict, checks: list[str]) -> str:
    """Render a self-contained forensic page for a verified pack."""
    report = pack.get("report") or {}
    summary = report.get("summary") or {}
    completion = report.get("completion") or {}
    failures = sum(1 for c in checks if c.startswith("FAIL"))
    passed = sum(1 for c in checks if c.startswith("PASS"))

    parts = [
        "<!doctype html><html><head><meta charset=utf-8>",
        "<title>PEX evidence pack</title>",
        f"<style>{_CSS}</style></head><body><main>",
        "<h1>PEX evidence pack &mdash; forensic receipt</h1>",
        f'<div class="sub">schema {_esc(pack.get("schema"))} &middot; generated '
        f"{_esc(pack.get('generated_at'))} &middot; manifest "
        f'<span class="mono">{_esc(str(pack.get("manifest_sha256") or "")[:24])}..</span></div>',
    ]
    badge_cls = "ok" if not failures else "bad"
    badge_text = (
        f"{passed}/{len(checks)} CHECKS PASSED" if not failures else f"{failures} CHECKS FAILED"
    )
    parts.append(f'<span class="badge {badge_cls}">{badge_text}</span>')
    status = completion.get("status") or "unknown"
    parts.append(f'<span class="badge info">completion: {_esc(status)}</span>')
    note = pack.get("consistency_note")
    if note:
        parts.append(f'<div class="sub" style="margin-top:10px">{_esc(note)}</div>')

    parts.append("<h2>Verdict summary</h2><div class=panel><dl class=kv>")
    parts.append(f"<dt>goal</dt><dd class=mono>{_esc(pack.get('goal_id'))}</dd>")
    goal = report.get("goal") or {}
    if goal.get("statement"):
        parts.append(f"<dt>statement</dt><dd>{_esc(goal['statement'])}</dd>")
    verdicts = summary.get("verdicts") or {}
    verdict_text = ", ".join(f"{k}: {v}" for k, v in sorted(verdicts.items()))
    parts.append(
        f"<dt>claims adjudicated</dt><dd>{_esc(summary.get('claims', 0))} "
        f"({_esc(verdict_text)})</dd>"
    )
    parts.append(
        f"<dt>integrity incidents</dt><dd>{_esc(summary.get('integrity_incidents', 0))}</dd>"
    )
    parts.append(
        f"<dt>corrective nudges</dt><dd>{_esc(summary.get('corrective_nudges', 0))}</dd></dl></div>"
    )

    parts.append("<h2>Verification checks</h2><div class=panel><table>")
    for line in checks:
        tag, _, rest = line.partition(" ")
        parts.append(f'<tr><td class="c-{tag.lower()}">{_esc(tag)}</td><td>{_esc(rest)}</td></tr>')
    parts.append("</table></div>")

    baseline_by_session = {
        (b.get("session_id") or ""): b for b in pack.get("acceptance_baselines") or []
    }
    if baseline_by_session:
        parts.append("<h2>Sealed acceptance baselines</h2>")
        for sid, baseline in baseline_by_session.items():
            sealed_at = _esc(baseline.get("sealed_at"))
            sealed_via = _esc(baseline.get("sealed_context"))
            parts.append(
                f"<div class=panel><div class=sub>{_esc(sid)} &middot; sealed "
                f"{sealed_at} via {sealed_via}</div>"
                "<table><tr><th>path</th><th>sha-256</th></tr>"
            )
            for path, digest in sorted((baseline.get("files") or {}).items()):
                parts.append(
                    f"<tr><td>{_esc(path)}</td><td class=mono>{_esc(str(digest)[:24])}..</td></tr>"
                )
            parts.append("</table></div>")

    flagged = pack.get("flagged") or []
    if flagged:
        parts.append("<h2>Flagged acceptance-surface bytes</h2>")
        for entry in flagged:
            sid = entry.get("session_id") or ""
            baseline = baseline_by_session.get(sid) or {}
            sealed_contents = baseline.get("contents") or {}
            parts.append(
                f"<div class=panel><div class=sub>{_esc(sid)} &middot; incident "
                f"{_esc(str(entry.get('intervention_id') or '')[:24])}.. &middot; "
                f"{_esc(entry.get('at'))}</div>"
            )
            for path in entry.get("flagged_paths") or []:
                new_text = (entry.get("contents") or {}).get(path) or ""
                old_text = sealed_contents.get(path)
                digest = (entry.get("flagged_sha256") or {}).get(path)
                parts.append(
                    f"<div><b>{_esc(path)}</b> &middot; flagged sha-256 "
                    f"<span class=mono>{_esc(str(digest)[:24])}..</span></div>"
                )
                parts.append(f"<pre class=diff>{_diff_html(old_text or '', new_text, path)}</pre>")
            parts.append("</div>")

    interventions = pack.get("interventions") or []
    if interventions:
        parts.append("<h2>Supervision arc</h2>")
        parts.append(
            "<div class=panel><table><tr><th>at</th><th>action</th>"
            "<th>policy</th><th>outcome</th><th>evidence</th></tr>"
        )
        for item in interventions:
            if not isinstance(item, dict):
                continue
            evidence = item.get("evidence") or []
            first_evidence = str(evidence[0])[:80] if evidence else ""
            parts.append(
                f"<tr><td>{_esc(str(item.get('created_at') or '')[:19])}</td>"
                f"<td>{_esc(item.get('action_taken'))}</td>"
                f"<td>{_esc(item.get('policy_verdict'))}</td>"
                f"<td>{_esc(item.get('result'))}</td>"
                f"<td class=mono>{_esc(first_evidence)}</td></tr>"
            )
        parts.append("</table></div>")

    ledgers = pack.get("event_ledger") or []
    if ledgers:
        parts.append("<h2>Hash-chained event ledger</h2>")
        for ledger in ledgers:
            parts.append(
                f"<div class=panel><div class=sub>{_esc(ledger.get('session_id'))} &middot; "
                f"{_esc(ledger.get('count'))} events &middot; head "
                f"<span class=mono>{_esc(str(ledger.get('chain_sha256') or '')[:24])}..</span>"
                + (" &middot; TRUNCATED" if ledger.get("truncated") else "")
                + "</div><table><tr><th>#</th><th>type</th><th>payload sha-256</th></tr>"
            )
            for i, entry in enumerate(ledger.get("events") or []):
                event = entry.get("event") or {}
                etype = event.get("event_type") or event.get("type") or "?"
                parts.append(
                    f"<tr><td>{i}</td><td>{_esc(etype)}</td>"
                    f"<td class=mono>{_esc(str(entry.get('sha256') or '')[:24])}..</td></tr>"
                )
            parts.append("</table></div>")

    # The raw pack rides inside the page so the report *is* the evidence —
    # verify_pack.py accepts this HTML file as input and re-checks the
    # embedded JSON. '<' is escaped so the JSON cannot close the tag early.
    raw_json = json.dumps(pack, ensure_ascii=False, indent=2).replace("<", "\\u003c")
    parts.append(
        "<h2>Raw pack</h2><details><summary class=sub>embedded "
        "pex.evidence-pack.v1 JSON</summary>"
        f'<pre class=diff id="raw"></pre></details>'
        f'<script type="application/json" id="pex-pack">{raw_json}</script>'
        "<script>document.getElementById('raw').textContent=JSON.stringify("
        "JSON.parse(document.getElementById('pex-pack').textContent),null,2)</script>"
    )
    parts.append(
        "<footer>This page verifies itself: "
        "<code class=cmd>uv run python scripts/verify_pack.py &lt;this-file.html&gt;</code><br>"
        "Digests prove these verdicts rest on these exact bytes and events. "
        "They do not prove a live worker ran &mdash; recorded replays are labeled "
        "replay:true + not_live_control:true.</footer></main></body></html>"
    )
    return "".join(parts)


def load_pack(path: Path) -> dict:
    """Read a pack from raw JSON or from a rendered forensic HTML file."""
    text = path.read_text(encoding="utf-8")
    doc = None
    if text.lstrip().startswith("<"):
        start = text.find('<script type="application/json" id="pex-pack">')
        if start != -1:
            start = text.find(">", start) + 1
            end = text.find("</script>", start)
            if end != -1:
                doc = text[start:end]
        if doc is None:
            raise ValueError("no embedded pex-pack JSON found in HTML")
    doc = doc or text
    pack = json.loads(doc)
    if not isinstance(pack, dict):
        raise ValueError("pack is not a JSON object")
    return pack


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pack", help="evidence-pack JSON file")
    parser.add_argument(
        "--html",
        metavar="OUT",
        help="also write a self-contained forensic HTML report to OUT",
    )
    ns = parser.parse_args()
    try:
        pack = load_pack(Path(ns.pack))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"cannot read pack: {exc}", file=sys.stderr)
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
        f"{failures} failed -- internal-consistency proof only, not proof of a live run."
    )
    if ns.html:
        Path(ns.html).write_text(render_html(pack, checks), encoding="utf-8")
        print(f"wrote forensic report: {ns.html}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
