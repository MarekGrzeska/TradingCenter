## Why

Operator 27.10.2026 porównuje backtesty o różnych zakresach (od miesiąca do jedenastu lat) i widzi na liście tylko zwrot
całkowity. Przy procencie składanym ten rośnie wykładniczo z długością zakresu: +7329% z jedenastu lat wyglądało na
najlepszą strategię, choć rocznie (49%) była słabsza od trzech innych (100–130%). Raport każdego uruchomienia już liczy
zwrot roczny, ale lista go nie nosi.

Druga sprawa to szerokość. Lista uruchomień jest tabelą z nagłówkami do sortowania dopiero od 64rem szerokości panelu.
Na laptopie panel jest węższy i lista spada do kart, na których nie ma ani kolumn, ani sortowania.

## What Changes

- Nagłówek uruchomienia (`HeadlineOut`, kolumna `runs.headline`) niesie `annual_return_pct` z raportu. Migracja uzupełnia
  go w zapisanych uruchomieniach z ich raportów.
- Lista uruchomień w Backtests ma kolumnę „Rocznie” i daje się po niej sortować.
- Tabela pojawia się już od 48rem szerokości panelu. W węższej tabeli rewizja i zlecający schodzą pod zakres, a kolumny R
  zostają tylko w najszerszej.
- Karty w najwęższym panelu mają wybór sortowania, więc lista daje się uporządkować przy każdej szerokości.

## Capabilities

### New Capabilities
Brak.

### Modified Capabilities
- `strategies-api`: główne metryki `GET /runs` obejmują zwrot całkowity i roczny.
- `terminal-strategies`: lista uruchomień pokazuje zwrot roczny i daje się sortować przy każdej szerokości.

## Impact

- `modules/workbench/strategies`: `HEADLINE`, `HeadlineOut`, `_headline` narzędzia MCP, migracja `0007`.
- `modules/terminal`: wygenerowany kontrakt strategii, `strategiesApi`, `order.ts`, `RunsPanel`.
- `design.md` i `tasks.md` pominięte: jedno pole z raportu przeniesione do nagłówka i układ jednej listy, bez decyzji do
  opisania i bez kroków, których nie widać w diffie.
