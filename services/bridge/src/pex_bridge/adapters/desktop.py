"""Detect coding-agent desktop apps that are already running.

PEX attaches to these first. CLI binaries are a fallback, not the product.
Never launch a second Cursor. Never launch Hermes/Devin unless asked.
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys

DESKTOP_APPS = (
    {
        "name": "cursor",
        "images": ("Cursor.exe",),
        "kind": "desktop",
        "connect": "hooks",
        "surface": "This Cursor session via ~/.cursor/hooks.json. Never spawn another Cursor.",
    },
    {
        "name": "codex",
        "images": ("ChatGPT.exe",),
        "kind": "desktop",
        "connect": "observe-process",
        "surface": (
            "ChatGPT.exe is observe/focus only. Private desktop JSON-RPC is unproven. "
            "Isolated `codex app-server --listen stdio://` is a separate attach."
        ),
    },
    {
        "name": "grok_bot",
        "images": ("Grok Bot.exe",),
        "kind": "desktop",
        "connect": "observe-process",
        "surface": "Grok Bot desktop (not Grok Build). Observe only; no official local control API.",
    },
    {
        "name": "hermes",
        "images": ("Hermes.exe", "NousHermes.exe"),
        "kind": "desktop",
        "connect": "observe-process",
        "surface": "Hermes desktop if already running. Do not launch it. Control is hermes acp when asked.",
    },
    {
        "name": "devin",
        "images": ("Devin.exe",),
        "kind": "desktop",
        "connect": "observe-process",
        "surface": "Devin desktop if already running. Do not launch it. Control is the Organization API.",
    },
)


def running_image_names() -> set[str]:
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        raw = subprocess.check_output(
            ["tasklist", "/fo", "csv", "/nh"],
            text=True,
            errors="replace",
            **kwargs,
        )
    except Exception:
        return set()
    names: set[str] = set()
    for row in csv.reader(io.StringIO(raw)):
        if row:
            names.add(row[0])
    return names


def list_desktop_apps(running: set[str] | None = None) -> list[dict]:
    images = {name.lower() for name in (running if running is not None else running_image_names())}
    found: list[dict] = []
    for app in DESKTOP_APPS:
        hit = next((image for image in app["images"] if image.lower() in images), None)
        if hit:
            found.append(
                {
                    "name": app["name"],
                    "kind": "desktop",
                    "connect": app["connect"],
                    "process": hit,
                    "surface": app["surface"],
                }
            )
    return found
