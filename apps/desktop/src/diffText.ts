export type DiffLineType = "same" | "add" | "del";

export interface DiffLine {
  type: DiffLineType;
  text: string;
}

export const DIFF_MAX_LINES = 400;

function splitLines(text: string): string[] {
  if (text === "") return [];
  const lines = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

/** A bounded LCS line diff — evidence is small, so no streaming needed. */
export function unifiedDiff(baseline: string, current: string): DiffLine[] {
  const a = splitLines(baseline).slice(0, DIFF_MAX_LINES);
  const b = splitLines(current).slice(0, DIFF_MAX_LINES);
  const rows = a.length;
  const cols = b.length;
  const table = new Uint32Array((rows + 1) * (cols + 1));
  const stride = cols + 1;
  for (let i = rows - 1; i >= 0; i -= 1) {
    for (let j = cols - 1; j >= 0; j -= 1) {
      table[i * stride + j] =
        a[i] === b[j]
          ? table[(i + 1) * stride + j + 1] + 1
          : Math.max(table[(i + 1) * stride + j], table[i * stride + j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < rows && j < cols) {
    if (a[i] === b[j]) {
      out.push({ type: "same", text: a[i] });
      i += 1;
      j += 1;
    } else if (table[(i + 1) * stride + j] >= table[i * stride + j + 1]) {
      out.push({ type: "del", text: a[i] });
      i += 1;
    } else {
      out.push({ type: "add", text: b[j] });
      j += 1;
    }
  }
  for (; i < rows; i += 1) out.push({ type: "del", text: a[i] });
  for (; j < cols; j += 1) out.push({ type: "add", text: b[j] });
  return out;
}
