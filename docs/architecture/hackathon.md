# Hackathon architecture diagram

FAQ requires: user input, Strands loop, tools/integrations, AWS services, output. The
diagram uses explicit evidence tiers: green is validated live in the controlled Codex
pair at `5c49c10`, blue is locally implemented/tested, and dashed gold is a deployment
target. The independent verifier is blue because the curated live receipt does not expose
judge-readable independent-verifier evidence.

Devpost image target: [`pex-architecture.png`](pex-architecture.png). It was regenerated
and visually inspected on 6 September from the current source; the verifier is visibly in
the blue local-contract tier:
[`pex-architecture.mmd`](pex-architecture.mmd).

```mermaid
flowchart LR
  human[Human: goals and decisions]
  pet[PEX Pet / Command Deck]
  bridge[Local Bridge + Policy Guard]
  store[(SQLite intent ledger)]
  adapters[Adapter layer]
  cursor[Cursor · implemented]
  codex[Codex App Server · validated live]
  others[Claude / OpenCode / Qwen / ...]
  strands[Bounded Strands Supervisor]
  verifier[Independent Verifier Agent · local contract]
  runtime[AgentCore Runtime · deploy target]
  memory[AgentCore Memory when configured]
  cw[CloudWatch when deployed]
  out[Typed interventions]

  human --> pet
  pet <--> bridge
  cursor --> adapters
  codex --> adapters
  others --> adapters
  adapters --> bridge
  bridge --> store
  bridge -->|redacted evidence + read-only tools| strands
  strands -->|semantic-only action| verifier
  bridge -->|same bounded evidence| verifier
  bridge -.->|remote mode| runtime
  runtime -->|hosts both Agents| strands
  runtime --> verifier
  runtime -.-> memory
  runtime -.-> cw
  verifier --> out
  bridge -->|deterministic action| out
  out --> bridge
  bridge -->|policy-gated| adapters
```

Cloud never bypasses local policy. Verifier failure or evidence-free approval becomes NOOP. Adapters are capability-negotiated, not assumed equal. AgentCore, Memory, and CloudWatch are deploy/configuration targets, not current live-service claims.
