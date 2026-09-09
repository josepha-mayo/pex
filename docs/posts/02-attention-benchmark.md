# Agents for Humans: Does Another Agent Actually Save You Time?

If a supervisor interrupts constantly or doubles the cost, has it actually helped anyone?

That's the question behind PEX's evaluation plan. PEX uses Strands Agents with an AgentCore runtime integration. The goal is less babysitting, not more agent activity.

I count task success, human interventions, time and cost on the same tasks with and without PEX. The supervisor's model calls count too—another runtime doesn't make them free.

The [benchmark runner](https://github.com/josepha-mayo/pex/blob/d79b17bd5d536cce62b60713a25db4aadd836bc1/benchmarks/runner.py#L1089) rejects treatment rows without PEX overhead metrics. A [regression test](https://github.com/josepha-mayo/pex/blob/d79b17bd5d536cce62b60713a25db4aadd836bc1/tests/unit/test_pexbench.py#L466) also keeps synthetic smoke results out of the presentation arms.

The current eight-task benchmark and Cursor-hook contracts pass 201/201, but the four-arm manifest is still deliberately unfrozen. There isn't a live improvement result to announce yet. My takeaway so far: decide what “helpful” means before building a chart that claims you've achieved it.

Built and written with AI assistance.
