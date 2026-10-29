# WIP: explicit private temporary storage and capacity checks

A new independently reviewed run identity uses a private non-symlink temporary-filesystem path. No paid resources or old claim are reused. Task, checks and equal model budgets are unchanged; historical unknown liabilities remain reserved.

Before resources, the private storage path must have at least1536MiB free and1024MiB available system memory. During the owned run, a1-second soft monitor cancels that run if free storage or available memory drops below512MiB, or owned regular files reach1024MiB. The caller retains cleanup responsibility. Symlinks outside the owned tree are not followed or counted.

Important qualification: this is a sampled soft guard, NOT a filesystem quota or exact aggregate-output bound. CLI database growth is not hard-bounded and samples can overshoot. Temporary storage is not persistent; actual evidence requires a later lossless hash-verified private persistent backup. Capacity failures are infrastructure failures, not task failures or evidence of benchmark benefit.

109 focused admission and worker-path/storage tests passed, including insufficient-capacity refusal, symlink refusal, owned-only accounting, cancellation/finalization and successful-return propagation. No provider, VM or credentials were used by these tests.
