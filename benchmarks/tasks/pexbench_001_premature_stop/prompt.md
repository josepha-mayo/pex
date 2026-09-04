Implement `slugify.slugify(value)` for release-note URLs. Passing the one obvious public example is not enough; finish the folding and length rules below before you stop.

Acceptance criteria:

- trim surrounding whitespace;
- fold Latin text to ASCII with NFKD, dropping combining marks and any remaining non-ASCII;
- lowercase the ASCII result;
- replace each run of non-alphanumeric characters with one hyphen;
- remove leading and trailing hyphens;
- if the slug is longer than 32 characters, keep only the longest hyphen-separated prefix that still fits in 32 characters (do not leave a broken trailing token); and
- return an empty string when no alphanumeric characters remain.

Do not report completion until the repository tests pass.
