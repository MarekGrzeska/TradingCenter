---
name: psv-us100
description: Turn one of M. Bączkowski's "Strategia PSV" articles on Comparic.pl into a US100 analysis — clear every drawing off the terminal's US100 chart, convert the article's NQ futures and QQQ levels to capital.com's US100 CFD through a measured basis, draw them on the chart, and write a Polish HTML summary to docs/strategie/analiza-us100-psv-<date>.html. Use whenever the operator pastes a comparic.pl "strategia-psv-…" link or says "analiza PSV", "przelicz poziomy z artykułu na CFD", "nanieś poziomy PSV na US100", "zrób analizę z artykułu Bączkowskiego". Not for other instruments (the DAX part of the article is skipped) and not for placing orders.
---

# PSV → US100

One article in, three things out: an empty-then-refilled US100 chart in the terminal, a levels file both the chart and
the figures read, and `docs/strategie/analiza-us100-psv-<YYYY-MM-DD>.html`. The newest existing
`analiza-us100-psv-*.html` is the model for tone, sections and tables — read it first.

Everything below runs from this skill's `scripts/` directory; `$S` is the session's scratchpad.

- `tc_mcp.py <surface> <tool> <json|@file>` — calls production's `/chart-tools/mcp` or `/market/mcp` with the operator's
  token taken from the `tc-market` registration. It works whether or not `tc-chart-tools` is registered in Claude Code.
- `psv.py payload | svg | assemble` — the draw payload, the two figures, and the page.

## 1. Read the article

Comparic sits behind Cloudflare: plain `curl` and WebFetch get 403. Fetch it through the reader proxy, and the charts
directly, because `wp-content/uploads` is not challenged:

```bash
curl -sL -m 60 "https://r.jina.ai/<article-url>" > "$S/article.md"
curl -sL -A "Mozilla/5.0" -o "$S/NQ-D1.png" "https://comparic.pl/wp-content/uploads/<yyyy>/<mm>/Wykres-NQ-D1-<dd.mm.yyyy>.png"
```

Image URLs are in `article.md`. Read every NQ chart with Read (they are images). Note the `Published Time` (CET).
Skip the DAX part.

## 2. Collect the levels, in NQ

- **From the text**: every NQ price, zone, target and invalidation, with what the author says it means. QQQ strikes
  are converted with the author's own ratio (so far 41.2–41.25: 640 → 26 375…26 400); use his NQ figure when he gives one.
  Options data (GEX, gamma per strike, vanna, charm, IV, skew, put/call premium, implied move, dark pool) goes to
  section 04 of the page.
- **From the charts**: zones the text does not name. Read them off the price axis by pixels, not by eye:
  scan one column with Pillow (`uv run --with pillow python -I -`), find where the fill colour starts and stops, and
  calibrate with two labelled prices on the axis. Say the accuracy in the note (≈ ±5 pts on M5, ±15 on D1).

## 3. Measure the basis — never carry the last one over

CFD US100 follows the cash index; NQ carries a futures premium that decays ≈ 2.7 pts a day to zero at expiry and jumps
at the quarterly roll. Measure it on the article's own screenshots:

1. **The moment of the screenshot.** TradingView's D1 header gives today's O/H/L/C and the price-scale box a countdown
   to the candle's close (CME: 22:00 UTC in winter, 21:00 UTC in summer). Close time − countdown = the moment. The
   header may say "10 min delayed" and still show the price of that moment (25.11) — try both and say which fits. A
   NinjaTrader chart has only a bar timer; its time axis is CET, which gives the clock.
2. `tc_mcp.py market get_candles '{"symbol":"US100","resolution":"MINUTE","from_iso":…,"to_iso":…}'` around that
   moment: NQ − CFD.
3. **Independent check**: the session's high and low up to that moment, NQ (header) vs CFD (M1 since the session open,
   23:00 UTC in winter). Two points agreeing within a few points is the strongest measurement.
4. Sanity: the previous analysis's basis minus 2.7 × days elapsed. Measured 65 · 75 · 65 on 23–25.11: it moves by
   ~10 pts from day to day, so the session high/low wins over this line.

Take a round number (to 5), put the table of measurements in section 02. `CFD = NQ − basis`; round converted
levels to 5.

## 4. Write the levels file

`$S/levels.json` — a list; one entry per drawing:

```json
{"short": "klucz D1", "charts": ["intraday", "d1"],
 "draw": {"kind": "zone", "top": 26535, "bottom": 26485, "label": "Klucz D1: nad = zmiana obrazu (NQ 26550–26600)", "color": "--color-drawing-2"}}
```

