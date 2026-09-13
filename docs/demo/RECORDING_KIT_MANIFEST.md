# PEX recording-kit manifest

Prepared for the focused Windows MVP built from product source
`f2832a8651442eb3ee47a508a9c81cc16a82ec5d`.

## Verify before installing

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `PEX_0.1.0_x64-setup.exe` | 101722399 | `63d9f4ae90ac9b3f83f5334b3d3c9abf8ef3db7d8be82e87ff1876f3b007b18a` |
| `PEX_0.1.0_x64_en-US.msi` | 114556952 | `4a3b1119e29933405330b51235b59dbd02bfc58245678787b90a6612ee8dd03e` |
| `pex-architecture.png` | 94752 | `dea91e42f057aea78a2d7c61add7b36de1ad3fc630a742bfd916e1a016fadd68` |
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

The public RC4 release contains these exact product bytes. Do not substitute an
older prerelease when recording the current candidate.
