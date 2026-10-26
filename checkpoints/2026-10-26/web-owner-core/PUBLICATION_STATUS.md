# Web-owner core — untested WIP

One standalone stdlib session/configuration source file. Syntax and lint checks only; focused tests, HTTP routes, frontend, real TLS/proxy validation and active WebSocket revocation are not yet implemented or qualified.

No environment or real credentials are read/provisioned. A separate high-entropy owner verifier would need explicit runtime provisioning. Existing native bearer/MCP/hook authorities and model-only live deny-all remain unchanged. This is not a deployable/public-ready web app or a complete recovery of the lost version.
