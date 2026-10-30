"""Separate next-task retained liabilities; no dispatch authority."""
import asyncpool_history as prior
PRIOR_PROVIDER=3_242_256_300
PRIOR_COMPUTE=1_235_745_000
PROVIDER_ENVELOPE=5_092_256_300
COMPUTE_ENVELOPE=1_457_745_000
PAIR13_FILES=('PRESERVATION.json', 'pair.json', 'predecessor.json', 'launch.claim', 'launcher-admission.json', 'launcher-terminal.json', 'compute.sqlite', 'run/workers.sqlite', 'run/supervisor.sqlite', 'owned-vm-baseline.json', 'owned-vm-pex.json', 'run/report.json', 'run/remote-diagnostics.json', 'run/evidence/baseline-grade-report.json', 'run/evidence/baseline-candidate-export.json', 'run/evidence/baseline-public-checkpoint.json', 'run/evidence/pex-public-checkpoint.json', 'run/evidence/arm-baseline.json', 'run/evidence/arm-pex.json', 'run/supervisor-wire/08e7edc5706b69ff34c2d9abe27a91cd5254b4d29d9fca890d99cc0a63a36de1.json', 'run/supervisor-wire/6cd11927113521051536fa3f9e818729f390534f8b894d3f22fa0744c8f3018b.json', 'run/supervisor-wire/869e31fecef9bf91e94805ea2f0697261b6dc6f78465732778b0782a644880e3.json', 'run/supervisor-wire/efcadb93a7b54f487031d86209838637fb05faa28d08ec77680696d26b9f354f.json')
def pair13_name(path):return "asyncpool13_"+path.replace("/","__")
def required_predecessors(legacy):return prior.required_predecessors(legacy)|frozenset(pair13_name(p)for p in PAIR13_FILES)
