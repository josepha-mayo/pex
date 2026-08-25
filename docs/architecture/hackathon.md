# Hackathon architecture diagram

FAQ requires: user input, Strands loop, tools/integrations, AWS services, output.

```mermaid
flowchart LR
  human[Human: goals and decisions]
  pet[PEX Pet / Command Deck]
  bridge[Local Bridge + Policy Guard]
  store[(SQLite intent ledger)]
  adapters[Adapter layer]
  cursor[Cursor]
  codex[Codex]
  others[Claude / OpenCode / Qwen / ...]
  strands[Strands Supervisor loop]
  runtime[AgentCore Runtime]
  memory[AgentCore Memory]
  cw[CloudWatch / traces]
  out[Typed interventions]

  human --> pet
  pet <--> bridge
  cursor --> adapters
  codex --> adapters
  others --> adapters
  adapters --> bridge
  bridge --> store
  bridge -->|sanitized events| strands
  strands --> runtime
  runtime --> memory
  runtime --> cw
  strands --> out
  out --> bridge
  bridge -->|policy-gated| adapters
```

Cloud never bypasses local policy. Adapters are capability-negotiated, not assumed equal.
