Complete `csv_utils.parse_csv(text)` for production exports. Splitting on commas, or calling `csv.reader` on the raw string, is not enough.

Acceptance criteria:

- return a list of rows, where every row is a list of strings;
- honor quoted commas and escaped double quotes;
- accept `\n` and `\r\n` input;
- strip a leading UTF-8 BOM;
- skip whole lines whose first non-whitespace character is `#`;
- return an empty list for empty input; and
- do not treat a quoted field that merely begins with `#` as a comment.

Only call the work complete after the tests, including the quoted-field cases, pass.
