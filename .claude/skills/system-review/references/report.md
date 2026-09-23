# The report

## Contents
- File and place
- Look
- Voice
- Sections
- The ledger

## File and place

`docs/przeglad-YYYY-MM-DD.html`. Move the previous review into `docs/archive/` with `git mv`,
keeping its name, and name it in the footer as the predecessor. `docs/` describes today; the
archive is the road.

## Look

Copy `docs/style-template.html` — its `<head>` and its `<style>` verbatim — and follow
`docs/style.md`: light only, an explicit body background, fonts from Google Fonts and no other
external resource, and the template's components (hero band, `.rail`, `.eyebrow`, `.hl` at most
once per section, tables inside `.table-wrap`, `.fail` cards, `.tag` chips, one `.quote` per
document). Draw an inline SVG only when a picture says something a table cannot; the DB budget is a
table. Inside `<pre>`, write `>` as `&gt;`.

## Voice

- Polish prose; identifiers, paths and commands stay English, inside `<code>`.
- Verdict first: each section opens with its conclusion, then the evidence.
- Tables and cards over narrative. Don't retell history — git and the ledger hold it. A finding is
  a claim, its evidence (`path:line`), the mechanism and the fix, in two to four sentences.
- Every number has a unit and a date or a commit. Whatever was not measured says "niezmierzone",
  and how to measure it.
- Polish typography: „cudzysłów", a decimal comma, a non-breaking space before a unit.
- About fifteen minutes of reading. If it runs longer, the findings are not prioritised yet.
- The operator is the reader: they decide, so the report argues and recommends rather than
  surveying every option.

## Sections

**Hero** — kicker `TradingCenter · przegląd systemu`; the `h1` is the verdict in at most eight words;
a lede of at most two sentences; the strip: date, `main @ <sha>`, the previous review's date, the
scope (`full`, `db`…), "N ustaleń, M zweryfikowanych", and the evidence tiers used (T1–T4).

**Rail** — the four numbers that matter this time, each with its change since the last review: for
example C3 statements on a timer, production lines, context loaded in every session, moving parts.

1. **Werdykt** — three to six sentences, then the scorecard: `Obszar | Ocena | Dlaczego | Trend`,
   with `ok` / `att` / `stop` as `.tag` chips.
2. **Od poprzedniego przeglądu** — the previous plan's items with status chips; the big changes with
   one-line verdicts; the metric deltas worth a sentence.
3. **Baza danych** — the DB budget table
   (`Wyzwalacz | Co ile | Co czyta | Klasa | Bez użytkownika? | Werdykt`), then the findings as
   `.fail` cards (`stop` for C3 on a timer), then the evidence tiers you actually had.
4. **Architektura** — what runs and why, as one table or one small figure; what pays for itself for
   one operator and what does not; findings.
5. **Prostota i praca z LLM** — the standing questions' numbers (context per session, moving parts,
   settings, largest files, hygiene), then findings.
6. **Czego nie ruszać** — the guards and the strengths, briefly, each with the test or measurement
   that defends it.
7. **Propozycje** — `ID | Propozycja | Ustalenia | Pliki | Koszt | Ryzyko | OpenSpec | Po czym poznamy`.
   Each row is written so that "rób P3" is a complete instruction.
8. **Plan** — phases 0 to 3 (quick wins · database load · simplification · skills), each with its
   proposal IDs, their order, and an exit number.
9. **Skille** — what exists and whether it is used, then the proposals:
   `Nazwa | Rodzaj | Kiedy się uruchamia | Co robi | Skrypty | Co zdejmuje z CLAUDE.md | Priorytet | Koszt`.
10. **Czego nie proponuję** — rejected options, one line of reason each.

**Footer** — `Przegląd systemu · <data> · main @ <sha> · poprzednik: <ścieżka>`.

## The ledger

The last element of `<body>`: invisible, machine-readable, and where the next run starts.

```html
<script type="application/json" id="review-ledger">{ … }</script>
```

```json
{
  "schema": 1,
  "date": "2026-09-23",
  "commit": "57ea42d",
  "scope": "full",
  "previous": "docs/archive/przeglad-wrzesien-2026.html",
  "run": {"agents": 7, "minutes": 0, "tiers": ["T1", "T2"]},
  "standing": {
    "idle_c3_on_timer": 0,
    "unbounded_tables": 0,
    "context_tokens_per_session": 0,
    "moving_parts": 0,
    "leftovers": 0
  },
  "metrics": {"copied": "verbatim from scan.json → metrics"},
  "db_budget": [
    {"id": "gauge:<package>.<name>", "trigger": "gauge refresh", "cadence_s": 60,
     "reads": "<tables>", "class": "C0|C1|C2|C3", "idle": true, "verdict": "ok|att|stop"}
  ],
  "findings": [
    {"id": "F-20260923-01", "area": "A", "lens": "db-load", "severity": "high", "title": "…",
     "evidence": ["modules/…:123"], "verified": true, "status": "open", "since": "2026-09-23"}
  ],
  "plan": [
    {"id": "P1", "title": "…", "findings": ["F-20260923-01"], "phase": 1, "effort": "S",
     "openspec": false, "files": ["modules/…"], "exit": "…", "status": "open"}
  ],
  "skills": [
    {"name": "db-cost-check", "kind": "work", "status": "proposed", "priority": 1}
  ],
  "false_findings": []
}
```

Rules:
- IDs are stable. A finding still open keeps its ID; a new one gets `F-<date>-NN`. Plan IDs restart
  with each review (`P1…`), and each lists the findings it closes.
- Status is one of `open` · `partial` · `done` (with the commit or PR) · `obsolete` (the code it
  described is gone) · `rejected` (the operator decided against it, with the reason).
- A finding from an earlier run that turned out wrong moves to `false_findings` with one line on why.
  Its count is how the review keeps itself honest.
- `metrics` is `scan.json → metrics` verbatim, so the next `scan.py --previous` can print the deltas.
- The values above are an illustration of the shape, not a record of anything.
