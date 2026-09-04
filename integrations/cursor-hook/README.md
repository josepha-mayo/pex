# Cursor hooks to PEX

Install `hooks.json` with `install.py`; the hook helper connects only to the
loopback bridge and fails open when PEX is unavailable.

Before opening the Cursor conversation, choose **Cursor** and the exact project
folder in **PEX Settings → Worker integrations**. Set the one-time value as
`PEX_CURSOR_HOOK_TOKEN` (or `PEX_HOOK_TOKEN`) in the environment that launches
Cursor. The first valid agent hook atomically binds the credential to its
`conversation_id`; hooks from another conversation or project are rejected.
The helper never reads the bridge operator bearer or its token file.
