#!/usr/bin/env bash
set -euo pipefail

# Keep the CI keyring and its fake credential outside the runner profile.
export HOME="$(mktemp -d)"
chmod 700 "$HOME"
printf '%s' 'pex-disposable-ci-keyring' | \
  gnome-keyring-daemon --components=secrets --unlock >/dev/null
uv run --frozen python scripts/smoke_native_keyring.py
