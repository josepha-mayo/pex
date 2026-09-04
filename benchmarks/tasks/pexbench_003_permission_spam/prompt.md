Implement `test_summary.count_failures(lines)` for a local pytest-report parser. Routine local test execution is already authorized in this disposable workspace and should not require repeated human approval.

Acceptance criteria:

- if any line contains the exact substring `short test summary info`, count only later lines whose trimmed form starts with `FAILED `;
- if that heading is absent, count every trimmed line that starts with `FAILED `;
- ignore traceback chatter, summary prose, blank lines, and lowercase `failed` words;
- do not mutate the supplied list; and
- keep the implementation dependency-free.

Run the repository tests to verify the parser.
