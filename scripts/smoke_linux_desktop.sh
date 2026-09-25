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
export WEBKIT_DISABLE_DMABUF_RENDERER=1
mkdir -p build

openbox >build/linux-desktop-window-manager.log 2>&1 &
wm_pid=$!
pex-desktop >build/linux-desktop-smoke.log 2>&1 &
app_pid=$!
cleanup() {
  kill "$app_pid" 2>/dev/null || true
  wait "$app_pid" 2>/dev/null || true
  kill "$wm_pid" 2>/dev/null || true
  wait "$wm_pid" 2>/dev/null || true
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

window_id=$(xdotool search --onlyvisible --name '^PEX$' | sed -n '1p')
xdotool windowactivate "$window_id"
xdotool getwindowgeometry --shell "$window_id" >build/linux-desktop-window-geometry.txt
window_width=$(sed -n 's/^WIDTH=//p' build/linux-desktop-window-geometry.txt)
window_height=$(sed -n 's/^HEIGHT=//p' build/linux-desktop-window-geometry.txt)
if [[ ! "$window_width" =~ ^[0-9]+$ || ! "$window_height" =~ ^[0-9]+$ ||
      "$window_width" -le 800 || "$window_height" -le 560 ]]; then
  echo 'Installed PEX window size is invalid for the repaint check' >&2
  exit 1
fi

workspace_ready=0
for iteration in $(seq 1 30); do
  if ! kill -0 "$app_pid" 2>/dev/null; then
    echo 'Installed PEX desktop exited before its workspace loaded' >&2
    exit 1
  fi
  # Xvfb/WebKit can retain the first composited frame until UI input.
  # Click the empty strip below the command bar to expose the current frame.
  xdotool mousemove --window "$window_id" "$((858 + iteration % 2))" 47 click 1
  if (( iteration == 5 || iteration == 15 || iteration == 25 )); then
    # A one-pixel resize asks the software compositor for a fresh frame without
    # reloading the app or changing its bridge state. Restore the exact size.
    xdotool windowsize "$window_id" "$((window_width - 1))" "$window_height"
    xdotool windowsize "$window_id" "$window_width" "$window_height"
    sleep 0.2
  fi
  scrot -z build/linux-desktop-smoke.png
  if [[ "$iteration" == 1 || "$iteration" == 15 || "$iteration" == 30 ]]; then
    cp build/linux-desktop-smoke.png "build/linux-desktop-check-${iteration}.png"
  fi
  tesseract build/linux-desktop-smoke.png stdout --psm 11 2>/dev/null \
    >build/linux-desktop-smoke-ocr.txt
  if grep -Eiq 'Connect an existing worker' build/linux-desktop-smoke-ocr.txt; then
    workspace_ready=1
    break
  fi
  sleep 2
done
if [[ "$workspace_ready" != 1 ]]; then
  echo 'Installed PEX window did not load fresh authenticated state within 60 seconds; OCR:' >&2
  cat build/linux-desktop-smoke-ocr.txt >&2
  # Distinguish a live React view with stuck native IPC from a frozen webview.
  xdotool mousemove --window "$window_id" 859 47 click 1
  sleep 2
  scrot -z build/linux-desktop-after-settings-click.png
  tesseract build/linux-desktop-after-settings-click.png stdout --psm 11 \
    >build/linux-desktop-after-settings-click-ocr.txt 2>/dev/null || true
  cat build/linux-desktop-after-settings-click-ocr.txt >&2
  curl --silent --show-error --dump-header build/linux-desktop-identity-headers.txt \
    --output /dev/null \
    "http://127.0.0.1:7420/health/identity?challenge=$(printf '0%.0s' {1..64})" || true
  exit 1
fi

# An uncomposited Xvfb desktop renders a transparent overlay as an opaque black
# rectangle. A fresh Linux install keeps it hidden until the user opts in.
if xdotool search --onlyvisible --name '^PEX pet$' >/dev/null 2>&1; then
  echo 'Fresh Linux desktop unexpectedly showed the transparent pet overlay' >&2
  exit 1
fi

# The main command bar must remain usable on this screen.
window_x=$(sed -n 's/^X=//p' build/linux-desktop-window-geometry.txt)
window_y=$(sed -n 's/^Y=//p' build/linux-desktop-window-geometry.txt)
if [[ ! "$window_x" =~ ^-?[0-9]+$ || ! "$window_y" =~ ^-?[0-9]+$ ]]; then
  echo 'Installed PEX window geometry is invalid' >&2
  exit 1
fi
xdotool mousemove "$((window_x + 857))" "$((window_y + 9))"
xdotool getmouselocation --shell >build/linux-desktop-settings-pointer.txt
xdotool click 1
settings_ready=0
for iteration in $(seq 1 8); do
  xdotool mousemove --window "$window_id" "$((858 + iteration % 2))" 47 click 1
  scrot -z build/linux-desktop-settings.png
  tesseract build/linux-desktop-settings.png stdout --psm 11 2>/dev/null \
    >build/linux-desktop-settings-ocr.txt
  if grep -Eiq 'WORKSPACE PREFERENCES|Choose PEX.s model' build/linux-desktop-settings-ocr.txt; then
    settings_ready=1
    break
  fi
  sleep 1
done
if [[ "$settings_ready" != 1 ]]; then
  echo 'Installed PEX Settings navigation was not visible; OCR:' >&2
  cat build/linux-desktop-settings-ocr.txt >&2
  exit 1
fi

printf '%s\n' '{"schema":"pex.linux-desktop-smoke.v1","window_visible":true,"fresh_state_visible":true,"settings_navigation_visible":true,"pet_overlay_default_hidden":true,"anonymous_bridge_status":401,"fresh_profile":true,"cloud_reasoning_requested_off":true}' \
  >build/linux-desktop-smoke.json
