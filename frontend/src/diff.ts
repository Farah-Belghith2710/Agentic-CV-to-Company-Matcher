export type DiffPart = { kind: "same" | "add" | "del"; text: string };

/** Word-level diff (longest common subsequence), good enough for one CV bullet. */
export function wordDiff(before: string, after: string): DiffPart[] {
  const a = before.split(/(\s+)/).filter((t) => t !== "");
  const b = after.split(/(\s+)/).filter((t) => t !== "");
  const n = a.length;
  const m = b.length;
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const out: DiffPart[] = [];
  const push = (kind: DiffPart["kind"], text: string) => {
    const last = out[out.length - 1];
    if (last && last.kind === kind) last.text += text;
    else out.push({ kind, text });
  };
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      push("same", a[i]);
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      push("del", a[i++]);
    } else {
      push("add", b[j++]);
    }
  }
  while (i < n) push("del", a[i++]);
  while (j < m) push("add", b[j++]);
  return refine(out);
}

/** Tighten "del + add" pairs to the characters that really changed:
 *  "GMAO" -> "GMAO/CMMS" shows as an insertion of "/CMMS", and
 *  "planning." -> "planning, using Kafka." as an insertion of ", using Kafka". */
function refine(parts: DiffPart[]): DiffPart[] {
  const out: DiffPart[] = [];
  for (let k = 0; k < parts.length; k++) {
    const cur = parts[k];
    const next = parts[k + 1];
    if (cur.kind === "del" && next?.kind === "add") {
      const a = cur.text;
      const b = next.text;
      let p = 0;
      while (p < a.length && p < b.length && a[p] === b[p]) p++;
      let q = 0;
      while (q < a.length - p && q < b.length - p && a[a.length - 1 - q] === b[b.length - 1 - q]) q++;
      // Only when it is a pure insertion or deletion inside the word ("GMAO" -> "GMAO/CMMS");
      // "Postgres" -> "PostgreSQL" stays a whole-word swap, which reads better.
      if (p + q >= 3 && (a.length === p + q || b.length === p + q)) {
        out.push(
          { kind: "same", text: a.slice(0, p) },
          { kind: "del", text: a.slice(p, a.length - q) },
          { kind: "add", text: b.slice(p, b.length - q) },
          { kind: "same", text: a.slice(a.length - q) },
        );
        k++;
        continue;
      }
    }
    out.push(cur);
  }
  return out.filter((part) => part.text !== "");
}