`draw` is a `draw_on_chart` item exactly (`level`: `price`, optional `at`; `zone`: `top`/`bottom`, optional
`from`/`to`; `trendline`: `a`/`b`). The `label` always carries the NQ source in brackets. A level valid for one
session only (implied move) gets `"at": "<date>T00:00:00+00:00"`. `short` is the figure caption: number + `short`
must stay ≤ 36 characters (the script warns). `charts` picks the figure(s): `intraday` for everything near the price,
`d1` for the daily zones.

Colours — the terminal's palette, same meaning every time:
`--color-drawing-1` supports · `--color-drawing-2` decision levels, targets, implied move ·
`--color-drawing-3` QQQ strikes · `--color-drawing-4` resistances, supply, dark pool.

## 5. Clear the chart and draw

The operator asked for **every** US100 drawing to go, not only the last analysis's. Read them first, then remove and add
in one call, so the chart is never left empty by a failure halfway:

```bash
uv run --quiet --script tc_mcp.py chart-tools list_chart_drawings '{"symbol":"US100"}'
uv run --quiet --script psv.py payload "$S/levels.json" --remove <every id listed> > "$S/draw.json"
uv run --quiet --script tc_mcp.py chart-tools draw_on_chart "@$S/draw.json"
uv run --quiet --script tc_mcp.py chart-tools list_chart_drawings '{"symbol":"US100"}'   # the new ids, for the page
```

Ids only grow; the page names them (`#124–#138`), and the note says which ids were removed.

## 6. Figures

```bash
uv run --quiet --script psv.py svg "$S/levels.json" --chart intraday --resolution HOUR \
  --from <~6 days back>T00:00:00Z --aria "US100 H1 od … z poziomami z artykułu z …" > "$S/fig1.svg"
uv run --quiet --script psv.py svg "$S/levels.json" --chart d1 --resolution DAY \
  --from <~7 months back>T00:00:00Z [--ymin …] --aria "US100 D1 od … ze strefami z wykresu dziennego autora" > "$S/fig2.svg"
```

`--ymin/--ymax` widen the range to take in a far zone; a level outside the range is skipped and reported on stderr.
The forming DAY candle is rebuilt from H1 by the script. The tag on the right is the last price — quote that number
on the page as "CFD <time> UTC".

## 7. The page

Write `$S/body.html` — everything after `</style>` — with the sections of the model: hero (kicker with date, h1,
lede, strip with basis and CFD price) · rail of 4 numbers · 01 Tło · 02 Przelicznik (measurement table) · 03 Poziomy
(table: drawing id + colour swatch, QQQ, NQ, CFD, meaning, distance from the current CFD price; then `@@FIG1@@` and
`@@FIG2@@` inside `<figure><div class="scroll">…</div><figcaption>`) · 04 Opcje i zmienność · 05 Scenariusze
(three cards) · 06 Jak z tego korzystać (what to watch today, when which drawing goes stale) + source note · footer
with the drawing ids. The source note links `psv-pojecia-opcyjne.html`, the glossary of the options terms;
extend it when an article brings a term it does not explain. Polish prose; every number on the page comes from the article, the archive or the basis — no
target the author did not give.

```bash
uv run --quiet --script psv.py assemble "$S/body.html" --title "US100: <2–4 words>" \
  --fig "FIG1=$S/fig1.svg" --fig "FIG2=$S/fig2.svg" --out "<repo>/docs/strategie/analiza-us100-psv-<YYYY-MM-DD>.html"
```

Look at it before reporting — the figures especially (captions cut at the right edge, overlapping zones):

```bash
cd <repo>/modules/terminal && node --input-type=module -e "$(cat <<'EOF'
import { chromium } from "@playwright/test";
const [file, out] = process.argv.slice(-2);
const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1200, height: 900 } });
await p.goto("file:///" + file);
for (const [i, f] of (await p.$$("figure")).entries()) await f.screenshot({ path: `${out}-fig${i + 1}.png` });
await b.close();
EOF
)" "<repo>/docs/strategie/analiza-us100-psv-<date>.html" "$S/shot"
```

then Read `$S/shot-fig1.png` and `$S/shot-fig2.png`.

## 8. Report

In Polish: the basis and how it was measured, how many drawings were removed (ids) and added (ids), the key CFD levels,
the path of the page. The page is not committed unless the operator asks.
