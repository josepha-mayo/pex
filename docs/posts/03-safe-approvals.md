# Agents for Humans: A Test Command Isn't a Permission Slip

While building PEX's Strands supervisor, one small approval detail stood out: a command starting with `pytest` isn't necessarily just a test command.

`pytest -q` and `pytest -q && curl ...` are different operations. Recognizing the first word isn't enough to approve everything that follows it.

PEX's [local policy code](https://github.com/josepha-mayo/pex/blob/e64270c1e947d3e0f7c95598ec108bc2a28dc282/services/bridge/src/pex_bridge/policy/engine.py#L20) checks shell operators, substitutions and redirection before giving familiar test commands their low-risk classification. [Regression tests](https://github.com/josepha-mayo/pex/blob/e64270c1e947d3e0f7c95598ec108bc2a28dc282/tests/unit/test_policy_scoring.py#L129) also check that a familiar command cannot erase an explicitly high-risk action label.

Even a plain test command runs repository code, so this isn't a sandbox or a universal safety guarantee.

That separation matters for the AgentCore integration too: remote reasoning can propose an action, but it doesn't grant local permission. Verified cloud deployment and the full live supervisor loop are still outstanding.

My takeaway: “the model suggested it” and “the user authorized it” should never mean the same thing.

Built and written with AI assistance.
