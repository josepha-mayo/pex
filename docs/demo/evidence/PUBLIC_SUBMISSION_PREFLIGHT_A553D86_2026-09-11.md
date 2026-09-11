# Public submission-material preflight

Checked 11 September 2026 after the current package, behavior and AgentCore/BYOK
evidence was pushed.

## Public repository

`git ls-remote origin refs/heads/main` returned
`a553d867f2a1729e495dcf5277a9bd2bfe4b62ad`. Local `HEAD` and `origin/main`
matched and the working tree was clean. GitHub reported:

- repository: `josepha-mayo/pex`
- visibility: public
- default branch: `main`
- archived: false
- detected license: MIT

The public README points at the current package source `79d4d18`, accepted
same-source OpenCode pair `150ea07`, current ship gate and current package
evidence. A tracked Markdown scan covered 132 files and found no broken public,
setup or evidence link. Its sole syntactic hit was an inert UUID in archived
handoff history, not a link intended for a reader.

## Architecture

`docs/architecture/pex-architecture.png` opened successfully at 1243 x 1733,
RGB, 104,099 bytes, SHA-256
`6839bdcf9667b3de104e87a675df896a75654ff62adc6111bb619d26b41eae73`.
It visibly separates the implemented local PEX/Strands path from the optional
AgentCore Runtime path and labels the latter implemented/offline-tested and not
deployed.

## Remaining submission boundary

This proves current public-source, license, README/link and architecture-file
readiness. It does not prove native installed-app acceptance, supply the required
public five-minute-or-shorter YouTube/Vimeo video, fill the submitter/country/AWS
Builder ID fields, verify the Builder Center article while logged out, publish a
GitHub installer release, acknowledge the rules, or submit the entry.
