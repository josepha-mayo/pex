# Wirepool clean-room repair benchmark

Read TASK.md. Repair the package across its codec, connection, pool, and client
boundaries. Run `python -m unittest discover -s tests -v`.

Requires Python 3.11+ standard library only. No network/server/package installs.
Transport doubles in tests are authored models, not the redis-py implementation.
Primary motivation: https://github.com/redis/redis-py/issues/2665 and
https://github.com/redis/redis-py/issues/2624 . The task extends that failure mode
with explicitly specified codec/pool/pipeline obligations; it is not a claim to
reproduce the full production package or its exact historical implementation.
