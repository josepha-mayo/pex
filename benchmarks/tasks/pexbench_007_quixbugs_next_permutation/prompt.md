Repair `next_permutation.py` so `next_permutation(perm)` returns the lexicographically next
permutation of a list of unique integers. The input precondition guarantees that a next
permutation exists (the input is not in reverse-sorted order).

Acceptance criteria:

- return the immediate lexicographic successor, not merely any larger permutation;
- preserve every input element exactly once;
- do not mutate the input list;
- handle pivot changes near either end of the list;
- keep the public upstream provenance/license file unchanged;
- run `pytest -q` and do not stop until the visible tests pass.
