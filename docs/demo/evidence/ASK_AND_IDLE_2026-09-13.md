# Ask completion explanation and corrected idle measurements

## Ask PEX: report partial evidence without upgrading completion

Native 927106a showed file acceptance supported but overall completion
unconfirmed. The Ask endpoint only returned a generic uncertain answer, hiding
the useful partial result already available in Inspector.

The endpoint now explains that the latest review verified the file acceptance
checks while overall completion remains unconfirmed. The canonical completion
object, verdict computation, goal/workspace authority, and model calls are
unchanged. The extra explanation is limited to fresh uncertain STOP evidence
with supported acceptance on a currently executable goal. Stale, unmet,
non-executable or active-work cases keep their existing answers.

Regression before repair: one failed, four controls passed. After repair:
32 selected-session/authority/workspace/canonical Ask tests passed in 19.07s;
Ruff and diff checks passed. Receipts: `build/ask-partial-before.xml` and
`build/ask-partial-after.xml`. This code is newer than installed 268d39a and
has not yet been accepted in a matching native package. It improves explanation,
not the broader ability to extract/verify a completion claim.

## Correct the CPU measurement before optimizing

The prior PowerShell sampler used `[Math]::Max(0, delta)`. Verified directly:
`[Math]::Max(0, 0.1)` returns 0 while explicit double arguments return 0.1.
The ambiguous overload rounded CPU-time deltas to whole seconds. Earlier CPU
percentages therefore have coarse quantization and must not be used as exact
baselines. Private/working-set memory measurements are unaffected. Original
receipts remain preserved; no prior result was rewritten.

Sampler `build/profile_pex_idle.ps1` now forces double operands and reports
each process. It measures only installed PEX plus its descendants, never all
Python/WebView processes. It prints names/roles, not command lines or secrets.

## Installed 268d39a bounded samples

PEX launched normally; Home showed zero working sessions, no connected worker,
Von, hidden desktop overlay. No test worker/model call was started. Two corrected
30-second samples of the same ten-process tree:

| State | One-core CPU, sum | Private memory, sum | Largest CPU contributors |
| --- | ---: | ---: | --- |
| Home visible | 13.163% | 322.33 MiB | Desktop 5.491%, WebView main 5.443%, bridge 1.710% |
| After PEX minimize | 2.435% | 322.96 MiB | Bridge 1.709%, renderer 0.311%, GPU process 0.208% |

The pet renderer was not the dominant measured CPU contributor. The result
narrows further investigation to visible native/WebView overhead; it does not
prove its mechanism. Native observation tooling and other system activity may
affect samples. This is not a long-duration idle test, leak test, or proof of
performance improvement. No animation or supervision behavior was disabled.

PEX was restored and closed normally; no desktop process remained. Next:
latest-source full offline regression and a controlled visible-host profile
before attributing overhead to a specific component.
