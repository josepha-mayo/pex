#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test_home="$(mktemp -d /tmp/pex-model-only-focused.XXXXXX)"
trap 'rm -rf "$test_home"' EXIT
env -i PATH="$PATH" HOME="$test_home" \
  PEX_SUPERVISOR_DISABLE=1 AWS_EC2_METADATA_DISABLED=true \
  PYTHONPATH="$PWD/packages/protocol/src:$PWD/services/supervisor/src:$PWD/services/bridge/src" \
  .venv/bin/python model-only-verification/network_guard.py \
  tests/unit/test_supervisor_model_only.py tests/integration/test_model_only_pipeline.py \
  -q -rs --tb=short
