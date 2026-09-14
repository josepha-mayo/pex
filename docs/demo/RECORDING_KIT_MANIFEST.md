# PEX recording-kit manifest

Prepared for the focused Windows MVP built from product source
`bd0471ffee43df60b95570df30a402b725f049c1`.

## Verify before installing

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `PEX_0.1.0_x64-setup.exe` | 101735091 | `07b82aa3c5685f3f4c0695a5b7b1e9c7bd6e26f70cc70c835545bac992b10d75` |
| `PEX_0.1.0_x64_en-US.msi` | 114581528 | `fb51eadd631f29fb17c8ddb56f26cadcae68e70c647f9d4023a62562e4fba8bb` |
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

The public RC6 release contains these exact product bytes. Do not substitute an
older prerelease when recording the current candidate.

Before the final Devpost action, run `python scripts/submission_preflight.py`
from a clean clone of the repository. It must report `ready:true`; the script
is repository-bound and therefore is not duplicated inside this recording kit.
