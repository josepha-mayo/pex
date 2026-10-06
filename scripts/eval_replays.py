"""Evaluate the shipped replay fixtures against a live demo bridge.

Runs each fixture through POST /v1/demo/replay — the real pipeline, real
persistence, real claim adjudication — then scores the verification report
against declared expectations. This is the curated fixture suite, not a
benchmark: it measures that the shipped scenarios still demonstrate the
supervision they claim to demonstrate.

Usage: start `python scripts/demo_bridge.py`, then

    python scripts/eval_replays.py [--bridge http://127.0.0.1:7420] [--json out.json]

Exit code is nonzero when any fixture misses its declared arc.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import sys
import urllib.error
import urllib.request

from pex_bridge.demo import score_declared_arc


def _get(base: str, path: str) -> dict | list:
    with urllib.request.urlopen(f"{base}{path}", timeout=60) as response:
        return json.loads(response.read())


def _post(base: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # The replay POST blocks until the trajectory is adjudicated; on a loaded
    # machine the bigger fixtures (captured live runs) can take minutes.
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read())


def _claim_evidence_strings(report: dict) -> set[str]:
    evidence: set[str] = set()
    for claim in report.get("claims") or []:
        for item in claim.get("evidence") or []:
            evidence.add(str(item))
    return evidence


def _score_fixture(base: str, fixture_id: str) -> dict:
    replay = _post(base, "/v1/demo/replay", {"fixture": fixture_id})
    session_id = replay.get("session_id")
    session = _get(base, f"/v1/sessions/{session_id}") if session_id else {}
    goal_id = session.get("goal_id")
    report = _get(base, f"/v1/goals/{goal_id}/verification-report") if goal_id else {}
    completion = report.get("completion") or {}
    claims = report.get("claims") or []
    verdicts = [str(claim.get("verification_status") or "") for claim in claims]
    evidence = _claim_evidence_strings(report)
    summary = report.get("summary") or {}
    integrity = summary.get("integrity_incidents") or 0
    if not isinstance(integrity, int):
        integrity = len(integrity)
    return {
        "fixture": fixture_id,
        "session_id": session_id,
        "goal_id": goal_id,
        "completion_status": completion.get("status"),
        "completion_reason": completion.get("reason"),
        "claims_adjudicated": len(claims),
        "verdicts": verdicts,
        "integrity_incidents": integrity,
        "interventions": [
            str(i.get("action_taken") or i.get("type") or "")
            for i in replay.get("interventions") or []
        ],
        "evidence_strings": sorted(evidence),
    }


_PER_RUN_ID = re.compile(r"=[0-9a-f]{16,64}$")


def _normalized_evidence(result: dict) -> list[str]:
    return [
        _PER_RUN_ID.sub("=<id>", str(item))
        for item in result.get("evidence_strings") or []
    ]


_EVAL_CSS = """
:root{color-scheme:dark;--bg:#0c0f0e;--panel:#131716;--line:#243029;
--ink:#d7e2dc;--dim:#7d8f87;--mint:#5adfa8;--red:#ff7a72;--amber:#e8c46a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 ui-monospace,
Cascadia Mono,Consolas,monospace;padding:32px 20px 64px}
main{max-width:960px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px;letter-spacing:.02em}
.sub{color:var(--dim);font-size:12px}
.mono{word-break:break-all}
.badge{display:inline-block;padding:2px 10px;border-radius:3px;font-weight:600;
font-size:12px;letter-spacing:.08em;margin:12px 8px 0 0}
.badge.ok{background:#123326;color:var(--mint);border:1px solid #1f5b3e}
.badge.bad{background:#3a1512;color:var(--red);border:1px solid #66241f}
.badge.info{background:#1a2a33;color:#8fc9e8;border:1px solid #274b5c}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;
padding:14px 16px;margin:14px 0}
.panel h2{font-size:14px;margin:0 0 2px;letter-spacing:.02em}
.panel .sum{color:var(--dim);font-size:12px;margin:2px 0 8px}
.kv{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:12.5px;color:var(--dim);
margin:6px 0}
.kv b{color:var(--ink);font-weight:600}
.chips{margin:8px 0 0}
.chips span{display:inline-block;padding:1px 8px;margin:0 5px 5px 0;border-radius:3px;
font-size:11.5px;border:1px solid var(--line);color:var(--dim)}
.chips span.ok{color:var(--mint);border-color:#1f5b3e}
.chips span.warn{color:var(--amber);border-color:#5c4a1f}
.lbl{font-size:10.5px;text-transform:uppercase;letter-spacing:.12em;color:var(--dim);
margin-top:10px}
ul.ev{margin:4px 0 0;padding-left:18px;font-size:12px;color:var(--dim)}
ul.fail{margin:8px 0 0;padding-left:18px;font-size:12.5px;color:var(--red)}
.live{font-size:10px;letter-spacing:.08em;color:var(--mint);text-transform:uppercase;
margin-left:8px;vertical-align:middle}
footer{margin-top:44px;color:var(--dim);font-size:12px;border-top:1px solid var(--line);
padding-top:14px}
"""

_VERDICT_OK = {"supported", "verified", "verified_complete"}
_VERDICT_WARN = {"uncertain", "no_claims", "in_progress", "incomplete"}


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def render_html(
    results: list[dict],
    fixture_meta: dict[str, dict],
    bridge: str,
    repeat: int,
) -> str:
    """Render the scored fixture results as a self-contained judge receipt."""
    scored = [r for r in results if "error" not in r]
    failures = [r for r in results if r.get("failures")]
    generated = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        "<!doctype html><html><head><meta charset=utf-8>",
        "<title>PEX fixture suite eval</title>",
        f"<style>{_EVAL_CSS}</style></head><body><main>",
        "<h1>PEX replay fixture suite &mdash; eval receipt</h1>",
        f'<div class="sub">generated {_esc(generated)} &middot; bridge {_esc(bridge)} '
        f"&middot; {repeat} run(s) per fixture, deterministic adjudication required</div>",
    ]
    badge_cls = "ok" if not failures else "bad"
    badge_text = (
        f"{len(scored)}/{len(results)} DECLARED ARCS MET"
        if not failures
        else f"{len(failures)} FIXTURES MISSED THEIR ARC"
    )
    parts.append(f'<span class="badge {badge_cls}">{badge_text}</span>')
    parts.append(
        '<div class="sub" style="margin-top:10px">Each fixture replays through the real '
        "supervision pipeline and is scored against the arc it exists to demonstrate. "
        "Fixture-suite scope only &mdash; this is not a benchmark.</div>"
    )

    for result in results:
        fixture_id = str(result.get("fixture") or "")
        meta = fixture_meta.get(fixture_id) or {}
        title = meta.get("title") or fixture_id
        parts.append('<div class="panel">')
        parts.append(f"<h2>{_esc(title)}")
        if meta.get("captured_from_live_session"):
            parts.append(
                f'<span class="live" title="Exported from recorded live session '
                f'{_esc(meta["captured_from_live_session"])}">from live</span>'
            )
        parts.append("</h2>")
        if meta.get("summary"):
            parts.append(f'<div class="sum">{_esc(meta["summary"])}</div>')
        status = str(result.get("completion_status") or "error")
        status_cls = "ok" if status == "verified_complete" else "info"
        if result.get("failures") or "error" in result:
            status_cls = "bad"
        parts.append(
            f'<span class="badge {status_cls}" style="margin-top:4px">'
            f"completion: {_esc(status)}</span>"
        )
        if "error" in result:
            parts.append(f'<ul class="fail"><li>{_esc(result["error"])}</li></ul></div>')
            continue
        parts.append(
            '<div class="kv">'
            f"<span>claims adjudicated <b>{_esc(result.get('claims_adjudicated', 0))}</b></span>"
            f"<span>integrity incidents <b>{_esc(result.get('integrity_incidents', 0))}</b></span>"
            f"<span>determinism runs <b>{_esc(result.get('runs', 1))}</b></span>"
            f'<span class="mono">session {_esc(str(result.get("session_id") or ""))}</span>'
            "</div>"
        )
        verdicts = [v for v in result.get("verdicts") or [] if v]
        if verdicts:
            parts.append('<div class="lbl">claim verdicts</div><div class="chips">')
            for verdict in verdicts:
                cls = "ok" if verdict in _VERDICT_OK else (
                    "warn" if verdict in _VERDICT_WARN else ""
                )
                parts.append(f'<span class="{cls}">{_esc(verdict)}</span>')
            parts.append("</div>")
        interventions = [i for i in result.get("interventions") or [] if i]
        if interventions:
            parts.append('<div class="lbl">supervision arc</div><div class="chips">')
            for item in interventions:
                parts.append(f"<span>{_esc(item)}</span>")
            parts.append("</div>")
        evidence = result.get("evidence_strings") or []
        if evidence:
            parts.append('<div class="lbl">evidence markers</div><ul class="ev">')
            for item in evidence:
                parts.append(f"<li class=mono>{_esc(item)}</li>")
            parts.append("</ul>")
        failures_list = result.get("failures") or []
        if failures_list:
            parts.append('<ul class="fail">')
            for item in failures_list:
                parts.append(f"<li>{_esc(item)}</li>")
            parts.append("</ul>")
        parts.append("</div>")

    payload = json.dumps(
        {
            "scope": "curated_replay_fixture_suite_not_a_benchmark",
            "bridge": bridge,
            "generated": generated,
            "fixtures": results,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    parts.append(
        '<footer>The embedded JSON below is the same receipt '
        "<code>--json</code> writes &mdash; this page is its human-readable "
        "form, not a separate claim.</footer>"
        f'<script type="application/json" id="eval-receipt">{payload}</script>'
        "</main></body></html>"
    )
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", default="http://127.0.0.1:7420")
    parser.add_argument("--json", default=None, help="write the scored results to a JSON file")
    parser.add_argument(
        "--html",
        default=None,
        help="write a self-contained HTML eval receipt (embeds the same JSON)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="replay each fixture N times; verdicts must be identical across runs",
    )
    args = parser.parse_args()
    base = args.bridge.rstrip("/")

    try:
        trajectories = _get(base, "/v1/demo/trajectories")
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"bridge unreachable at {base}: {exc}", file=sys.stderr)
        return 2
    fixture_ids = [f.get("id") for f in trajectories.get("fixtures") or []]
    fixture_meta = {
        str(f.get("id")): f for f in trajectories.get("fixtures") or [] if f.get("id")
    }

    print(f"{'fixture':<34} {'completion':<18} {'claims':>6} {'incidents':>9} verdict")
    print("-" * 78)
    results = []
    failed = 0
    for fixture_id in fixture_ids:
        try:
            runs = [_score_fixture(base, fixture_id)]
            for _ in range(max(1, args.repeat) - 1):
                runs.append(_score_fixture(base, fixture_id))
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"{fixture_id:<34} ERROR {exc}")
            failed += 1
            results.append({"fixture": fixture_id, "error": str(exc)})
            continue
        result = runs[0]
        # The declared arc travels inside the fixture file — the bridge
        # surfaces it on /v1/demo/trajectories and scores runs against it
        # with the same pex_bridge.demo.score_declared_arc used here.
        expectation = (fixture_meta.get(fixture_id) or {}).get("expected")
        failures = (
            score_declared_arc(expectation, result)
            if isinstance(expectation, dict)
            else ["fixture declares no expected arc"]
        )
        # Determinism: a recorded trajectory replayed again must produce the
        # same adjudication — drift here means hidden state leaking into
        # verdicts. Per-run minted ids (pytest_event_id=…) are normalized
        # before comparing evidence strings.
        for run in runs[1:]:
            for key in (
                "completion_status",
                "claims_adjudicated",
                "integrity_incidents",
                "verdicts",
            ):
                if run.get(key) != result.get(key):
                    failures.append(
                        f"nondeterministic {key}: {result.get(key)} vs {run.get(key)}"
                    )
            if _normalized_evidence(run) != _normalized_evidence(result):
                failures.append(
                    f"nondeterministic evidence_strings: "
                    f"{_normalized_evidence(result)} vs {_normalized_evidence(run)}"
                )
        result["runs"] = len(runs)
        verdict = "PASS" if not failures else "FAIL: " + "; ".join(failures)
        print(
            f"{fixture_id:<34} {str(result['completion_status']):<18} "
            f"{result['claims_adjudicated']:>6} {result['integrity_incidents']:>9} {verdict}"
        )
        result["failures"] = failures
        results.append(result)
        failed += bool(failures)

    scored = sum(1 for r in results if "error" not in r)
    print("-" * 78)
    print(
        f"{scored}/{len(fixture_ids)} fixtures adjudicated; "
        f"{len(fixture_ids) - failed} met the declared arc. "
        f"Fixture-suite scope only -- this is not a benchmark."
    )
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "scope": "curated_replay_fixture_suite_not_a_benchmark",
                    "bridge": base,
                    "fixtures": results,
                },
                handle,
                indent=2,
            )
        print(f"wrote {args.json}")
    if args.html:
        with open(args.html, "w", encoding="utf-8") as handle:
            handle.write(render_html(results, fixture_meta, base, max(1, args.repeat)))
        print(f"wrote {args.html}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
