"""Prove the Nebius Token Factory supervisor path is live-wired.

PEX's semantic supervisor calls an OpenAI-compatible endpoint; provider
`nebius` targets https://api.tokenfactory.nebius.com/v1 with an NVIDIA
Nemotron model - the platform path the hackathon requires (an NVIDIA open
model served by Token Factory, verified end-to-end rather than asserted).

    set NEBIUS_API_KEY=...   # Token Factory -> API Keys
    python scripts/check_token_factory.py            # GET /models only
    python scripts/check_token_factory.py --infer    # + one real inference

Exit codes: 0 ok, 2 no key configured, 1 call failed (honest detail printed).
Nothing is faked: failures print the HTTP status and response excerpt.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import httpx

BASE_URL = os.environ.get("PEX_NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1")
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"


def _key() -> str | None:
    # Same order providers.py resolves them: PEX-specific override first,
    # then the platform-native name.
    for name in ("PEX_SUPERVISOR_API_KEY", "NEBIUS_API_KEY"):
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--infer",
        action="store_true",
        help="also run one real chat completion (bills ~8 tokens)",
    )
    parser.add_argument("--model", default=os.environ.get("PEX_NEBIUS_MODEL", DEFAULT_MODEL))
    args = parser.parse_args()

    key = _key()
    if not key:
        print("no Nebius key configured - set NEBIUS_API_KEY (Token Factory -> API keys).")
        print("this is a real-call smoke; it will not fake a result without one.")
        return 2

    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=30.0) as http:
        started = time.monotonic()
        try:
            models = http.get("/models")
        except httpx.HTTPError as exc:
            print(f"FAIL models: {type(exc).__name__}: {exc}")
            return 1
        elapsed = time.monotonic() - started
        if models.status_code != 200:
            print(f"FAIL models: HTTP {models.status_code} - {models.text[:300]}")
            return 1
        catalog = [m.get("id", "") for m in models.json().get("data", [])]
        nemotron = [m for m in catalog if "nemotron" in m.lower() or "nvidia/" in m.lower()]
        print(f"GET /models  {models.status_code}  {elapsed * 1000:.0f} ms")
        print(f"catalog: {len(catalog)} models; nvidia/nemotron entries: {len(nemotron)}")
        for entry in nemotron[:8]:
            print(f"  - {entry}")
        listed = (
            "  (present in catalog)"
            if args.model in catalog
            else "  (not listed - will still attempt)"
        )
        print(f"selected supervisor model: {args.model}{listed}")

        if not args.infer:
            print("PASS  endpoint + credential verified (run with --infer for a live inference)")
            return 0

        prompt = "Reply with exactly: PEX-TOKEN-FACTORY-OK"
        started = time.monotonic()
        try:
            completion = http.post(
                "/chat/completions",
                json={
                    "model": args.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 16,
                    "temperature": 0,
                },
            )
        except httpx.HTTPError as exc:
            print(f"FAIL inference: {type(exc).__name__}: {exc}")
            return 1
        elapsed = time.monotonic() - started
        if completion.status_code != 200:
            print(f"FAIL inference: HTTP {completion.status_code} - {completion.text[:300]}")
            return 1
        body = completion.json()
        content = body.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        usage = body.get("usage", {})
        print(f"POST /chat/completions  {completion.status_code}  {elapsed * 1000:.0f} ms")
        print(f"model={body.get('model', args.model)}  usage={json.dumps(usage)}")
        print(f"reply: {content[:120]!r}")
        if not content:
            print("FAIL inference: empty completion content")
            return 1
        print("PASS  Nemotron inference via Nebius Token Factory verified")
        return 0


if __name__ == "__main__":
    sys.exit(main())
