import { useEffect, useRef } from "react";
import { autocompletion, type CompletionContext, type CompletionResult } from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { json, jsonParseLinter } from "@codemirror/lang-json";
import { bracketMatching, syntaxTree } from "@codemirror/language";
import { forceLinting, linter, lintGutter, type Diagnostic } from "@codemirror/lint";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { offersAfterAt, offersForKeys, offersInFormula, type Offer } from "./completions";
import { problemSpan, valueSpans } from "./jsonPaths";
import type { Language, Problem } from "./strategiesApi";

/**
 * The document as text, in the form it is stored and hashed (design D9). The JSON's syntax is checked here at once; what
 * the package says about the document arrives with the text it was said about, and is shown only while that is still the
 * text — a problem pointing into a line since rewritten would point at the wrong thing.
 */

export interface Checked {
  text: string;
  problems: Problem[];
}

const THEME = EditorView.theme(
  {
    "&": { height: "100%", fontSize: "12px", backgroundColor: "var(--color-sunken)", color: "var(--color-ink)" },
    ".cm-content": { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", caretColor: "var(--color-primary)" },
    ".cm-gutters": { backgroundColor: "var(--color-panel)", color: "var(--color-ink-faint)", border: "none" },
    ".cm-activeLine": { backgroundColor: "var(--color-panel)" },
    ".cm-tooltip": { backgroundColor: "var(--color-raised)", color: "var(--color-ink)", border: "none" },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": { backgroundColor: "var(--color-primary-soft)" },
  },
  { dark: true },
);

const parseJson = jsonParseLinter();

function asCompletions(offers: Offer[], from: number): CompletionResult {
  return { from, options: offers.map((o) => ({ label: o.label, detail: o.detail, type: o.kind })) };
}

export function StrategyEditor({
  text,
  onChange,
  checked,
  language,
  symbols,
}: {
  text: string;
  onChange(text: string): void;
  checked: Checked | null;
  language: Language | null;
  symbols: readonly string[];
}) {
  const host = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  // Read by the editor's own callbacks, which are built once.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const checkedRef = useRef(checked);
  checkedRef.current = checked;
  const languageRef = useRef(language);
  languageRef.current = language;
  const symbolsRef = useRef(symbols);
  symbolsRef.current = symbols;

  useEffect(() => {
    if (!host.current) return;

    const diagnose = (view: EditorView): Diagnostic[] => {
      const current = view.state.doc.toString();
      const syntax = parseJson(view);
      if (syntax.length > 0) return syntax;
      const said = checkedRef.current;
      if (said === null || said.text !== current) return [];
      const spans = valueSpans(current);
      return said.problems.map((p) => {
        const span = problemSpan(current, p.path, p.column, spans);
        return {
          from: span.from,
          to: Math.max(span.to, span.from + 1),
          severity: "error" as const,
          message: `${p.path}: ${p.message}${p.hint ? ` — ${p.hint}` : ""}`,
        };
      });
    };

    const complete = (context: CompletionContext): CompletionResult | null => {
      const known = languageRef.current;
      if (known === null) return null;
      const word = context.matchBefore(/[\w.]*/);
      if (word === null || (word.from === word.to && !context.explicit)) return null;
      const node = syntaxTree(context.state).resolveInner(context.pos, -1);
      if (node.name === "PropertyName") return asCompletions(offersForKeys(known), word.from + 1);
      if (node.name !== "String") return null;
      const before = context.state.sliceDoc(node.from, word.from).trimEnd();
      if (before.endsWith("@")) return asCompletions(offersAfterAt(known, symbolsRef.current), word.from);
      let document: unknown = null;
      try {
        document = JSON.parse(context.state.doc.toString());
      } catch {
        // A document mid-edit still has the language's names to offer; only its own `let` and `params` wait.
      }
      return asCompletions(offersInFormula(known, document), word.from);
    };

    const view = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: text,
        extensions: [
          lineNumbers(),
          history(),
          bracketMatching(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          json(),
          lintGutter(),
          linter(diagnose, { delay: 150 }),
          autocompletion({ override: [complete] }),
          EditorView.lineWrapping,
          THEME,
          EditorView.updateListener.of((update) => {
            if (update.docChanged) onChangeRef.current(update.state.doc.toString());
          }),
        ],
      }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // Built once; `text` from outside is applied by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A revision loaded from outside — another strategy opened, the agent's revision taken — replaces the text.
  useEffect(() => {
    const view = viewRef.current;
    if (!view || view.state.doc.toString() === text) return;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } });
  }, [text]);

  useEffect(() => {
    if (viewRef.current) forceLinting(viewRef.current);
  }, [checked]);

  return <div ref={host} className="h-full min-h-0 overflow-hidden rounded border border-border" aria-label="Dokument strategii" />;
}
