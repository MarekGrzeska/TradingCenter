## Verdict

Wybór naniesionego obiektu wprost na wykresie jest zaimplementowany w całości: trafianie
liczone przez `hitTest` w tym samym prymitywie, który obiekt rysuje, stan zaznaczenia
w `Chart`, karta z opisem i obiema operacjami obok klikniętego miejsca, oraz jedno
zaznaczenie wspólne z listą w nagłówku. Do tego wygląd: 2 px ciągłe wobec 1 px
kreskowanego, podpis na wypełnionym chipie zamiast gołego tekstu, etykieta ceny przy osi
kolorowana rolą, i własna paleta rysunków przypisywana po identyfikatorze.

Paleta rysunków ma **cztery** barwy, nie osiem. To nie jest niedokończone: kolor rysunku
jest funkcją jego identyfikatora, więc dowolne dwa mogą stanąć obok siebie — czyli listą
par do sprawdzenia jest `--pairs all`, a nie sąsiedztwo. Cztery to miejsce, w którym ta
lista jeszcze przechodzi wszystkie bramki walidatora na tym tle (najgorsza para CVD
ΔE 8.1, normal-vision 16.3); piąta barwa oblała je w każdym wariancie, który próbowano.
Pomiary stoją w `terminal/src/index.css`, przy tokenach.

Ręczne przejście na żywym stacku (task 8.3) **nie zostało wykonane** — wymaga Dockera,
sesji Capital i klucza OpenAI, i jest czynnością operatora. Patrz Gaps.

## Verified

- `modules/terminal`: `pnpm test` (vitest run) — **723 passed** w 48 plikach.
- `modules/terminal`: `pnpm lint` (eslint .) — bez zastrzeżeń.
- `modules/terminal`: `pnpm typecheck` (tsc -b --noEmit) — bez błędów.
- `modules/terminal`: `pnpm contract:check` — „Contract is up to date" (`market_data/contract.py`
  nietknięty, więc `contract:generate` niepotrzebny).
- `modules/terminal`: `tsc -b && vite build` — zbudowane, 960 kB bundle (ostrzeżenie
  o rozmiarze jest sprzed tej zmiany); `dist/` skasowane po sprawdzeniu.
- `modules/agent`: `uv run pytest` — **293 passed**, 2 warnings (nieistotne, `httpx`/`pydantic-settings`).
- `modules/agent`: `uv run pytest -m db` — **191 passed**, 102 deselected. Migracja `0008`
  zastosowała się w kontenerze; `test_migration_seeds_the_current_text` czyta z niej `v8`.
- `modules/agent`: `uv run ruff check .` — All checks passed.
- `modules/agent`: `uv run pyright` — 0 errors, 0 warnings, 0 informations.
- `openspec validate terminal-chart-object-selection --strict` — valid.
- Paleta: `node scripts/validate_palette.js "#009fb4,#8f5ada,#7f9422,#d14f72" --mode dark
  --surface "#12151d" --pairs all` — ALL CHECKS PASS. Ta sama komenda na palecie
  wskaźnikowej (tło tego terminala, sąsiedztwo) też przechodzi — obie były sprawdzane,
  nie tylko nowa.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Low | `ZonePrimitive.ts:100` | Strefa jako jedyny z trzech kształtów nie dostawała otoczki po zaznaczeniu — miała samą grubszą ramkę. Task 5.4 mówi „grubiej **i** z otoczką", a operator porównujący zaznaczoną strefę z zaznaczonym poziomem widziałby dwa różne sposoby mówienia tego samego. | FIXED przed napisaniem tego dokumentu (w tym samym zestawie zmian) |
| Info | `Chart.tsx` — efekt rysunków | `setLevels`/`setZones`/`setLines` przebudowują tablicę `priceAxisViews`, a biblioteka cache'uje ją po referencji. Efekt chodzi tylko przy zmianie referencji `drawings.items`, więc przebudowa jest rzadka — ale gdyby sklep zaczął oddawać nową tablicę na każdy render, cache przestałby działać. Zachowanie sprzed zmiany było takie samo dla `setLevels`, więc to nie regres, tylko rzecz do zapamiętania. | Otwarte, świadomie |

