"""Honest AgentCore deploy preflight. Exits 0 only when deploy tools exist."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone

# Verified 2026-08-25 from
# https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html
# Europe (Stockholm) = eu-north-1: AgentCore Runtime microVMs yes; Runtime Instances no.
PREFERRED_REGION = "eu-north-1"
RUNTIME_MICROVMS = True
RUNTIME_INSTANCES = False
FALLBACK_REGIONS = ("eu-west-1", "eu-central-1")


def check() -> dict:
    aws = shutil.which("aws")
    docker = shutil.which("docker")
    blockers = []
    if not aws:
        blockers.append("AWS CLI is not installed")
    if not docker:
        blockers.append("Docker is not installed")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preferred_region": PREFERRED_REGION,
        "agentcore_runtime_microvms": RUNTIME_MICROVMS,
        "agentcore_runtime_instances": RUNTIME_INSTANCES,
        "fallback_regions": list(FALLBACK_REGIONS),
        "aws_cli": aws,
        "docker": docker,
        "deployable": not blockers,
        "blockers": blockers,
        "source": "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html",
        "note": (
            "Deploy the supervisor image to AgentCore Runtime microVMs in eu-north-1. "
            "Do not assume Runtime Instances (EC2) exist there."
        ),
    }


if __name__ == "__main__":
    report = check()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["deployable"] else 2)
