# Hermes plugin to PEX

Load `pex_plugin.py` through the official Hermes plugin surface. Before starting
the session, choose **Hermes** and the exact project folder in **PEX Settings →
Worker integrations**. Set the one-time value as `PEX_HERMES_HOOK_TOKEN` (or
`PEX_HOOK_TOKEN`) in the environment that launches Hermes.

The first valid plugin hook atomically binds the credential to its Hermes vendor
session; another session or project cannot reuse it. The plugin never reads the
bridge operator bearer or its token file and fails open if the local bridge is
unavailable.
