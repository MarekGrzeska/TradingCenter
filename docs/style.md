# Document style

Every `docs/*.html` in this repository is a standalone page with its own `<style>` block —
there is no shared stylesheet, and there cannot be one: these pages are also published as
artifacts, where a strict CSP blocks every external host except Google Fonts, and a relative
`href` to a repo file resolves to nothing. So the system is written down here and pasted in,
rather than linked.

Before this file existed, the pages drifted into a house style nobody had chosen: nine out of
nine shared the same token names, the same `prefers-color-scheme` block and the same
`system-ui` stack, because each was written by copying the last one. Different accent hues,
identical bones. This file replaces that inheritance with a decision.

`docs/style-template.html` is the reference implementation — every component below appears in
it once, with real content. Start a new document by copying it.

## The two rules that are not taste

**Light only.** No `@media (prefers-color-scheme: dark)`, no `:root[data-theme="dark"]`. A
page carrying both themes renders dark for a reader whose system is dark, which is not what
these documents are for. Paint `body` with an explicit background — a transparent body borrows
whatever ground the host paints, and that is how a light page arrives dark.

**Self-contained.** All CSS inline in one `<style>`. No external stylesheet, no CDN script, no
remote image. Fonts come from `fonts.googleapis.com` — the one host the artifact CSP admits —
and every family still declares a real fallback stack.

## Colour

Navy carries the identity, yellow is the single accent, and the semantic three are for state
only — never for decoration.

| Token | Value | Used for |
|---|---|---|
| `--paper` | `#fcfbf7` | page ground, warm off-white |
| `--card` | `#ffffff` | figures, tables, cards sitting on the ground |
| `--navy` / `--band` | `#14306b` | header band, table head, code block, emphasis |
| `--yellow` | `#f2c313` | the accent: eyebrow rules, marker, pull quote, figure underline |
| `--yellow-soft` | `#fdf3d0` | the `.hl` marker fill behind running text |
| `--ink` | `#16181d` | headings and bold text |
| `--ink-2` | `#4f535e` | running text |
| `--ink-3` | `#85899a` | captions, metadata, muted rows |
| `--line` / `--line-soft` | `#ddd9cd` / `#ebe8de` | borders, row rules |
| `--green` / `--green-soft` | `#17734c` / `#e0f0e8` | state: healthy |
| `--red` / `--red-soft` | `#b8322a` / `#fae7e4` | state: refused, dead, broken |
| `--navy-soft` | `#e6ebf5` | inline `code` ground |

Yellow on white fails contrast for text; it is a ground and a rule, never a foreground. Where
a yellow field carries words, the words are navy (`--band`), as in the hero kicker and the
pull quote.

## Type

```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700;12..96,800&family=Karla:wght@400;500;700&family=Roboto+Mono:wght@400;700&display=swap">
```

- `--head` — **Bricolage Grotesque**, 700/800, `letter-spacing: -0.028em`. Headings only.
  `h1` runs `clamp(38px, 6.6vw, 76px)` in the band; `h2` runs `clamp(26px, 3.6vw, 38px)`.
- `--body` — **Karla**, 16.5px/1.64. Running text caps at `68ch`; the lead paragraph
  (`p.intro`) runs 18.5px and caps at `60ch`.
- `--mono` — **Roboto Mono**. Code, ports, numbers, eyebrows, captions' figure numbers, every
  uppercase label. Anything tabular also takes `font-variant-numeric: tabular-nums`.

Fallback stacks are `system-ui, sans-serif` for both text faces and `ui-monospace, monospace`
for the third.

## Components

Each of these exists in the template; take it from there rather than rebuilding it.

- **Hero band** — full-bleed `--band`, yellow kicker chip, `h1` capped at `17ch`, lede at
  `56ch`, then a `.strip` of monospace metadata over a hairline. The band is the only place
  white text appears.
- **`.rail`** — the four-number strip, pulled up `-30px` so it overlaps the band's lower edge.
  Numbers in `--head` 800 at 40px, navy; labels 13px, `--ink-3`.
- **`.eyebrow`** — `NN · Name` in monospace, with a 3px yellow rule filling the rest of the
  line via `::after`. This is what separates sections; there are no horizontal rules elsewhere.
- **`.hl`** — the marker. `linear-gradient(transparent 58%, var(--yellow-soft) 58%)` with
  `box-decoration-break: clone` so it survives a line wrap. One phrase per section at most:
  the sentence the reader would underline, not every claim.
- **Tables** — navy head row, white body, `.table-wrap` with `overflow-x: auto` and
  `min-width` on the table. A refused or dead row takes `tr.void`.
- **`pre`** — navy ground, `#e7ecf8` text, yellow keywords, `#8fd6b0` strings, `#8f9ec4`
  comments. Escape `>` as `&gt;` inside; a raw one closes nothing but reads as broken markup.
- **`.quote`** — solid yellow field, navy text, `--head` 700, capped at `30ch`. One per
  document. It carries the sentence the document exists to make.
- **`.fail`** — the state cards: white, thin border, 6px left edge in yellow, or `--red` /
  `--green` for the two extremes.
- **`.tag`** — the state chips, monospace 10px uppercase, in the three semantic pairs.

## Figures

Diagrams are hand-authored inline `<svg>` — no library, no runtime, no image file. The rules
that keep them legible:

- Size by `viewBox`; let CSS scale (`width: 100%; height: auto`). Wrap in `.scroll` so a wide
  drawing scrolls inside its own box and the page body never scrolls sideways.
- Strokes and text in `currentColor`, which inherits `--ink-2`. Spend a literal hue on the one
  element the figure is about: `#14306b` for the box under discussion, `#f2c313` for the label
  that names what happens there.
- Label every arrow. `POST /chat`, `REST + klucz`, `sesja demo` — never a bare line.
- `role="img"` plus an `aria-label` carrying the same claim as the caption.
- `figcaption` states what the picture shows, opening with `<b>Rys. N</b>` in monospace.

## Language

The pages themselves are **Polish prose** — they are written for the operator. This file, the
class names, the comments and the commit messages stay **English**, like the rest of the
repository outside `openspec/`.
