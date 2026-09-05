# Local workspace origin and existing Codex attachment

The production inspect route now creates `codex-received.sqlite` in the existing PEX data directory before connecting. It retains potentially sensitive exact received bytes locally, including invalid/partial/vendor data, with immutable requested-inspection provenance; it is not a raw HTTP/model/export or live-replay API. Capacity/failure stops capture without deleting old evidence. Source `db98481` is reviewed and tested; full recovery/installed-worker proof remains open. See [received journal review](../RECEIVED_JOURNAL_REVIEW.md) before handling or copying this private data.

This is the backend connection contract. Settings now contains the explicit connection/recovery caller, reviewed in source `cd39913`, with isolated rendered verification; it is not proof of installed Codex compatibility. Shared worker messaging, approvals and configuration changes remain disabled. PEX still needs its real same-worker supervisory loop. See [connection/control review](../CONNECTION_CONTROL_REVIEW.md).

## Why an origin is required

Two machines can have the same directory name. A registered PEX project can also have a legacy key that looks exactly like a path. Neither fact establishes that it is the local workspace selected for a worker.

The operator explicitly declares this installation's `ProjectOrigin` (namespace and host label). PEX measures local directory identity independently. It never guesses the hostname, relabels project history or treats a supplied physical-identity claim as a measurement. File/device IDs are scoped filesystem evidence, not globally unique machine attestation; see [Python's stat contract](https://docs.python.org/3.12/library/os.html#os.stat_result).

## Setup and recovery

All origin and connection-status endpoints below require the bridge's operator authentication. Never place credentials in example files, URLs, committed scripts or logs.

1. `GET /v1/local-workspace-origin` reads canonical configuration without probing or launching a worker. Status is `unconfigured`, `configured`, `reconfirmation_required` or `unavailable`.
2. For a genuinely unconfigured installation, `PATCH /v1/local-workspace-origin` with:

   ```json
   {
     "origin": {"namespace": "machine", "host": "operator-chosen-name"},
     "expected_revision": null,
     "expected_choice_id": null,
     "confirm_local_origin": true,
     "allow_storage_rebind": false
   }
   ```

   The example name is not a default. Choose the exact origin that represents this local installation. For a named project, its registered local locator must have that origin. Existing project registration/conflict resolution is separate; this endpoint does not create or merge projects.
3. To change a configured choice, supply both the revision and choice ID returned by the latest GET. Every successful save creates a new choice ID. Detach an active shared connection first. Saving invalidates pending inspections and closes their PEX-owned connectors, not the worker.
4. If a copied configuration reports `reconfirmation_required`, inspect the returned old choice, deliberately confirm the installation/origin, and submit its exact revision/ID with `allow_storage_rebind: true`. A malformed or unreadable file is `unavailable`, never silently treated as first-run data or overwritten by this flow.
5. After any uncertain save response, reload. Do not blindly retry with old revision/ID or assume cancellation prevented the save. The bridge holds its attachment lock until its one threaded save settles.

The normal bridge data directory must already exist. Configuration is stored there as `local-origin.json`. Reads do not create directories. Saves use bounded strict JSON, an exclusive flushed temporary file and replacement, verifying the temporary object's ownership and exact bytes before publication.

## Existing-worker selection

1. `POST /v1/adapters/codex/shared/inspect` with the existing socket path, thread ID, PEX project ID and cwd. This authenticated inspection is not consent to subscribe. It returns an expiring inspection/selection pair plus server-measured `workspace_binding` evidence.
2. Review the exact worker, PEX/vendor project distinction, cwd, origin and workspace evidence. `POST /v1/adapters/codex/shared/confirm` requires operator authority, that exact pair and `allow_resume: true`. This subscribes to the selected existing thread; it must not start a new worker turn.
3. `GET /v1/adapters/codex/shared/status` returns current connection ownership, pending selection expiry/confirmability, observation coverage and IDs needed for detach after a client reload. It does not launch a connector, read a vendor thread or resume anything. `observing` describes the stream, not successful supervision or worker control.
4. `POST /v1/adapters/codex/shared/detach` with the exact active inspection/selection pair closes PEX's connector. It does not stop the worker. Detach preserves the prior workspace receipt even if the original directory or origin configuration is no longer available.

A registered project must retain its selected local locator and immutable project identity. An old locator without physical proof cannot bypass a conflicting physical claim for the same local directory. Only a genuinely unregistered exact-directory project key may use the separate legacy path route; origin confirmation and measured directory binding still apply.

## Evidence boundary

Workspace authority is rechecked before subscription and during Store publication. The Store checks locator ownership/membership, conflicting local claims, the current origin choice and the actual session path, while preserving current human goal/pause state. These are sampled checks plus a SQLite transaction, not an atomic filesystem lock, a guarantee against inode reuse, or proof of the cwd handle retained by a worker process.

## Continuous authority and migration

Dedicated publication now also persists a server-owned workspace/subscription witness and the exact origin configuration path in SQLite. Generic session updates cannot grant, replace or drop these fields. Accepted events, new local inspection, planning and adapter-entry paths recheck current workspace authority. A stale connection is retired without reusing the receipt to inspect a replacement directory. Historical observations and actual delivery outcomes remain records; they do not authorize new actions.

Older workspace-bound sessions without that durable witness require explicit detach/reinspection after upgrade. PEX never reconstructs the origin path from client metadata or guesses it from the database location. Truly unbound legacy paths retain their previous contract; they are not newly certified by this change.

Ask PEX reports changed/uncertain workspace authority and revokes local evidence reads and new outer fallback attempts after its review ends. Already-entered provider work cannot be retracted by these checks. See [the continuity review](../WORKSPACE_CONTINUITY_REVIEW.md) for exact verification state, failed cases and remaining sampling/concurrency limits.

Complete raw event capture, crash recovery, safe same-worker delivery and installed runtime compatibility still require separate verification. The desktop source flow is reviewed and tested with an explicit fake API; native end-to-end setup remains unverified. Passing local attachment/continuity tests does not certify those gates.
