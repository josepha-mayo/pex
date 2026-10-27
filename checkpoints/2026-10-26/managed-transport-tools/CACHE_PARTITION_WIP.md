# Cache partition compatibility WIP
Observed live Nebius responses contain prompt_cache_hit_tokens and prompt_cache_miss_tokens. Accept only both strict nonnegative integers, each bounded by prompt_tokens and summing exactly to it; cached_tokens detail, when present, must agree. Unknown fields and malformed counters still fail closed. Full prompt input pricing remains unchanged; no discount or reservation refund.

Primary schema reference: https://api-docs.deepseek.com/api/create-chat-completion/ . This describes alias semantics, not Nebius prices. Authored parser regression tests only; new bytes are not yet live-qualified. Historical failed receipts and retained liabilities remain unchanged.
