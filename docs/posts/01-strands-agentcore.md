# Agents for Humans: Teaching PEX When to Stay Quiet

I'm building PEX to help with a familiar problem: a coding agent says it's done, but you still have to check everything and tell it what it missed.

PEX is meant to handle some of that babysitting in the agent session you're already using. I'm building its supervisor with Strands Agents, with an Amazon Bedrock AgentCore integration for the runtime.

One lesson from the build: doing nothing needs to be a real decision. Otherwise, a supervisor just becomes another source of interruptions.

The [Strands supervisor code](https://github.com/josepha-mayo/pex/blob/e64270c1e947d3e0f7c95598ec108bc2a28dc282/services/supervisor/src/pex_supervisor/loop.py#L1103) preserves a completed NOOP decision instead of replacing it with an older rule-based warning. Proposed corrections still have to pass separate local policy and session checks.

The [AgentCore entrypoint](https://github.com/josepha-mayo/pex/blob/e64270c1e947d3e0f7c95598ec108bc2a28dc282/services/supervisor/src/pex_supervisor/runtime.py#L171) is implemented, but cloud deployment and the full live correction loop are still unverified. That's the next proof to earn—not something a passing local test can stand in for.

Built and written with AI assistance.
