# PEX code audit coverage — 5 September 2026

Snapshot: 341 unique tracked or untracked source/configuration paths from the current checkout. Includes tests and fixtures. Excludes generated dependency lockfiles and node_modules/target/dist/results/_audit trees; release dependencies, raw evidence, assets and prose docs need separate targeted checks. This is an inventory, **not evidence that every file has been reviewed**.

All entries start `PENDING` for the fresh independent audit. Replace status only with specific coverage evidence from the reviewer; reading a diff, searching a symbol or passing a test does not equal full-file review. Record unresolved findings in SHIP_CHECKLIST.md or a linked findings log. New source files must be added and changed files re-reviewed.

| File | Audit responsibility | Fresh audit status |
| --- | --- | --- |
| `apps/desktop/package.json` | UI / release | PENDING |
| `apps/desktop/scripts/build-sidecar.mjs` | UI / release | PENDING |
| `apps/desktop/scripts/record_submission_demo.py` | UI / release | PENDING |
| `apps/desktop/scripts/release-contract.mjs` | UI / release | PENDING |
| `apps/desktop/scripts/release-contract.test.mjs` | UI / release | PENDING |
| `apps/desktop/src-tauri/build.rs` | UI / release | PENDING |
| `apps/desktop/src-tauri/capabilities/default.json` | UI / release | PENDING |
| `apps/desktop/src-tauri/capabilities/pet.json` | UI / release | PENDING |
| `apps/desktop/src-tauri/Cargo.toml` | UI / release | PENDING |
| `apps/desktop/src-tauri/permissions/focus.toml` | UI / release | PENDING |
| `apps/desktop/src-tauri/src/main.rs` | UI / release | PENDING |
| `apps/desktop/src-tauri/tauri.conf.json` | UI / release | PENDING |
| `apps/desktop/src/App.tsx` | UI / release | PENDING |
| `apps/desktop/src/components/AskPex.tsx` | UI / release | PENDING |
| `apps/desktop/src/components/CommandDeck.tsx` | UI / release | PENDING |
| `apps/desktop/src/components/GoalEditor.tsx` | UI / release | PENDING |
| `apps/desktop/src/components/Inspector.tsx` | UI / release | PENDING |
| `apps/desktop/src/components/PetStage.tsx` | UI / release | PENDING |
| `apps/desktop/src/components/ProjectIdentityPanel.tsx` | UI / release | PENDING |
| `apps/desktop/src/components/SettingsPage.tsx` | UI / release | PENDING |
| `apps/desktop/src/decisionContract.ts` | UI / release | PENDING |
| `apps/desktop/src/main.tsx` | UI / release | PENDING |
| `apps/desktop/src/pets/atlas.tsx` | UI / release | PENDING |
| `apps/desktop/src/pets/atlasMath.ts` | UI / release | PENDING |
| `apps/desktop/src/pets/drift/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/ember/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/ledger/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/mesh/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/nudge/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/pex/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/quiet/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/release-manifest.json` | UI / release | PENDING |
| `apps/desktop/src/pets/types.ts` | UI / release | PENDING |
| `apps/desktop/src/pets/von/pet.json` | UI / release | PENDING |
| `apps/desktop/src/releasePet.ts` | UI / release | PENDING |
| `apps/desktop/src/types.ts` | UI / release | PENDING |
| `apps/desktop/src/viewModel.test.ts` | UI / release | PENDING |
| `apps/desktop/src/viewModel.ts` | UI / release | PENDING |
| `apps/desktop/src/vite-env.d.ts` | UI / release | PENDING |
| `apps/desktop/tsconfig.json` | UI / release | PENDING |
| `apps/desktop/vite.config.ts` | UI / release | PENDING |
| `benchmarks/boundary.py` | Harness / integrity | PENDING |
| `benchmarks/cursor_capture.py` | Harness / integrity | PENDING |
| `benchmarks/cursor_isolated_stop.py` | Harness / integrity | PENDING |
| `benchmarks/evaluator.py` | Harness / integrity | PENDING |
| `benchmarks/four_arm.py` | Harness / integrity | PENDING |
| `benchmarks/manifest.yaml` | Harness / integrity | PENDING |
| `benchmarks/pex_attach.py` | Harness / integrity | PENDING |
| `benchmarks/pex_supervisor_process.py` | Harness / integrity | PENDING |
| `benchmarks/report.py` | Harness / integrity | PENDING |
| `benchmarks/runner.py` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_001_premature_stop/metadata.yaml` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_002_drift/metadata.yaml` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_003_permission_spam/metadata.yaml` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_004_false_claim/metadata.yaml` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_005_handoff/metadata.yaml` | Harness / integrity | PENDING |
| `deploy/agentcore/preflight.py` | Backend / release cross-review | PENDING |
| `docker-compose.yml` | Backend / release cross-review | PENDING |
| `fixtures/demo/dataset_before_eval.json` | Backend / release cross-review | PENDING |
| `fixtures/demo/premature_stop_eval.json` | Backend / release cross-review | PENDING |
| `integrations/claude-hook/settings.fragment.json` | Harness / integrity | PENDING |
| `integrations/cursor-hook/hooks.json` | Harness / integrity | PENDING |
| `integrations/cursor-hook/install.py` | Harness / integrity | PENDING |
| `integrations/cursor-hook/pex_cursor_hook.py` | Harness / integrity | PENDING |
| `integrations/cursor-hook/pex_cursor_observe.py` | Harness / integrity | PENDING |
| `integrations/hermes-plugin/pex_plugin.py` | Harness / integrity | PENDING |
| `integrations/hooks/pex_hook.py` | Harness / integrity | PENDING |
| `integrations/opencode-plugin/pex-plugin.js` | Harness / integrity | PENDING |
| `integrations/qwen-hook/settings.fragment.json` | Harness / integrity | PENDING |
| `packages/protocol-ts/src/index.ts` | Backend / release cross-review | PENDING |
| `packages/protocol/pyproject.toml` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/__init__.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/actions.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/capabilities.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/context.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/enums.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/fingerprint.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/goal.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/intervention.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/overlay.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/project_identity.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/redaction.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/session.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/supervisor.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/verification.py` | Backend / release cross-review | PENDING |
| `pyproject.toml` | Backend / release cross-review | PENDING |
| `rust-toolchain.toml` | Backend / release cross-review | PENDING |
| `scripts/install.ps1` | Backend / release cross-review | PENDING |
| `scripts/pet_atlas_runtime_contract.py` | Backend / release cross-review | PENDING |
| `services/bridge/pyproject.toml` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/__init__.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/__main__.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/adapters/__init__.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/acp_client.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/acp_harness.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/attach.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/base.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/claude_code.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/codex_bin.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/codex.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/connect.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/cursor_bin.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/cursor_hooks.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/cursor_inbox.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/cursor.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/desktop.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/devin.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/discover.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/fleet.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/grok_bot.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/grok_build_bin.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/grok_build.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/hermes_bin.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/http_json.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/opencode.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/qwen.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/strict_json.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/synthetic.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/winfocus.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/agentcore.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/app.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/ask.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/benchmark_public.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/bus.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/channels.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/claims.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/config.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/context/__init__.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/context/health.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/context/mesh.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/cursor_delivery.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/decision_delivery.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/decisions.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/deep_links.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/demo.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/executor.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/fingerprints.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/handoff_views.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/hook_auth.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/intent.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/ledger.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/main.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/mcp_auth.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/mcp_server.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/observe.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/origin_guard.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/overlay_runtime.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/pets/__init__.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/pets/atlas.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/pets/hatch_store.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/pets/hatch.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/pets/imagegen.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/pipeline.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/policy/__init__.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/policy/engine.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/request_limits.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/scoring.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/secrets.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/shell_state.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/speculative.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/store.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/supervisor_config.py` | Backend / release cross-review | PENDING |
| `services/supervisor/pyproject.toml` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/__init__.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/ask_review.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/background.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/catalog.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/drift.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/evidence_tools.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/inspect_http.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/loop.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/planner.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/providers.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/public_task.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/runtime.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/search.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/verify.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/workspace.py` | Backend / release cross-review | PENDING |
| `tests/__init__.py` | Test cross-review | PENDING |
| `tests/chaos/test_malformed_events.py` | Test cross-review | PENDING |
| `tests/conftest.py` | Test cross-review | PENDING |
| `tests/contract/__init__.py` | Test cross-review | PENDING |
| `tests/contract/codex_live_proof.py` | Test cross-review | PENDING |
| `tests/contract/live_gate.py` | Test cross-review | PENDING |
| `tests/contract/test_authorization_inventory.py` | Test cross-review | PENDING |
| `tests/contract/test_cursor_capture_hooks.py` | Test cross-review | PENDING |
| `tests/contract/test_cursor_delivery_ack_hook.py` | Test cross-review | PENDING |
| `tests/contract/test_cursor_hooks.py` | Test cross-review | PENDING |
| `tests/contract/test_cursor_prompt_policy.py` | Test cross-review | PENDING |
| `tests/contract/test_intent_guardrails.py` | Test cross-review | PENDING |
| `tests/contract/test_live_agentcore.py` | Test cross-review | PENDING |
| `tests/contract/test_live_claude_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_codex_pump.py` | Test cross-review | PENDING |
| `tests/contract/test_live_codex.py` | Test cross-review | PENDING |
| `tests/contract/test_live_cursor_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_devin_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_grok_build_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_hermes_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_kimi_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_omp_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_opencode_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_opencode.py` | Test cross-review | PENDING |
| `tests/contract/test_live_qwen_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_supervisor.py` | Test cross-review | PENDING |
| `tests/contract/test_supervisor_settings.py` | Test cross-review | PENDING |
| `tests/e2e/test_ask_canonical.py` | Test cross-review | PENDING |
| `tests/e2e/test_decision_resolution.py` | Test cross-review | PENDING |
| `tests/e2e/test_direct_message_durability.py` | Test cross-review | PENDING |
| `tests/e2e/test_goal_control_operation_routes.py` | Test cross-review | PENDING |
| `tests/e2e/test_goal_lifecycle.py` | Test cross-review | PENDING |
| `tests/e2e/test_handoff_and_permissions.py` | Test cross-review | PENDING |
| `tests/e2e/test_handoff_timeout_safety.py` | Test cross-review | PENDING |
| `tests/e2e/test_hatch_operator_api.py` | Test cross-review | PENDING |
| `tests/e2e/test_hook_credentials.py` | Test cross-review | PENDING |
| `tests/e2e/test_lifecycle_decision_resolution.py` | Test cross-review | PENDING |
| `tests/e2e/test_m0_roundtrip.py` | Test cross-review | PENDING |
| `tests/e2e/test_mcp_adversarial_boundary.py` | Test cross-review | PENDING |
| `tests/e2e/test_mcp_credentials.py` | Test cross-review | PENDING |
| `tests/e2e/test_mcp_safety_contract.py` | Test cross-review | PENDING |
| `tests/e2e/test_mcp_server.py` | Test cross-review | PENDING |
| `tests/e2e/test_mcp_verify_claim_atomic.py` | Test cross-review | PENDING |
| `tests/e2e/test_overlay_revert_operator_auth.py` | Test cross-review | PENDING |
| `tests/e2e/test_project_identity_operator_api.py` | Test cross-review | PENDING |
| `tests/e2e/test_recovery_stop_loop.py` | Test cross-review | PENDING |
| `tests/e2e/test_remote_channels.py` | Test cross-review | PENDING |
| `tests/e2e/test_speculative_execution.py` | Test cross-review | PENDING |
| `tests/integration/test_strands_supervisor.py` | Test cross-review | PENDING |
| `tests/unit/test_acp_cursor.py` | Test cross-review | PENDING |
| `tests/unit/test_adapter_capabilities.py` | Test cross-review | PENDING |
| `tests/unit/test_adapter_deep_audit.py` | Test cross-review | PENDING |
| `tests/unit/test_adapter_protocol_safety.py` | Test cross-review | PENDING |
| `tests/unit/test_agentcore_client.py` | Test cross-review | PENDING |
| `tests/unit/test_agentcore_pipeline.py` | Test cross-review | PENDING |
| `tests/unit/test_agentcore_preflight.py` | Test cross-review | PENDING |
| `tests/unit/test_agentcore_runtime.py` | Test cross-review | PENDING |
| `tests/unit/test_artifact_project_bindings.py` | Test cross-review | PENDING |
| `tests/unit/test_ask_review.py` | Test cross-review | PENDING |
| `tests/unit/test_ask.py` | Test cross-review | PENDING |
| `tests/unit/test_attach_security.py` | Test cross-review | PENDING |
| `tests/unit/test_attention_metrics.py` | Test cross-review | PENDING |
| `tests/unit/test_audit_invariants.py` | Test cross-review | PENDING |
| `tests/unit/test_auth.py` | Test cross-review | PENDING |
| `tests/unit/test_authority_consumer_wiring.py` | Test cross-review | PENDING |
| `tests/unit/test_background.py` | Test cross-review | PENDING |
| `tests/unit/test_benchmark_execution_safety.py` | Test cross-review | PENDING |
| `tests/unit/test_benchmark_public.py` | Test cross-review | PENDING |
| `tests/unit/test_broadcast_serialization.py` | Test cross-review | PENDING |
| `tests/unit/test_channels.py` | Test cross-review | PENDING |
| `tests/unit/test_claim_verification_protocol.py` | Test cross-review | PENDING |
| `tests/unit/test_claims_and_shell_state.py` | Test cross-review | PENDING |
| `tests/unit/test_claims.py` | Test cross-review | PENDING |
| `tests/unit/test_cleanup_executor_ledger.py` | Test cross-review | PENDING |
| `tests/unit/test_cleanup_restore_executor_ledger.py` | Test cross-review | PENDING |
| `tests/unit/test_codex_live_proof.py` | Test cross-review | PENDING |
| `tests/unit/test_codex_pipeline_pump.py` | Test cross-review | PENDING |
| `tests/unit/test_config_security.py` | Test cross-review | PENDING |
| `tests/unit/test_context_handoff_protocol.py` | Test cross-review | PENDING |
| `tests/unit/test_context_health.py` | Test cross-review | PENDING |
| `tests/unit/test_context_mesh.py` | Test cross-review | PENDING |
| `tests/unit/test_control_file_bounds.py` | Test cross-review | PENDING |
| `tests/unit/test_credential_project_bindings.py` | Test cross-review | PENDING |
| `tests/unit/test_cursor_capture.py` | Test cross-review | PENDING |
| `tests/unit/test_cursor_delivery_store.py` | Test cross-review | PENDING |
| `tests/unit/test_cursor_followup_receipt.py` | Test cross-review | PENDING |
| `tests/unit/test_cursor_hook_preparation.py` | Test cross-review | PENDING |
| `tests/unit/test_cursor_stop_response_authority.py` | Test cross-review | PENDING |
| `tests/unit/test_deep_links.py` | Test cross-review | PENDING |
| `tests/unit/test_demo_security.py` | Test cross-review | PENDING |
| `tests/unit/test_drift.py` | Test cross-review | PENDING |
| `tests/unit/test_event_bus.py` | Test cross-review | PENDING |
| `tests/unit/test_event_processing_pipeline.py` | Test cross-review | PENDING |
| `tests/unit/test_event_processing_store.py` | Test cross-review | PENDING |
| `tests/unit/test_event_publications.py` | Test cross-review | PENDING |
| `tests/unit/test_evidence_tools.py` | Test cross-review | PENDING |
| `tests/unit/test_existing_sessions.py` | Test cross-review | PENDING |
| `tests/unit/test_fleet_pets_codex.py` | Test cross-review | PENDING |
| `tests/unit/test_goal_control_operations.py` | Test cross-review | PENDING |
| `tests/unit/test_goal_intent_authority.py` | Test cross-review | PENDING |
| `tests/unit/test_goal_intent_semantics.py` | Test cross-review | PENDING |
| `tests/unit/test_goal_store_transaction.py` | Test cross-review | PENDING |
| `tests/unit/test_handoff_assimilation_paths.py` | Test cross-review | PENDING |
| `tests/unit/test_hatch_durability.py` | Test cross-review | PENDING |
| `tests/unit/test_hatch_imagegen_security.py` | Test cross-review | PENDING |
| `tests/unit/test_host_guard.py` | Test cross-review | PENDING |
| `tests/unit/test_human_decision_delivery.py` | Test cross-review | PENDING |
| `tests/unit/test_human_decision_protocol.py` | Test cross-review | PENDING |
| `tests/unit/test_inspect_http.py` | Test cross-review | PENDING |
| `tests/unit/test_intent_guardrails.py` | Test cross-review | PENDING |
| `tests/unit/test_intervention_authority_consumers.py` | Test cross-review | PENDING |
| `tests/unit/test_leakage.py` | Test cross-review | PENDING |
| `tests/unit/test_lifecycle_actions.py` | Test cross-review | PENDING |
| `tests/unit/test_lifecycle_resource_operations.py` | Test cross-review | PENDING |
| `tests/unit/test_lifecycle_restore_operations.py` | Test cross-review | PENDING |
| `tests/unit/test_mcp_auth_middleware.py` | Test cross-review | PENDING |
| `tests/unit/test_mcp_auth.py` | Test cross-review | PENDING |
| `tests/unit/test_named_hook_deadline.py` | Test cross-review | PENDING |
| `tests/unit/test_observe_security.py` | Test cross-review | PENDING |
| `tests/unit/test_opencode_fork.py` | Test cross-review | PENDING |
| `tests/unit/test_opencode_pipeline_pump.py` | Test cross-review | PENDING |
| `tests/unit/test_operator_effects.py` | Test cross-review | PENDING |
| `tests/unit/test_operator_handoff_effects.py` | Test cross-review | PENDING |
| `tests/unit/test_overlay_executor_ledger.py` | Test cross-review | PENDING |
| `tests/unit/test_overlay_lifecycle.py` | Test cross-review | PENDING |
| `tests/unit/test_overlay_pipeline_recovery.py` | Test cross-review | PENDING |
| `tests/unit/test_overlay_runtime.py` | Test cross-review | PENDING |
| `tests/unit/test_overlay_store_authority.py` | Test cross-review | PENDING |
| `tests/unit/test_pet_atlas_runtime_contract.py` | Test cross-review | PENDING |
| `tests/unit/test_pet_hatch.py` | Test cross-review | PENDING |
| `tests/unit/test_pet_snapshot.py` | Test cross-review | PENDING |
| `tests/unit/test_pexbench.py` | Test cross-review | PENDING |
| `tests/unit/test_pipeline_serialization.py` | Test cross-review | PENDING |
| `tests/unit/test_pipeline_session_merge.py` | Test cross-review | PENDING |
| `tests/unit/test_planner.py` | Test cross-review | PENDING |
| `tests/unit/test_policy_scoring.py` | Test cross-review | PENDING |
| `tests/unit/test_progress_protocol.py` | Test cross-review | PENDING |
| `tests/unit/test_project_identity_store.py` | Test cross-review | PENDING |
| `tests/unit/test_project_identity.py` | Test cross-review | PENDING |
| `tests/unit/test_providers.py` | Test cross-review | PENDING |
| `tests/unit/test_public_task.py` | Test cross-review | PENDING |
| `tests/unit/test_request_limits.py` | Test cross-review | PENDING |
| `tests/unit/test_resolution_dispatch_identity.py` | Test cross-review | PENDING |
| `tests/unit/test_scoring.py` | Test cross-review | PENDING |
| `tests/unit/test_search.py` | Test cross-review | PENDING |
| `tests/unit/test_session_control_transactions.py` | Test cross-review | PENDING |
| `tests/unit/test_shell_state.py` | Test cross-review | PENDING |
| `tests/unit/test_speculative.py` | Test cross-review | PENDING |
| `tests/unit/test_store_artifact_transactions.py` | Test cross-review | PENDING |
| `tests/unit/test_store_audit_outbox.py` | Test cross-review | PENDING |
| `tests/unit/test_store_canonical_queries.py` | Test cross-review | PENDING |
| `tests/unit/test_store_fingerprints.py` | Test cross-review | PENDING |
| `tests/unit/test_store_mcp_decision.py` | Test cross-review | PENDING |
| `tests/unit/test_store_mcp_integrity.py` | Test cross-review | PENDING |
| `tests/unit/test_store_mcp_verify_claim.py` | Test cross-review | PENDING |
| `tests/unit/test_strands_runtime.py` | Test cross-review | PENDING |
| `tests/unit/test_supervisor_config.py` | Test cross-review | PENDING |
| `tests/unit/test_supervisor_loop.py` | Test cross-review | PENDING |
| `tests/unit/test_verification_protocol.py` | Test cross-review | PENDING |
| `tests/unit/test_verify.py` | Test cross-review | PENDING |
| `tests/unit/test_websocket_auth.py` | Test cross-review | PENDING |
| `tests/unit/test_worker_hook_credentials.py` | Test cross-review | PENDING |
| `tests/unit/test_workspace_inspect.py` | Test cross-review | PENDING |
