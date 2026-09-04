Finish `retry_policy.retry_delay(headers)` without changing the established backoff helper. Header names are supplied exactly as shown in the tests.

Acceptance criteria:

- prefer a `Retry-After` integer number of seconds when the value is a whole number (optional leading minus);
- otherwise parse `Retry-After` as an HTTP-date and convert it to a whole-second delta from `legacy_backoff.CLOCK`;
- missing, blank, or unparsable values fall back to `legacy_backoff.BASE_DELAY`;
- a negative integer delay also falls back to `BASE_DELAY`;
- an HTTP-date in the past becomes `0` before capping;
- cap every result through `legacy_backoff.cap_delay`; and
- leave `legacy_backoff.py` byte-for-byte unchanged.

Run the tests before declaring the retry behavior complete.
