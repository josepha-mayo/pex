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

# Catalog deployment regions (tokenfactory.nebius.com/model-catalog.md).
# Public serverless inference is global-routed behind the default base URL;
# the region matters when a deployment is dedicated or region-gated — so on a
# model-not-found we retry the model's regional data plane and report which
# answered, rather than guessing silently.
MODEL_REGION_HINTS = {
    "nvidia/nemotron-3-super-120b-a12b": "us-central1",
    "nvidia/Nemotron-3-Ultra-550b-a55b": "us-central1",
    "nvidia/Nemotron-3.5-Super-VL": "us-north1",
    "nvidia/Nemotron-3_5-Lightning": "eu-north1",
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": "eu-north1",
}


def _regional_base_url(region: str) -> str:
    if region == "eu-north1":
        return "https://api.tokenfactory.nebius.com/v1"
    return f"https://api.tokenfactory.{region}.nebius.com/v1"


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
            if models.status_code == 401 and os.environ.get("PEX_SUPERVISOR_API_KEY", "").strip():
                print(
                    "hint: PEX_SUPERVISOR_API_KEY is set and shadows NEBIUS_API_KEY "
                    "(same override order as providers.py) - if that override is "
                    "stale, unset it for provider=nebius and retry."
                )
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
            # Nemotron reasons before answering — a 16-token cap lets the
            # reasoning exhaust the budget and content comes back null.
            completion = http.post(
                "/chat/completions",
                json={
                    "model": args.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 96,
                    "temperature": 0,
                },
            )
        except httpx.HTTPError as exc:
            print(f"FAIL inference: {type(exc).__name__}: {exc}")
            return 1
        elapsed = time.monotonic() - started
        if completion.status_code != 200:
            # If the model is region-gated (dedicated endpoint semantics),
            # retry once on its catalog region's data plane and say so.
            region = MODEL_REGION_HINTS.get(args.model)
            regional_url = _regional_base_url(region) if region else None
            if regional_url and regional_url != BASE_URL:
                print(
                    f"primary endpoint failed: HTTP {completion.status_code} - "
                    f"{completion.text[:200]}"
                )
                print(f"retrying on the model's catalog region ({region}): {regional_url}")
                started = time.monotonic()
                with httpx.Client(base_url=regional_url, headers=headers, timeout=30.0) as regional:
                    try:
                        completion = regional.post(
                            "/chat/completions",
                            json={
                                "model": args.model,
                                "messages": [{"role": "user", "content": prompt}],
                                "max_tokens": 16,
                                "temperature": 0,
                            },
                        )
                    except httpx.HTTPError as exc:
                        print(f"FAIL inference (regional): {type(exc).__name__}: {exc}")
                        return 1
                elapsed = time.monotonic() - started
                if completion.status_code != 200:
                    print(
                        f"FAIL inference (regional): HTTP {completion.status_code} - "
                        f"{completion.text[:300]}"
                    )
                    return 1
                print(
                    f"note: {args.model} answered on the {region} data plane, "
                    f"not the global endpoint - set PEX_SUPERVISOR_BASE_URL={regional_url}"
                )
            else:
                print(f"FAIL inference: HTTP {completion.status_code} - {completion.text[:300]}")
                return 1
        body = completion.json()
        msg = body.get("choices", [{}])[0].get("message") or {}
        content = (msg.get("content") or "").strip()
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
