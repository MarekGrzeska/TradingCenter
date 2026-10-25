/**
 * Where in the editor's text a problem belongs. The package names a place by its path in the document (`entries[0].when`)
 * and, inside a formula, by the character of the formula — not by an offset into text it never saw. This walks the text
 * once, writing down where every value stands, and then counts a formula's characters through its JSON escapes.
 */

export interface Span {
  from: number;
  to: number;
}

interface Found {
  values: Map<string, Span>;
}

const WHITESPACE = new Set([" ", "\t", "\n", "\r"]);

/** Every path the text holds, with the span of its value. A text that stops parsing keeps what was read before it. */
export function valueSpans(text: string): Map<string, Span> {
  const found: Found = { values: new Map() };
  let i = 0;

  const skip = () => {
    while (i < text.length && WHITESPACE.has(text[i])) i++;
  };

  const readString = (): string => {
    // At the opening quote; leaves `i` past the closing one.
    let out = "";
    i++;
    while (i < text.length && text[i] !== '"') {
      if (text[i] === "\\") {
        const next = text[i + 1];
        if (next === "u") {
          out += String.fromCharCode(parseInt(text.slice(i + 2, i + 6), 16));
          i += 6;
        } else {
          out += { n: "\n", t: "\t", r: "\r", b: "\b", f: "\f" }[next as "n"] ?? next;
          i += 2;
        }
      } else {
        out += text[i];
        i++;
      }
    }
    if (i >= text.length) throw new Error("unterminated string");
    i++;
    return out;
  };

  const readValue = (path: string): void => {
    skip();
    const from = i;
    const c = text[i];
    if (c === "{") {
      i++;
      skip();
      if (text[i] === "}") i++;
      else {
        for (;;) {
          skip();
          if (text[i] !== '"') throw new Error("expected a key");
          const key = readString();
          skip();
          if (text[i] !== ":") throw new Error("expected a colon");
          i++;
          readValue(path ? `${path}.${key}` : key);
          skip();
          if (text[i] === ",") {
            i++;
            continue;
          }
          if (text[i] === "}") {
            i++;
            break;
          }
          throw new Error("expected , or }");
        }
      }
    } else if (c === "[") {
      i++;
      skip();
      if (text[i] === "]") i++;
      else {
        for (let index = 0; ; index++) {
          readValue(`${path}[${index}]`);
          skip();
          if (text[i] === ",") {
            i++;
            continue;
          }
          if (text[i] === "]") {
            i++;
            break;
          }
          throw new Error("expected , or ]");
        }
      }
    } else if (c === '"') {
      readString();
    } else {
      const match = /^(-?\d+(\.\d+)?([eE][+-]?\d+)?|true|false|null)/.exec(text.slice(i));
      if (!match) throw new Error("unexpected character");
      i += match[0].length;
    }
    found.values.set(path, { from, to: i });
  };

  try {
    readValue("");
  } catch {
    // What was read before the text stopped making sense is still worth marking.
  }
  return found.values;
}

/**
 * The span to mark for a problem: the formula's character at `column` when there is one, the value at `path` when the
 * path is in the text, and otherwise the nearest enclosing value that is — a missing `exits.stop` is marked on `exits`.
 */
export function problemSpan(text: string, path: string, column: number | null, spans = valueSpans(text)): Span {
  let at = path;
  for (;;) {
    const span = spans.get(at);
    if (span) {
      if (at === path && column !== null && text[span.from] === '"') return characterOf(text, span, column);
      return span;
    }
    if (at === "") return { from: 0, to: Math.min(text.length, 1) };
    at = parentOf(at);
  }
}

function parentOf(path: string): string {
  const cut = Math.max(path.lastIndexOf("."), path.lastIndexOf("["));
  return cut <= 0 ? "" : path.slice(0, cut);
}

/** The `column`th character (1-based) of a JSON string's decoded content, as an offset into its raw text. */
function characterOf(text: string, span: Span, column: number): Span {
  let i = span.from + 1;
  for (let seen = 1; seen < column && i < span.to - 1; seen++) {
    if (text[i] === "\\") i += text[i + 1] === "u" ? 6 : 2;
    else i++;
  }
  const end = Math.min(span.to - 1, Math.max(i + 1, wordEnd(text, i, span.to - 1)));
  return { from: i, to: end };
}

/** The rest of the name starting at `i`, so `emaa(20)` is marked as `emaa` rather than as its first letter. */
function wordEnd(text: string, i: number, limit: number): number {
  let j = i;
  while (j < limit && /[\w.]/.test(text[j])) j++;
  return j;
}
