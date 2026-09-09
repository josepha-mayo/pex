# Agents for Humans: A Test Command Isn't a Permission Slip

While building PEX's Strands supervisor, one small approval detail stood out: a command starting with `pytest` isn't necessarily just a test command.

`pytest -q` and `pytest -q && curl ...` are different operations. Recognizing the first word isn't enough to approve everything that follows it.

PEX's [local policy code](https://github.com/josepha-mayo/pex/blob/d79b17bd5d536cce62b60713a25db4aadd836bc1/services/bridge/src/pex_bridge/policy/engine.py#L21) checks shell operators, substitutions and redirection before giving familiar test commands their low-risk classification. [Regression tests](https://github.com/josepha-mayo/pex/blob/d79b17bd5d536cce62b60713a25db4aadd836bc1/tests/unit/test_policy_scoring.py#L145) cover chained commands, pipes, redirection, newlines and substitutions.

Even a plain test command runs repository code, so this isn't a sandbox or a universal safety guarantee.

That separation matters for the AgentCore integration too: remote reasoning can propose an action, but it doesn't grant local permission. PEX's local AgentCore-compatible protocol now passes `/ping` and a strict `/invocations` smoke; AWS deployment is still honestly outstanding.

My takeaway: “the model suggested it” and “the user authorized it” should never mean the same thing.

Built and written with AI assistance.
