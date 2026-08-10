Etapy 1–6 wchodzą osobno na gałąź `add-technical-indicators`. Każdy kończy się zielonym
`uv run pytest`, `uv run ruff check .`, `uv run pyright` w `market-data` oraz `pnpm test`,
`pnpm lint`, `pnpm typecheck`, `pnpm contract:check` w terminalu. Do `main` idzie dopiero
grupa 7.

## 1. Szkielet na wylot (E0)

- [x] 1.1 Prototyp jądra na 5 prymitywach; zmierzyć p95 dla 5000 świec × 10 wskaźników i zapisać wynik
- [x] 1.2 Ustalić sufit żądania na podstawie 1.1
- [x] 1.3 `numpy` w `pyproject.toml`
- [x] 1.4 `market_data/indicators/kernel.py`: `sma`, `ema`, `rma`, `wma`, `stdev`, `true_range`, `rolling_max`, `rolling_min`
- [x] 1.5 `market_data/indicators/warmup.py`: `m = ceil(ln(1e-9) / ln(1 − α))` per rodzina wskaźników
- [x] 1.6 `market_data/indicators/catalogue.py`: kształt wpisu (id, name, aliases, group, params, output, render, warmup) + wpisy `sma`, `ema`, `atr`
- [x] 1.7 Modele w `market_data/contract.py`: katalog, żądanie, odpowiedź, cztery kształty wyjścia (`lines`, `markers`, `zones`, `levels`)
- [x] 1.8 `market_data/routers/indicators.py`: `GET /indicators`, `POST /indicators/{symbol}`
- [x] 1.9 Rozszerzanie okna odczytu o rozgrzewkę; `warmup_from` i `settled` w odpowiedzi
- [x] 1.10 Przeniesienie `uncovered`, `price_side` i `derived` z odczytu świec do odpowiedzi wskaźnikowej
- [x] 1.11 Odmowa ponad sufit i przy odwróconym zakresie, z nazwaną granicą
- [x] 1.12 Semafor ograniczający równoległe obliczenia
- [x] 1.13 Pliki wzorcowe dla `sma`, `ema`, `atr` na ustalonej serii syntetycznej
- [x] 1.14 Test niezależności od punktu startu, parametryzowany po wszystkich wskaźnikach z tłumieniem
- [x] 1.15 Test spójności katalogu z jądrem: każdy wpis policzony, klucze wyjścia równe deklarowanym
- [x] 1.16 Test granicy: żaden wpis nie czyta wolumenu, nie wymaga drugiego instrumentu i nie zwraca wartości logicznej
- [x] 1.17 `pnpm contract:generate` w terminalu
- [x] 1.18 Terminal: adapter w `src/data/archive.ts` (`indicatorCatalogue`, `computeIndicators`) — katalog i wyniki na typy terminala; `IndicatorSource` w `src/data/source.ts`
- [x] 1.19 Terminal: wybierak wskaźników budowany z katalogu, z walidacją parametrów wobec zakresów (`IndicatorPicker.tsx`)
- [x] 1.20 Terminal: rysowanie nakładek liniowych na panelu ceny, z `autoscaleInfoProvider` wg podpowiedzi katalogu — plus odczyt wartości pod kursorem, obok OHLC (spec `terminal-chart`, poza pierwotnym podziałem zadań)
- [x] 1.21 Terminal: przerwa w linii dla wartości nieznanych; sygnalizacja `settled: false`
- [x] 1.22 Terminal: nieudany odczyt wskaźników nie zasłania świec, z możliwością ponowienia

## 2. Miary ciągłe (E1)

- [x] 2.1 Pozostałe prymitywy: `rolling_argmax`, `rolling_argmin`, `linreg`, `mean_abs_dev`, `shift`, `diff`, `cross`
- [x] 2.2 Skala ruchu: `true_range`, `atr`, `atr_pct`
- [x] 2.3 Geometria świecy: `bar_range_atr`, `body_ratio`, `wick_up_ratio`, `wick_down_ratio`, `close_position`, `gap_prev_close_atr`
- [x] 2.4 Położenie w zakresie: `range_position`, `zscore`
- [x] 2.5 Zmienność z OHLC: `stdev`, `parkinson`, `garman_klass`, `rogers_satchell`, `yang_zhang`, `ulcer`
- [x] 2.6 Reżim: `adx` (z `+DI`/`−DI`), `choppiness`, `aroon`, `vortex`, `linreg_slope`, `r_squared`
- [x] 2.7 Średnie: `wma`, `rma`, `hma`, `kama`, `alma`, `lsma` (`sma` i `ema` z etapu 1)
- [x] 2.8 Oscylatory: `rsi`, `macd`, `stoch`, `stoch_rsi`, `cci`, `roc`, `williams_r`, `cmo`
- [x] 2.9 Wstęgi: `bbands`, `bbands_percent_b`, `bbands_bandwidth`, `keltner`, `donchian`, `envelope`
- [x] 2.10 Pliki wzorcowe dla całego zestawu
- [x] 2.11 TA-Lib jako zależność `dev`; porównanie z jawną tolerancją i spisaną listą znanych różnic
- [x] 2.12 Terminal: osobne panele oscylatorów przez `chart.addPane()` i `setStretchFactor`
- [x] 2.13 Terminal: poziomy odniesienia rysowane z podpowiedzi katalogu
- [x] 2.14 Terminal: histogram z kolorem na słupek (MACD)
- [x] 2.15 Terminal: odczyt wartości wskaźników pod kursorem obok OHLC, z nazwą i parametrami
- [x] 2.16 Terminal: zestaw wskaźników zapisywany w slocie siatki i odtwarzany; wpis nieznany katalogowi pomijany z komunikatem
- [x] 2.17 Pomiar p95 na pełnym zestawie; porównać z sufitem z 1.2