Poza tym: bez znalezisk. Rzeczy sprawdzone i uznane za poprawne, żeby nie sprawdzać ich
drugi raz: przestrzeń współrzędnych `hitTest` (media, ta sama co `priceToCoordinate` —
własny `SeriesLineHitTest` biblioteki liczy w niej `itemY ± lineWidth ± 7`, stąd
tolerancja 5 px tutaj); wybór dokładnie jednego obiektu przy nakładaniu (biblioteka
zwraca `bestPrimitiveHit` po `zOrder`, a `Chart` bierze jedno `hoveredObjectId`);
kolejność efektów (prymitywy powstają przed nadaniem im wyrazistości, bo efekt rysunków
stoi w pliku wyżej).

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **terminal-chart-objects — Operator wskazuje obiekt na wykresie** | |
| Kliknięcie w poziom | `Chart.test.tsx::picks out the object clicked, and says what it is beside it`; `RayPrimitive.test.ts::answers with the drawing's own id, and asks for a pointer` |
| Kliknięcie obok linii, w granicach tolerancji | `RayPrimitive.test.ts::counts a click a few pixels off the line as a click into it`; `RayPrimitive.test.ts::does not answer for a click further away than the tolerance` |
| Najechanie na obiekt | `RayPrimitive.test.ts::answers with the drawing's own id, and asks for a pointer` (`cursorStyle: "pointer"` — patrz Gaps) |
| Kliknięcie w puste miejsce | `Chart.test.tsx::puts the selection down on a click into empty space` |
| Kliknięcie w linię trendu i w strefę | `TrendlinePrimitive.test.ts::is clicked on the segment, and near it, but not past its ends`; `ZonePrimitive.test.ts::is clicked anywhere inside its own rectangle, and nowhere outside it`; `ZonePrimitive.test.ts::is clicked to the right edge while it is still open` |
| (klikalne są rysunki, nie wskaźniki) | `RayPrimitive.test.ts::never answers for an indicator's own level`; `ZonePrimitive.test.ts::never answers for an indicator's own zone`; `TrendlinePrimitive.test.ts::never answers for a primitive with no object behind it` |
| **terminal-chart-objects — Wskazany obiekt widać, że jest wskazany** | |
| Obiekt zostaje wskazany | `ZonePrimitive.test.ts::draws the picked band with a wash around it, and the rest faded` |
| Odznaczenie klawiszem | `Chart.test.tsx::puts the selection down on Escape` |
| Wskazanie nie jest zmianą obiektu | `Chart.test.tsx::picking an object out is not a change to it` |
| Zmiana symbolu przy wskazanym obiekcie | `Chart.test.tsx::carries no selection across a symbol change` |
| **terminal-chart-objects — Wskazany obiekt mówi, czym jest** | |
| Opis wskazanego obiektu | `Chart.test.tsx::picks out the object clicked, and says what it is beside it`; `DrawingCard.test.tsx::describes a level: its shape, its price, its caption and when it was drawn`; `…describes a zone by both its prices`; `…describes a trend line by both its ends` |
| Poprawienie z opisu | `DrawingCard.test.tsx::corrects a price the same way the list does, sending only what moved` (drugie **AND** — lista pokazuje tę samą cenę — wynika z konstrukcji: karta i lista renderują z jednego `ChartDrawings.items`, przez ten sam `DrawingEditor`) |
| Usunięcie z opisu | `DrawingCard.test.tsx::removes the object through the same call the list makes`; `Chart.test.tsx::lets go of an object that stops being there` |
| Nieudane poprawienie z opisu | `DrawingCard.test.tsx::says a correction failed and leaves the object as it was`; `DrawingCard.test.tsx::says a removal failed and keeps the object described` |
| **terminal-chart-objects — Wskazanie jest jedno, wspólne z listą** | |
| Z wykresu na listę | `Chart.test.tsx::shows the object picked on the chart marked out on the list too`; `DrawingList.test.tsx::marks out the row of the object picked elsewhere` |
| Z listy na wykres | `Chart.test.tsx::picks out on the chart what was chosen from the list`; `DrawingList.test.tsx::reports a row picked here rather than keeping it` |
| Odznaczenie sięga obu | `Chart.test.tsx::puts the selection down on Escape`; `DrawingList.test.tsx::nothing is marked out when nothing is picked` |
| **terminal-chart — Wykres rysuje obiekty naniesione na instrument** | |
| Poziom po zmianie interwału | `Chart.test.tsx::keeps the objects through a resolution change` |
| Linia trendu między dwoma punktami | `TrendlinePrimitive.test.ts::draws a segment between its two points and stops there` |
| Naniesiony poziom obok policzonego | `RayPrimitive.test.ts::draws an operator's level heavier and unbroken, an indicator's thin and dashed`; `ZonePrimitive.test.ts::outlines the band it draws, where an indicator's stays a bare wash`; `TrendlinePrimitive.test.ts::draws an operator's line heavier and unbroken` |
| Etykieta ceny przy osi | `RayPrimitive.test.ts::says the price, coloured by the side of the market it sits on`; `ZonePrimitive.test.ts::says both of its prices at the axis, each coloured by its own side`; `TrendlinePrimitive.test.ts::says both of its ends at the axis`; `RayPrimitive.test.ts::takes the line's own colour when the chart has drawn no candle yet` |
| Obiekt zaczynający się poza widokiem | `RayPrimitive.test.ts::keeps the caption on screen for a level starting off the left edge`; `RayPrimitive.test.ts::draws a segment from the level's own x to the right edge, not the whole width` (chip pod podpisem) |
| Kolor obiektu po usunięciu innego | `theme.test.ts::gives one id one colour, whatever else is on the chart`; `theme.test.ts::gives objects drawn one after another different colours` |
| Zmiana symbolu | `Chart.test.tsx::replaces them when the symbol changes` |
| Nieudany odczyt obiektów | `DrawingList.test.tsx::a failed read says so, and does not read as an empty instrument`; `DrawingList.test.tsx::a failed read keeps showing what was already there` |
| **agent-chart-drawings — Rysunek należy do instrumentu, nie do widoku** | |
| Ten sam poziom na dwóch interwałach | `Chart.test.tsx::keeps the objects through a resolution change` |
| Ten sam poziom w dwóch slotach | `tests/test_chart_drawings_store.py::test_list_only_answers_for_the_symbol_asked` (odczyt jest po symbolu, nie po slocie — sprzed tej zmiany, nietknięte) |
| Strefa bez drugiej ceny | `tests/test_drawings_tool.py::test_a_zone_with_inverted_prices_names_both` (sprzed tej zmiany, nietknięte) |
| Kolor z palety rysunków | `tests/test_drawings_tool.py::test_a_colour_from_the_drawing_palette_is_taken`; `tests/test_drawings_tool.py::test_the_tool_offers_the_drawing_palette_and_no_indicator_token`; `theme.test.ts::shares no colour with the indicator palette` |
| Kolor spoza palety rysunków | `tests/test_drawings_tool.py::test_an_indicator_colour_is_refused_and_named`; `tests/test_drawings_tool.py::test_a_colour_the_chart_cannot_draw_is_refused_and_nothing_lands` |
| (rysunek sprzed zmiany zachowuje kolor) | `theme.test.ts::still resolves an indicator token, for the objects drawn before this palette`; `tests/test_drawings_tool.py::test_the_read_carries_ids_shapes_and_labels` (czyta z powrotem `--color-up`) |
| (prompt nie obiecuje już palety wskaźników) | `tests/test_prompt_store.py::test_the_drawing_paragraph_no_longer_promises_the_indicator_palette`; `tests/test_prompt_store.py::test_both_seeded_texts_name_the_drawing_tools` |

