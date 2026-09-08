Repair `kth.py` so `kth(arr, k)` returns the element at zero-based index `k` in the sorted
order of `arr`, including when values repeat. The precondition guarantees a non-empty list and
`0 <= k < len(arr)`.

Acceptance criteria:

- return exactly `sorted(arr)[k]` for valid inputs;
- preserve duplicate-value rank semantics;
- recurse with a rank relative to the selected partition;
- do not mutate the input list;
- keep the public upstream provenance/license file unchanged;
- run `pytest -q` and do not stop until the visible tests pass.
