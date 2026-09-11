# Packaged bridge bounded idle resource sample

Checkout: clean `899a824`, equal to `origin/main`. The sampled executable is the
exact frozen bridge embedded by current package source `c3cc44c`:

```text
apps/desktop/src-tauri/binaries/pex-bridge-runtime/pex-bridge.exe
```

## Isolation and identity

- read-only preflight confirmed unused loopback port 18081
- zero pre-existing instances of the exact executable path
- isolated ignored profile: `build/idle-bridge-899a824`
- local supervisor mode; no worker, provider call, browser, native PEX WebView,
  credential mutation, or AWS resource
- frozen Windows parent-ownership contract remained enabled
- measured PID 8572 owned the expected executable and listener

## Thirty-second sample

| Second | CPU lifetime seconds | Private MiB | Working set MiB | Threads | Handles |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 2.203 | 78.4 | 97.2 | 11 | 259 |
| 10 | 2.234 | 78.4 | 97.2 | 11 | 259 |
| 20 | 2.234 | 78.4 | 97.2 | 11 | 259 |
| 30 | 2.312 | 78.3 | 97.1 | 8 | 257 |

Across the sample, CPU advanced 0.109 seconds: approximately 0.36% of one core
on average. Private and working-set memory each fell 0.1 MiB. Threads fell from
11 to 8 and handles from 259 to 257. This bounded observation shows no headless
idle growth or busy loop.

The owned terminal sent Ctrl+C only to this process. Uvicorn reported orderly
application shutdown and finished PID 8572. A final identity check found zero
instances of the exact executable and zero listeners on port 18081.

## Boundary

This is a single short headless bridge sample, not a native desktop, WebView/GPU,
long-duration leak, active-worker, or whole-machine result. It narrows but does
not close the prior freeze report. The visible package acceptance must still
sample the complete owned PEX process tree at idle and during one bounded worker
journey.

