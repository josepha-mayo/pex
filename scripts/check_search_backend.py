"""Prove a configured web-search backend is live-wired for supervision.

The semantic supervisor exposes `web_search`/`scrape_url` only when a
producer classifies a public-claim feature; when it does, the call routes
through the first configured BYOK backend (Tavily, Firecrawl, Exa, Brave,
Serper — or DuckDuckGo's keyless instant-answer API). Tavily wiring is
what the hackathon's bonus award asks about; this script makes it a
5-second verifiable fact instead of a doc claim.

    set TAVILY_API_KEY=...                    # or PEX_TAVILY_API_KEY
    uv run python scripts/check_search_backend.py                  # auto-pick
    uv run python scripts/check_search_backend.py --provider tavily

Exit codes: 0 ok, 2 no usable backend for the requested provider,
1 call failed (honest detail printed). DuckDuckGo is skipped by default:
its instant-answer API needs no key, so it proves nothing about wiring.
"""

from __future__ import annotations

import argparse
import sys
import time

from pex_supervisor.search import available_search_backends, web_search

KEYED = ("tavily", "firecrawl", "exa", "brave", "serper")
KEY_ENV = {
    "tavily": ("TAVILY_API_KEY", "PEX_TAVILY_API_KEY"),
    "firecrawl": ("FIRECRAWL_API_KEY", "PEX_FIRECRAWL_API_KEY"),
    "exa": ("EXA_API_KEY", "PEX_EXA_API_KEY"),
    "brave": ("BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY", "PEX_BRAVE_API_KEY"),
    "serper": ("SERPER_API_KEY", "PEX_SERPER_API_KEY"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=KEYED,
        default=None,
        help="force one backend instead of auto-picking the first configured one",
    )
    parser.add_argument(
        "--query",
        default="Nebius Token Factory Nemotron",
        help="public-web query to run",
    )
    args = parser.parse_args()

    available = [name for name in available_search_backends() if name in KEYED]
    provider = args.provider or (available[0] if available else None)
    if provider is None:
        print("no keyed search backend configured.")
        print("set one of: " + "; ".join(f"{k} ({'/'.join(v)})" for k, v in KEY_ENV.items()))
        print("this is a real-call smoke; it will not fake a result without a key.")
        return 2
    if provider not in available:
        envs = "/".join(KEY_ENV[provider])
        print(f"{provider} is not configured - set {envs}.")
        print(f"configured keyed backends: {', '.join(available) or 'none'}")
        return 2

    started = time.monotonic()
    result = web_search(args.query, limit=3, provider=provider)
    elapsed = time.monotonic() - started
    if not result.get("ok"):
        print(f"FAIL {provider}: {result.get('error', 'unknown error')}")
        return 1
    results = result.get("results") or []
    print(f"provider={provider}  {elapsed * 1000:.0f} ms  results={len(results)}")
    for row in results[:3]:
        print(f"  - {str(row.get('title') or '')[:80]}  {row.get('url') or ''}")
    if not results:
        print(f"FAIL {provider}: call succeeded but returned no results")
        return 1
    print(f"PASS  {provider} search verified through the supervisor evidence path")
    return 0


if __name__ == "__main__":
    sys.exit(main())
