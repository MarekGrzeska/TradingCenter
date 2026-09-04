## Why

Rachunek za sierpień 2026 to 59,6 EUR, z czego 34,7 EUR zjadł Log Analytics — więcej niż plan
App Service, na którym stoi osiem aplikacji. Źródło jest jedno i naprawia je PR #242: gateway
zapisywał każdą ramkę WebSocketu jako zależność i eksportował własne „Transmission succeeded",
razem 97% ingestu, 0,8 GB dziennie. Ta zmiana **nie jest** tą naprawą. Jest odpowiedzią na to,
że nic w tej infrastrukturze nie ograniczało kosztu takiej pętli i nic o niej nie powiedziało:
pętla chodziła od 9 sierpnia do 4 września i została zauważona przy czytaniu rachunku, nie
przez system. Workspace nie ma dziennego limitu (komentarz w `monitoring.tf` mówi wprost,
że „projekt nie zbliża się" do darmowych 5 GB — a przekroczył je czterokrotnie), a subskrypcja
nie ma budżetu.

## What Changes

- **Dzień logów dostaje sufit.** `log-tradingcenter` przyjmuje najwyżej ustaloną ilość danych
  na dobę; powyżej niej zbieranie staje do resetu. Sufit stoi z zapasem nad normalnym ruchem po
  #242, więc zwykły dzień go nie dotyka; dzień z pętlą taką jak sierpniowa kosztuje najwyżej
  tyle, ile sufit razy cena za GB.
- **Osiągnięcie sufitu budzi operatora.** Zatrzymane zbieranie to cisza, a ciszy ten projekt
  nie traktuje jak sygnału (`a-stopped-loop-wakes-somebody`). Jeden alert na zdarzeniu
  osiągnięcia limitu, do tej samej grupy akcji co pozostałe.
- **Subskrypcja dostaje budżet miesięczny** z powiadomieniem na prognozie i na przekroczeniu.
  Budżet nie ogranicza niczego — jest listem, nie bezpiecznikiem — ale to on mówi o koszcie,
  którego sufit nie widzi: nowy SKU, drugi serwer, koniec darmowego grantu bazy.
- Komentarz w `monitoring.tf` o niedosięganiu 5 GB znika, bo był nieprawdą od pierwszego dnia
  produkcji.

Poza zakresem, celowo: sama naprawa ingestu (#242, ścieżka PR), plan B3 → B2 (osobna decyzja
po pomiarze pamięci) i dwanaście zasobów w Sweden Central spoza Terraforma (decyzja
operatora, nie zmiana wymagania).

## Capabilities

### New Capabilities

- `monitoring-workspace`: co platforma gwarantuje o koszcie i widoczności własnej telemetrii —
  dzienny sufit ingestu, powiadomienie o jego osiągnięciu i miesięczny budżet subskrypcji.
  Nowa zdolność, bo żadna z istniejących nie jest o platformie: `market-data-monitoring`
  i trzy `*-liveness` mówią, co moduł publikuje, nie co dzieje się z tym po drugiej stronie.

### Modified Capabilities

—

## Impact

- `infra/monitoring.tf`: `daily_quota_gb` na workspace, jeden `azurerm_monitor_scheduled_query_rules_alert_v2`,
  jeden `azurerm_consumption_budget_subscription`, jedno `data "azurerm_subscription"`.
- `docs/kiedy-produkcja-milczy.html`: nowy alert i co przy nim zrobić.
- `apply` operatora, i to w określonej kolejności: **po** wdrożeniu #242 i po jednym dniu
  odczytu tabeli `Usage`. Sufit nałożony na dzisiejszy ruch (0,8 GB/dobę) odcinałby dane
  w co drugi dzień.
- Koszt zmiany: jeden alert logowy, rzędu 0,13 EUR miesięcznie (ta sama pozycja, którą miał
  `alert-app-exceptions-high`). Budżet i sufit są darmowe.
- `review.md` powstaje po `apply`, jak zawsze; `design.md` jest, bo są dwie decyzje z liczbą
  (wysokość sufitu, kwota budżetu) i jedna o kolejności.
