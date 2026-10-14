"""Probe: does a resolved human ruling reach a NEW session on the same goal?

Usage (while a demo bridge is up on the tamper-run home):
    python scripts/probe_ruling_continuity.py \
        --bridge http://127.0.0.1:7420 --goal goal_<id>

Creates a fresh synthetic session, attaches it to the goal, mints an MCP
session credential, and calls pex.get_relevant_context — then reports
whether the durable human ruling (DECISION-kind context item written by
resolving a worker's pex.request_decision) is delivered to the new worker.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def _control_state(http: httpx.AsyncClient, session_id: str) -> dict:
    response = await http.get(f"/v1/sessions/{session_id}")
    response.raise_for_status()
    return response.json()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="http://127.0.0.1:7420")
    parser.add_argument("--goal", required=True)
    parser.add_argument(
        "--session",
        help="Use an existing sibling session instead of creating a fresh synthetic one",
    )
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.bridge, timeout=30.0) as http:
        goal = (await http.get(f"/v1/goals/{args.goal}")).json()
        if args.session:
            session_id = args.session
            print(f"existing sibling session: {session_id}")
        else:
            session = (
                await http.post(
                    "/v1/synthetic/sessions",
                    json={"vendor_id": "continuity-probe", "cwd": goal["project_id"]},
                )
            ).json()
            session_id = session["id"]
            print(f"fresh session: {session_id}")

            control = await _control_state(http, session_id)
            attached = await http.post(
                f"/v1/sessions/{session_id}/attach",
                json={
                    "idempotency_key": "probe-continuity-attach-0001",
                    "goal_id": args.goal,
                    "expected_goal_id": (control.get("session") or {}).get("goal_id"),
                    "expected_control_revision": control.get("control_revision"),
                    "expected_goal_intent_revision": goal.get("intent_revision"),
                },
            )
            if attached.status_code != 200:
                print(f"attach failed: {attached.status_code} {attached.text[:400]}")
                return 1
            print("attached to goal")

        credential = await http.post(f"/v1/sessions/{session_id}/mcp-credential")
        credential.raise_for_status()
        token = credential.json()["token"]

    async with httpx.AsyncClient(
        base_url=args.bridge,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as worker_http:
        async with streamable_http_client(f"{args.bridge}/mcp/", http_client=worker_http) as (
            read_stream,
            write_stream,
            _sid,
        ):
            async with ClientSession(read_stream, write_stream) as mcp:
                await mcp.initialize()
                result = await mcp.call_tool(
                    "pex.get_relevant_context",
                    {"session_id": session_id, "token_budget": 8_000},
                )
                if result.isError:
                    print(f"get_relevant_context error: {result.content}")
                    return 1
                payload = result.structuredContent or {}
                if set(payload) == {"result"}:
                    payload = payload["result"]
                items = payload.get("items") or payload.get("context") or []
                decisions = [
                    item
                    for item in items
                    if isinstance(item, dict) and item.get("kind") == "decision"
                ]
                print(f"bundle items: {len(items)}")
                for item in decisions:
                    print("--- ruling delivered to fresh session ---")
                    print(item.get("content", "")[:400])
                    print(
                        f"provenance={item.get('provenance')} "
                        f"decision_id={item.get('metadata', {}).get('decision_id')}"
                    )
                if not decisions:
                    print("NO DECISION item in the fresh session's bundle")
                    print(json.dumps(payload, indent=1)[:1500])
                    return 2
                print("CONTINUITY VERIFIED: ruling reached a session created after it")
                return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
