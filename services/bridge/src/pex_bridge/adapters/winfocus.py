"""Focus an already-running desktop harness window.

PEX never launches Cursor, Codex, or Grok Bot. It only brings the existing
process to the front. Process image names come from desktop.DESKTOP_APPS.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

HARNESS_IMAGES = {
    "cursor": "Cursor.exe",
    "codex": "ChatGPT.exe",
    "grok_bot": "Grok Bot.exe",
    "hermes": "Hermes.exe",
    "devin": "Devin.exe",
}


def focus_harness(harness: str) -> bool:
    image = HARNESS_IMAGES.get(harness)
    if not image:
        return False
    return focus_image(image)


def focus_image(image_name: str) -> bool:
    if sys.platform != "win32":
        return False
    target = image_name.lower()
    if not target.endswith(".exe"):
        target += ".exe"
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    matches: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: int, _: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return True
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(len(buf))
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
            path = buf.value.lower() if ok else ""
        finally:
            kernel32.CloseHandle(handle)
        if path.endswith("\\" + target) or path.endswith("/" + target):
            matches.append(hwnd)
        return True

    user32.EnumWindows(_enum, 0)
    if not matches:
        return False
    hwnd = matches[0]
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    foreground = user32.GetForegroundWindow()
    current = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(foreground, None)
    user32.AttachThreadInput(current, other, True)
    user32.SetForegroundWindow(hwnd)
    user32.AttachThreadInput(current, other, False)
    return True
