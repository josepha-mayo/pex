# Release-candidate OpenCode/Strands supervision pair — 12 September 2026

Source: clean `deb2b15f1c9dfe7a6a8ca6f45fc0f5a80809a4cd`, equal to
`origin/main` before and after both runs. Product code is exact package source
`49385f2`; `deb2b15` adds only release evidence and current submission docs.
OpenCode was 1.18.30. The worker was `ling-3.0-flash-fin-free`; the PEX
supervisor was the saved Zen BYOK route `muse-spark-1.3-contributor-free`
through Strands Agents. Both runs used new isolated XDG profiles, a new owned
server on port 4098 and public throwaway workspaces. No paid fallback, AWS
resource, existing user session, native UI or comparative benchmark ran.

Immediately before the calls, the current [official OpenCode Zen page](https://opencode.ai/docs/zen) still
listed Muse Spark 1.3 Contributor Free as free and mapped it to
`https://opencode.ai/zen/v1/responses`. The runners independently refused a
saved provider, model, base URL or secret-store mismatch.

## Controlled same-session recovery

```text
python scripts/opencode_recovery_once.py
  --run-name opencode-recovery-release-deb2b15
```

Result: **PASS**, exit 0, 68.28 seconds.

- The first observed stop had exact `stage-one.txt`, absent `final.txt`, and
  zero earlier PEX follow-ups.
- PEX completed real semantic reviews through Strands and recorded a causal
  recovery pass.
- Exactly one `SEND_NUDGE` reached the same OpenCode vendor session.
- The worker continued and produced exact `final.txt` bytes.
- All 138 observed events settled; the action history contains `NOOP` and
  `SEND_NUDGE`; follow-up count is exactly one.
- The owned server exited and port 4098 was clean afterward.

| Local retained receipt | Bytes | SHA-256 |
| --- | ---: | --- |
| `build/opencode-recovery-release-deb2b15/summary.json` | 1,803 | `7b11a4e023d88adc5231574717601b3dd0cc4e7224425670e263937978d3d187` |
| `build/opencode-recovery-release-deb2b15/receipt.json` | 1,291 | `426b712a1d8b543ec941aa5806b338cf81f7181d08a0caf35a9c9ed7ff8559bf` |

## Correct completion stays quiet

```text
python scripts/opencode_quiet_ten.py
  --run-name opencode-quiet-release-deb2b15
  --case-count 1
```

Result: **PASS**, exit 0, 78.33 seconds.

- Exact output bytes `6170706c652c706561720a` existed before PEX's review,
  and the input remained unchanged.
- The worker completion fence and completion-stop review both passed.
- Two model-backed semantic decisions were both `NOOP`.
- Follow-up count is zero and `unnecessary_interruption` is false.
- All 223 observed events settled.
- The owned server exited and port 4098 was clean afterward.

| Local retained receipt | Bytes | SHA-256 |
| --- | ---: | --- |
| `build/opencode-quiet-release-deb2b15/summary.json` | 2,082 | `502c5c4da80b92328254252f18f49edcd6311177ffc9507bb9ca1c438a55f494` |
| `build/opencode-quiet-release-deb2b15/case-01-deduplicate/receipt.json` | 1,433 | `01e9dd87863e6a949fac6c40a1276ca50469ee2f114349edf36e53a1644aa8f4` |

## Claim boundary

This is a fresh release-source behavioral pair and the strongest current proof
for the demo narrative: PEX distinguishes a controlled incomplete stop from a
correct completion, corrects the former on the same session, and leaves the
latter alone. It is not a frozen four-arm benchmark or an intervention-rate
estimate. It does not prove Cursor treatment, native-desktop-driven supervision,
AWS AgentCore deployment, provider permanence or a zero-cost guarantee beyond
the provider's listing at run time.
