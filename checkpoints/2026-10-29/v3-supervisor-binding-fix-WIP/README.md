# WIP: bind supervisor to exact registered task

The supervisor previously still compared against the legacy v2 manifest constant. It now revalidates the task through the exact source-pinned registry and config manifest identity. The new task is not admitted from arbitrary caller metadata. Historical consumed claims remain consumed; a fresh root-reviewed identity is required.

Qualification:133 authored/mock tests passed, including construction and identity verification of the actual frozen v3 closed composition, without model or VM calls. The private v3 fixture is deliberately not distributed in this source checkpoint; that specific test skips if absent. A prior failed local construction incurred no worker/supervisor calls or VM allocations; its immutable evidence is retained. No task-solving benefit is claimed.
