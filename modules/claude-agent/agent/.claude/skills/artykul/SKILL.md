---
name: artykul
description: An article, report or overview for the operator as one HTML file in the house style, sent on Telegram. Use whenever the answer is longer than a few phone messages — "napisz artykuł", "raport", "przegląd tematu", "zrób dokument", "wyślij jako plik".
---

# Artykuł

1. Gather first: the `tc-*` tools for anything the system holds (prices from `tc-market`, with the time you read them),
   the web for the rest. Two to four sources are enough; note each address, publisher and date.
2. `Read` `.claude/skills/artykul/template.html` once. It is the whole style: copy its `<head>` — the font link and the
   `<style>` block — **verbatim**. Do not restyle, add CSS, scripts or images; that is where the tokens go.
3. Fill the `<body>` from the template's pieces, Polish, for a phone:
   - `header`: `.kick` a category in two or three words, `h1` the title, `.lede` one or two sentences with the key
     number in `<b>`, `.strip` the date, the number of sources, "agent TradingCenter".
   - `.rail`: two to four numbers that carry the piece (`.v` the number, `.l` what it is). Leave it out when there are none.
   - `section`s, each with `.eye` (`01 · Nazwa`), `h2`, `p.intro`, then `p`, `ul`, `.hl` for the one sentence that matters.
   - `.tw > table` for comparisons (`.n` on number cells), `.box` (`.ok`, `.stop`) for scenarios or risks with a `.tag`,
     one `.quote` at most.
   - The last section is always **Źródła**: `ol.src` with a link per source — title, publisher, date. Say there which
     numbers you could not confirm.
   - `footer`: the date.
4. One `Write` to `/home/agent/work/out/<kebab-name>-<YYYY-MM-DD>.html` — the whole file at once, no edits afterwards.
5. Telegram reply with `files: ["/home/agent/work/out/<name>.html"]` and two sentences: the conclusion and the one
   number that matters. No tables or headings in the message itself.

Length: what the question needs, usually 600–1200 words. Every number either comes from a source listed at the end or
from a tool read in this conversation; anything else is an estimate and says so.
