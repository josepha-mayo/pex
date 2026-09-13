# PEX second-laptop acceptance and recording card

Use this card on the clean Windows laptop. Stop on the first failed gate and
retain the screenshot/log; do not film around a defect.

## 1. Download and verify

For the current flat-logo candidate, copy
`build/release-candidate-0ea2639/PEX_0.1.0_x64-setup.exe` from the development
laptop. This candidate has been installed and visually checked locally. The
public [PEX 0.1.0 RC1](https://github.com/josepha-mayo/pex/releases/tag/v0.1.0-rc1)
still contains the older `49385f2` build; downloading it will not include the
new logo or supervisor usage receipt.

```powershell
$pexInstaller = '.\PEX_0.1.0_x64-setup.exe'
(Get-Item -LiteralPath $pexInstaller).Length
(Get-FileHash -LiteralPath $pexInstaller -Algorithm SHA256).Hash
```

Expected bytes for `0ea2639`: `101667761`

Expected SHA-256:
`BA170B74EDBB6A7A381F78E1FF360E175462BAEF23EACE63E4192100D2D7074F`

The installer is unsigned, so a Windows publisher warning is expected. Reject
the file if its size or hash differs.

## 2. Clean-start UI gate

Install and open PEX normally. Reject the take if any of these occur:

- bridge Retry/error screen;
- blank, clipped, or frozen main window;
- opaque rectangle behind the pet;
- fast roaming or uncontrolled hopping;
- detached/flying hide control;
- message cannot be dismissed independently;
- anything other than Pex and Von in Companion settings.

Verify Home, Inspector, Deck, and all Settings tabs. Switch Pex to Von once.
Dismiss the status message without hiding Von, then hide and restore the pet
from Settings. Close PEX normally and confirm it disappears promptly.

## 3. OpenCode and Zen BYOK

Install OpenCode if it is not already available. In a new public throwaway
folder, open two terminals. Terminal one:

```powershell
opencode serve --port 4096
```

Terminal two, in the same folder:

```powershell
opencode attach http://127.0.0.1:4096
```

Create the OpenCode session before connecting PEX. In PEX:

1. Settings → Connections → OpenCode URL `http://127.0.0.1:4096` → Connect.
2. Settings → Supervisor → provider `zen`.
3. Model `muse-spark-1.3-contributor-free` exactly.
4. Paste the Zen key off-camera; keep the saved review limit at `3`.
5. Disable provider auto-reload and allow no paid fallback.

Saving configuration is not proof. The Inspector must later show a real
model-backed decision with `used_llm=true` and `runtime=strands-agents`.

## 4. Recovery behavior

Follow [`REHEARSAL_CARD.md`](REHEARSAL_CARD.md) exactly. Attach its persistent
goal, then send the phase-one-only prompt. Do not manually correct the worker.

Accept only if PEX:

- observes `final.txt` missing;
- produces one evidence-specific `SEND_NUDGE`;
- delivers it to the unchanged OpenCode vendor session;
- observes `final.txt` containing `pex-supervised-ok` plus one newline;
- records the correction outcome;
- stops rather than repeatedly nudging.

Verify bytes in the demo workspace:

```powershell
python -c "from pathlib import Path; assert Path('stage-one.txt').read_bytes() == b'stage-one-ok\n'; assert Path('final.txt').read_bytes() == b'pex-supervised-ok\n'; print('Both files match exactly')"
```

## 5. Quiet behavior

Use a second new workspace and OpenCode session. Send the complete-task prompt
from `REHEARSAL_CARD.md`. Accept only if both files exist before review, Strands
returns model-backed `NOOP`, and PEX sends zero follow-ups.

## 6. Bounded performance evidence

With PEX idle after the UI settles, capture two samples 20 seconds apart:

```powershell
$pexProcesses = Get-Process | Where-Object {
  $_.ProcessName -match 'pex|msedgewebview2'
}
$pexProcesses | Select-Object ProcessName, Id, Responding,
  @{Name='PrivateMB';Expression={[math]::Round($_.PrivateMemorySize64 / 1MB, 2)}},
  @{Name='WorkingSetMB';Expression={[math]::Round($_.WorkingSet64 / 1MB, 2)}},
  CPU
```

This is diagnostic: WebView2 may also belong to another application, so confirm
process ancestry before totaling it. Reject the take if PEX is unresponsive or
memory/CPU rises continuously during an otherwise idle sample. Do not claim a
long-run leak result from 20 seconds.

## 7. Record and upload

Use [`VOICEOVER_SCRIPT.md`](VOICEOVER_SCRIPT.md). Keep the final video under
five minutes and publicly playable on YouTube or Vimeo. Never show the Zen key,
email, private task content, or unrelated desktop windows. Say:

- Strands is used live;
- AgentCore is implemented and locally tested, not deployed;
- PexBench integrity passed, but no comparative score is claimed;
- the recovery is controlled behavioral evidence, not a natural failure-rate
  measurement.

Send the public video URL back before final Devpost review and submission.