## 3. Punkty i poziomy (E2)

- [x] 3.1 `swing_points(n)` — zgłaszany po potwierdzeniu, z opóźnieniem podanym w odpowiedzi
- [x] 3.2 `last_swing_high` / `last_swing_low` jako linie schodkowe
- [x] 3.3 `rolling_extreme(n)`
- [x] 3.4 `htf_levels(okres)` — odczyt międzyrozdzielczościowy z zamkniętego okresu; odmowa przy braku serii
- [x] 3.5 `pivots(typ, okres)` — classic, fibonacci, camarilla, woodie, demark
- [x] 3.6 `level_clusters(n, tol)` — tolerancja w jednostkach ATR, wynik z licznością
- [x] 3.7 Wypełnienie kształtów `markers` i `levels` w odpowiedzi
- [x] 3.8 Terminal: markery przez `createSeriesMarkers`
- [x] 3.9 Terminal: prymityw promienia — odcinek od zadanego momentu, nie przez całą szerokość
- [x] 3.10 Test: punkt zwrotny nie znika ani nie przesuwa się przy powtórnym odczycie dłuższego zakresu
- [x] 3.11 Test: poziomy dnia poprzedniego na serii piętnastominutowej obowiązują od zamknięcia tamtego dnia

## 4. Strefy (E3)

- [x] 4.1 `range_gap` — kierunek, granice, `touched_at`, `filled_at` względem żądanego zakresu
- [x] 4.2 `body_gap`
- [x] 4.3 Klasyfikacja przerwy sesyjnej z pokrycia archiwum; `skip_session_gaps` domyślnie włączony
- [x] 4.4 `session_range(od, do, strefa)` — granice wyznaczane w kalendarzu strefy
- [x] 4.5 `opening_range(okno, n)`
- [x] 4.6 Kształt `zones` w odpowiedzi; strefa niedomknięta ma koniec nieustalony
- [x] 4.7 Terminal: `ZonePrimitive` — prostokąty, strefa otwarta do prawej krawędzi, selekcja po widocznym zakresie
- [x] 4.8 Test: przerwa piątek–niedziela nie jest zgłaszana jako luka cenowa
- [x] 4.9 Test: okno sesji obejmuje te same godziny lokalne przed i po zmianie czasu
- [x] 4.10 Pomiar płynności przewijania przy ~300 strefach w widocznym zakresie

## 5. Profil czasowy (E4)

- [x] 5.1 `time_profile` — odczyt serii minutowej niezależnie od zamówionej rozdzielczości
- [x] 5.2 Rozkład, poziom o największym udziale, przedział obejmujący zadany udział
- [x] 5.3 Odmowa przy braku serii minutowej dla pary
- [x] 5.4 Terminal: prymityw panelu — poziomy histogram przy prawej krawędzi
- [x] 5.5 Test: poziom o największym udziale zgodny z ręcznym przeliczeniem na próbce

## 6. Na żywo (E5)

- [x] 6.1 Terminal: dopytanie o ogon serii po zamknięciu świecy, tym samym żądaniem
- [x] 6.2 Terminal: wskaźnik nie zmienia się w trakcie świecy w budowie
- [x] 6.3 Terminal: zmiana symbolu, rozdzielczości albo źródła kasuje serie wskaźników razem ze świecami
- [x] 6.4 Test: żadna wartość policzona dla poprzedniej serii nie zostaje na ekranie w trakcie ładowania nowej

## 7. Domknięcie

- [ ] 7.1 `modules/market-data/README.md` — sekcja o wskaźnikach i o tym, czego moduł nie liczy
- [ ] 7.2 `CLAUDE.md` — poprawić opis modułu; dopisać ścieżkę dodania nowego wskaźnika
- [ ] 7.3 `openspec validate add-technical-indicators --strict`
- [ ] 7.4 Test lokalny całego stosu przez `./scripts/dev.sh`
- [ ] 7.5 `review.md`
- [ ] 7.6 Pull request gałęzi `add-technical-indicators` do `main`
