# PEX recording-kit manifest

Prepared for the focused Windows MVP built from product source
`fc20329794a6a453868ca01ea903b4c41f471475`.

## Verify before installing

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `PEX_0.1.0_x64-setup.exe` | 101712659 | `aee5a212997dc4a493cec5a812344af04aed539ef219ee5ddbc78ea33781629c` |
| `PEX_0.1.0_x64_en-US.msi` | 114561048 | `da223af2e251d3cd030fdb3af6a3918fabb5889d6636967739ed864320b94519` |
| `pex-architecture.png` | 104099 | `6839bdcf9667b3de104e87a675df896a75654ff62adc6111bb619d26b41eae73` |
| `pex-mark.png` | 99348 | `61ff11794df490525b95a3e7b83c6c635e641f01c50f1a0cb8187f1276709795` |

Reject any copied file whose byte count or SHA-256 differs. The installers are
unsigned, so a Windows unknown-publisher warning is expected.

## Recording order

1. Read `SECOND_LAPTOP_ACCEPTANCE.md` and stop on its first failed gate.
2. Use `REHEARSAL_CARD.md` verbatim for one controlled OpenCode recovery and
   one separate already-correct quiet case.
3. Follow `RECORDING_RUNBOOK.md` and `VOICEOVER_SCRIPT.md`; the public video must
   be no longer than five minutes.
4. Never show the Zen key, email, private task content, or unrelated windows.
5. Say that Strands is used live, AgentCore is implemented and locally tested
   but not deployed, and PexBench is unfrozen with no valid comparative score.

The public RC1 release contains older product bytes. Do not substitute it for
this kit when recording the current candidate.
