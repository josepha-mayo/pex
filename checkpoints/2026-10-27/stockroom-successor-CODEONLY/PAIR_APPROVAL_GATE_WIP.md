# Fresh pair approval gate WIP

The fresh Stockroom pair now refuses before configuration or credential-file reads unless root pins the exact new pair approval in source. A caller-supplied RootAdmission cannot grant itself authority. APPROVED_PAIR_REF remains None; the separate supervisor gate also remains None. Authored fixtures patch the reference in memory only.

The current original USD1 funding envelope cannot admit a fresh pair after retained prior uncertainty. The proposed USD2 ceiling is awaiting user approval and is NOT activated by this code. Existing stale budget profiles are not silently updated or reused. No model call, VM, credential access or new runtime configuration is created by this checkpoint.
