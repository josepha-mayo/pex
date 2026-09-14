# PEX recording-kit manifest

Prepared for the focused Windows MVP built from product source
`5bd01945098284b994f488011848c7aedcfe1863`.

## Verify before installing

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `PEX_0.1.0_x64-setup.exe` | 101737472 | `8f1acb81fbd6f8eabb23b0f3185ac6385855cbde0a5e06f7f9bfa983be21b49f` |
| `PEX_0.1.0_x64_en-US.msi` | 114569240 | `484b71d1ae3c7ce919e91d17f3f83db3648ba8112f73352a9a42743ba0146530` |
| `pex-architecture.png` | 94752 | `dea91e42f057aea78a2d7c61add7b36de1ad3fc630a742bfd916e1a016fadd68` |
| `pex-mark.png` | 99348 | `61ff11794df490525b95a3e7b83c6c635e641f01c50f1a0cb8187f1276709795` |

Reject any copied file whose byte count or SHA-256 differs. The installers are
unsigned, so a Windows unknown-publisher warning is expected.

## Recording order

1. Read `MVP_BEHAVIOR_SCORECARD.md`, then `SECOND_LAPTOP_ACCEPTANCE.md`; stop
   on the acceptance checklist's first failed gate.
2. Use `REHEARSAL_CARD.md` verbatim for one controlled OpenCode recovery and
   one separate already-correct quiet case.
3. Follow `RECORDING_RUNBOOK.md` and `VOICEOVER_SCRIPT.md`; the public video must
   be no longer than five minutes.
4. Never show the Zen key, email, private task content, or unrelated windows.
5. Say that Strands is used live, AgentCore is implemented and locally tested
   but not deployed, and PexBench is unfrozen with no valid comparative score.

The public RC5 release contains these exact product bytes. Do not substitute an
older prerelease when recording the current candidate.

Before the final Devpost action, run `python scripts/submission_preflight.py`
from a clean clone of the repository. It must report `ready:true`; the script
is repository-bound and therefore is not duplicated inside this recording kit.
