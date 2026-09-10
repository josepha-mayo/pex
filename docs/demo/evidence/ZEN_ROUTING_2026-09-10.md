# Zen routing repair and offline checkpoint — 10 September 2026

Official source checked: https://opencode.ai/docs/zen/

Zen documents Muse Spark 1.3, 1.2 and Contributor Free on `/responses`.
PEX previously routed only Contributor Free there and sent the other two IDs
through Chat Completions. The existing test incorrectly required that behavior.
Two new parameter cases failed before the repair; both now pass. Big Pickle
remains on Chat Completions. No saved provider/model selection was changed.

The settings API constructor test now includes Zen Big Pickle and Muse Contributor
Free, asserting the exact vault key, endpoint and model ID without returning the
key to the caller. Vault and model constructors are fake; no real secret is read.
This is not a live inference receipt. Plain Muse is paid in the official table;
Contributor Free is separately listed as free. Never substitute the paid ID under
the user's no-billing authorization.

## Verification

```text
.venv\Scripts\python.exe -m pytest -q tests/unit/test_providers.py tests/contract/test_supervisor_settings.py -k 'zen or responses_model or named_byok or named_provider_key_rotation or byok_is_write_only or model_only_patch' --tb=short
```

15 passed, 125 deselected in 12.58 seconds. Ruff passed for the three changed
Python files. Full `test_providers.py` then passed 81 tests in 13.38 seconds,
exit 0, serially after build completion, with no Windows diagnostic in its output.
An earlier full-provider run before the repair reported 79 passes but emitted
Windows `0x8007000e` in `platform._wmi_query` during the Anthropic dependency
import; that earlier run is not treated as clean. Exact cause remains unproven.

Before this routing repair, clean source d1b259b also passed:

- Five selected settings contracts in 12.61 seconds.
- AgentCore client/runtime/preflight/pipeline, Strands runtime and integration:
  212 tests in 32.90 seconds, fake models/clients, no AWS deployment.
- All 268 desktop tests in 6.221 seconds, no native UI.

## Intermediate build, not a submission candidate

At clean source d1b259b, `npm run tauri -- build` exited 0 using pinned Rust
1.97.1 and `CARGO_BUILD_JOBS=2`. All three sidecars and TypeScript/Vite built;
Rust release compilation took 3m 32s. MSI and NSIS were produced. No installer
was installed and no UI/worker was launched. Build warnings: optional Cedar
handler lacks cedarpy; pycparser.lextab/yacctab and tzdata hidden imports missing;
unused Rust bridge_port_state_at. These optional paths are not verified by build.

Current default installer paths were overwritten by that build:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| MSI | 125599744 | `c313c6cd1361562e7b6a051056193690f5a277ec463ac4d04a51e87214d3f892` |
| NSIS | 124323504 | `0565ef98fc1d0b4a3c87f32fcc6dfe51ee55c4a10e7b601d302b2f41d0dd2861` |

They include prior memory-retention fixes but not this Zen repair. Their contents
have not passed the package verifier. Historical 166a656 hashes apply only to the
historical receipt, not these paths. Rebuild and verify the final collected source
before native acceptance. Native testing remains on hold after the Codex incident.
