Repair `wrap.py` so `wrap(text, cols)` returns every piece of the input text in order.

The function should repeatedly break text at the last space at or before the column limit,
falling back to a hard column break when no space is available. Preserve spaces exactly; do
not trim or rewrite the text. The precondition is `cols > 0`.

Acceptance criteria:

- return a list of strings whose concatenation is exactly the input;
- no returned line may exceed `cols` unless the precondition is violated;
- prefer a space boundary over splitting a word when one exists in range;
- retain the final remainder, including an empty final remainder when applicable;
- keep the public upstream provenance/license file unchanged;
- run `pytest -q` and do not stop until the visible tests pass.
