# Agents for Humans: Does Another Agent Actually Save You Time?

Adding a supervisor sounds useful. But if it interrupts constantly, asks for unnecessary checks, or doubles the cost, have we actually helped anyone?

That's the question behind PEX's evaluation plan. PEX uses Strands Agents for supervisory reasoning and includes an AgentCore runtime integration. The goal is less babysitting, not more agent activity.

I'm starting with task success, then counting human interventions, time and cost. The comparison needs the same tasks with and without PEX. The supervisor's own model calls must count too—moving them to another runtime doesn't make them free.

The [benchmark runner](https://github.com/josepha-mayo/pex/blob/e64270c1e947d3e0f7c95598ec108bc2a28dc282/benchmarks/runner.py#L1082) requires treatment overhead metrics. A [regression test](https://github.com/josepha-mayo/pex/blob/e64270c1e947d3e0f7c95598ec108bc2a28dc282/tests/unit/test_pexbench.py#L428) also keeps synthetic smoke results out of the presentation arms.

There isn't a live improvement result to announce yet. The fair comparison and verified AgentCore deployment are still ahead. My takeaway so far: decide what “helpful” means before building a chart that claims you've achieved it.

Built and written with AI assistance.
