## Why

`POST /indicators/{symbol}` odmawia całego żądania, gdy choć jeden z zamówionych wskaźników nie
da się policzyć. Wskaźniki czytające serię drobniejszą niż rysowana — `session_range_*`,
`opening_range`, `time_profile`, a także `htf_levels_*`/`pivots_*` czytające grubszą — odmawiają
zawsze, gdy tej serii nikt nie zbiera, a to nie jest pomyłka wołającego, tylko właściwość tego,
co archiwum ma. Skutek: zaznaczenie jednego takiego wpisu kasuje z ekranu wszystkie pozostałe
wskaźniki tego samego panelu, choć policzyły się bez problemu.

Odmowa sama w sobie jest poprawna i zostaje. Zła jest jej ziarnistość: dotyczy żądania, a
powinna dotyczyć wpisu, którego naprawdę dotyczy.

## What Changes

- `IndicatorResultOut` niesie pole błędu. Wynik, którego nie dało się policzyć, wraca **z nazwą
  swojej przyczyny zamiast wartości** — nie jako brak wpisu w liście i nie jako pusta linia.
- Odpowiedź częściowa jest odpowiedzią udaną (`200`), nie odmową. Wskaźniki, które się policzyły,
  wracają policzone.
- Granica zostaje przesunięta tylko dla **stanu archiwum**: brak serii wymaganej przez konkretny
  wpis. Pomyłka wołającego — nieznany identyfikator, parametr poza zakresem, odwrócony zakres,
  przekroczony sufit żądania — dalej odmawia całości i dalej jest `422`. Cicha, częściowa
  odpowiedź na literówkę w identyfikatorze byłaby gorsza niż odmowa.
- Terminal: nieudany wskaźnik **zostaje zaznaczony** i zapisany w slocie siatki, nie rysuje się,
  a przyczyna trafia do istniejącego toasta i plakietki — z nazwą wskaźnika, którego dotyczy.
  Po zebraniu brakującej serii zaczyna działać sam, bez ponownego klikania.
- Nie jest to zmiana łamiąca: pole jest opcjonalne i puste dla każdej odpowiedzi, która dziś
  wraca. Konsument, który go nie czyta, widzi dokładnie to, co widział — poza tym, że dostaje
  odpowiedź tam, gdzie wcześniej dostawał `422`.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `market-data-indicators`: wymaganie „Wynik ma jeden z czterech kształtów" zyskuje piątą
  możliwość — wynik bez kształtu, za to z przyczyną. Wymaganie „Profil czasowy liczy się z serii
  minutowej" i „Poziomy z wyższego interwału pochodzą z zamkniętego okresu" przestają opisywać
  swoją odmowę jako odmowę całego żądania.
- `terminal-chart`: wymaganie „Wykres mówi, gdy wskaźników nie da się policzyć" przestaje
  zakładać, że nie da się policzyć **żadnego** — mówi o tych, których nie dało się, i rysuje
  resztę.

**Kolejność wobec `add-technical-indicators`.** Obie te zdolności opisują dziś wskaźniki
wyłącznie w delcie tamtej, niezarchiwizowanej jeszcze zmiany — `openspec/specs/` nie ma jeszcze
ani `market-data-indicators`, ani wskaźnikowych wymagań w `terminal-chart`. Ta zmiana stoi na
tamtej: wchodzi po niej i nie da się jej zarchiwizować wcześniej.

## Impact

- `market_data/contract.py` — `IndicatorResultOut`; pełna pięcioprzystankowa ścieżka
  (`CLAUDE.md`, „A new field on market-data's wire"), więc także `pnpm contract:generate`,
  `src/data/archive.ts` i `src/data/types.ts` w terminalu.
- `market_data/routers/indicators.py` — miejsce, w którym dziś podnoszone jest `HTTPException`
  dla brakującej serii: przenoszone do wyniku. Odczyty serii pomocniczych (drobnej i grubszej)
  przestają być warunkiem wstępnym całego żądania.
- `modules/terminal/src/chart/Chart.tsx`, `chart/indicators/useIndicators.ts` — plakietka i toast
  nazywają wskaźnik; wynik z błędem nie idzie do rysowania.
- Bez migracji: nic z tego nie jest przechowywane.