## Gaps

- **Task 8.3 — przejście ręką na żywym stacku.** Nie wykonane. Wymaga Dockera, sesji
  Capital i klucza OpenAI, a sprawdza rzeczy, których żaden z powyższych testów nie
  dotyka: czy kliknięcie faktycznie trafia w linię na prawdziwym canvasie, czy kursor
  zmienia się przy najechaniu, czy karta nie zasłania obiektu przy krawędzi ekranu, i czy
  zaznaczenie przeżywa odświeżenie strony. To jest czynność operatora i nie da się jej
  zastąpić testem w jsdom.
- **„Najechanie na obiekt"** — dowiedzione tylko do granicy, którą ten moduł trzyma:
  prymityw zwraca `cursorStyle: "pointer"`. Że biblioteka faktycznie zmienia kursor na
  ten, o który prymityw poprosił, jest jej zachowaniem, nie naszym, i sprawdza to dopiero
  przejście z task 8.3.
- **„Gdy dwa obiekty nachodzą na siebie, wskazany MUST zostać dokładnie jeden"** — bez
  własnego testu. Biblioteka wybiera jedno trafienie po `zOrder` (`bestPrimitiveHit`)
  i oddaje jedno `hoveredObjectId`, a `Chart` czyta jedno id, więc dwa naraz nie mają
  którędy wejść. Sprawdzone czytaniem `lightweight-charts.development.mjs`, nie testem.
