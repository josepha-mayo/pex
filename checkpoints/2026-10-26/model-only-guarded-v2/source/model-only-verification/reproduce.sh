#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Dependencies were installed separately from official PyPI. Never inherit
# provider credentials, application environment, proxy, or the real user HOME.
test_home="$(mktemp -d /tmp/pex-model-only-test-home.XXXXXX)"
trap 'rm -rf "$test_home"' EXIT
env -i PATH="$PATH" HOME="$test_home" \
  PEX_SUPERVISOR_DISABLE=1 AWS_EC2_METADATA_DISABLED=true \
  PYTHONPATH="$PWD/packages/protocol/src:$PWD/services/supervisor/src:$PWD/services/bridge/src" \
  .venv/bin/python model-only-verification/network_guard.py \
  tests/unit/test_supervisor_model_only.py \
  tests/integration/test_model_only_pipeline.py \
  tests/unit/test_supervisor_loop.py tests/unit/test_supervisor_config.py \
  tests/unit/test_strands_runtime.py tests/unit/test_agentcore_client.py \
  tests/unit/test_agentcore_pipeline.py tests/unit/test_event_processing_pipeline.py \
  tests/unit/test_event_processing_store.py tests/unit/test_supervisor_context.py \
  tests/unit/test_supervisor_evidence_observations.py \
  tests/integration/test_strands_supervisor.py tests/unit/test_agentcore_runtime.py \
  tests/contract/test_supervisor_settings.py tests/unit/test_operator_handoff_effects.py \
  tests/unit/test_workspace_operator_handoff.py tests/unit/test_handoff_assimilation_paths.py \
  -q -rs --tb=short
