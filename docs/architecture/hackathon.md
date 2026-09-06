# Hackathon architecture diagram

FAQ requires: user input, Strands loop, tools/integrations, AWS services, output. The
diagram uses explicit evidence tiers: green is validated live in the controlled Codex
pair, blue is locally implemented/tested, and dashed gold is a deployment target.

Rendered image for Devpost: [`pex-architecture.png`](pex-architecture.png). Source: [`pex-architecture.mmd`](pex-architecture.mmd).

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
  verifier[Independent Verifier Agent]
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
