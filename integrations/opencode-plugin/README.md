# PEX OpenCode plugin

This plugin is the reversible, session-scoped JIT overlay surface for OpenCode.
It reads active overlays from the authenticated local PEX bridge and applies only
the supported parts to the matching OpenCode session:

- system instructions through `experimental.chat.system.transform`;
- tool denials through `tool.execute.before`;

Permission-policy overlays are intentionally not advertised: OpenCode declares
`permission.ask` in its plugin types, but the current runtime does not invoke it.
PEX keeps permission mediation on the session-bound HTTP API instead of claiming
that an ignored plugin hook changed policy.

PEX deliberately does not use OpenCode's `PATCH /config` for ephemeral overlays.
That endpoint updates persistent project configuration and deep-merges fields,
so it cannot reliably restore an originally absent key.

## Install

Copy `pex-plugin.js` into one of OpenCode's documented local plugin folders:

- project: `.opencode/plugins/pex-plugin.js`
- global: `~/.config/opencode/plugins/pex-plugin.js`

Run the PEX bridge first. In **PEX Settings → Worker integrations**, provision
OpenCode for the exact project folder before starting it, then set the one-time
value as `PEX_OPENCODE_HOOK_TOKEN` (or `PEX_HOOK_TOKEN`) in OpenCode's launch
environment. The first session-bearing plugin heartbeat binds it to the OpenCode vendor session;
another session or project cannot reuse it. The plugin never reads the
bridge operator bearer or its token file, and connects only to a loopback
`PEX_BRIDGE_URL` (default `http://127.0.0.1:7420`). OpenCode remains usable if
PEX is offline, but PEX will stop advertising overlay capability once the
authenticated plugin heartbeat expires. Token and response reads are bounded,
and the token is re-read from the running process environment for each request.
Because a launched process does not inherit later parent-environment changes,
restart OpenCode with the replacement token after rotating the credential.
