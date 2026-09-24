#!/usr/bin/env bash
set -euo pipefail

package=${1:?pass the built Debian package}
if [[ ! -f "$package" ]]; then
  echo 'Built Debian package is missing' >&2
  exit 1
fi

if [[ ${PEX_LINUX_DESKTOP_SMOKE_INSIDE:-} != 1 ]]; then
  sudo apt-get install -y --no-install-recommends "./$package"
  exec dbus-run-session -- xvfb-run -a -s '-screen 0 1280x800x24' \
    env PEX_LINUX_DESKTOP_SMOKE_INSIDE=1 bash "$0" "$package"
fi

# The runner owns a fresh profile. No provider key or saved worker is present.
export HOME="$(mktemp -d)"
export PEX_CLOUD_REASONING=false
export GDK_BACKEND=x11
export WEBKIT_DISABLE_COMPOSITING_MODE=1
mkdir -p build

pex-desktop >build/linux-desktop-smoke.log 2>&1 &
app_pid=$!
cleanup() {
  kill "$app_pid" 2>/dev/null || true
  wait "$app_pid" 2>/dev/null || true
}
trap cleanup EXIT

ready=0
for _ in $(seq 1 90); do
  if ! kill -0 "$app_pid" 2>/dev/null; then
    echo 'Installed PEX desktop exited before its window and bridge were ready' >&2
    exit 1
  fi
  status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
    http://127.0.0.1:7420/health || true)
  if [[ "$status" == 401 ]] && xdotool search --onlyvisible --name '^PEX$' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then
  echo 'Installed PEX did not show a window and authenticated bridge within 90 seconds' >&2
  exit 1
fi

scrot -z build/linux-desktop-smoke.png
printf '%s\n' '{"schema":"pex.linux-desktop-smoke.v1","window_visible":true,"anonymous_bridge_status":401,"fresh_profile":true,"cloud_reasoning_requested_off":true}' \
  >build/linux-desktop-smoke.json
