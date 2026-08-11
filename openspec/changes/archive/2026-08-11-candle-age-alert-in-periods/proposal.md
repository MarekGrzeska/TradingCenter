## Why

`alert-candle-age-stale` — jedyny alarm, który miał zawołać, gdy archiwum przestaje zbierać —
pali się nieprzerwanie od 9 sierpnia 2026, 19:22, i przespał całą awarię 10 sierpnia. Reguła
bierze `Maximum` z `market_data.candle_age_seconds` po **wszystkich** parach i porównuje z
jednym progiem 600 sekund, a świeca `DAY` ma z definicji do 86 400 sekund wieku. Odkąd
śledzona jest choć jedna para wolniejsza niż dziesięć minut, maksimum jest trwale ponad
progiem i alarm nie ma jak zmienić stanu.

## What Changes

- `market-data` emituje drugą metrykę wieku świecy — spóźnienie liczone w **okresach** danej
  rozdzielczości, a nie w sekundach. Jedna liczba znaczy wtedy to samo dla `MINUTE` i dla
  `WEEK`, więc jeden próg dla wszystkich par staje się prawdziwy.
- Metryka w sekundach zostaje bez zmian. Jest czytelna dla człowieka w portalu i nic jej nie
  zastąpi przy diagnozie; przestaje tylko być tym, na czym stoi alarm.
- Alarm w `infra/monitoring.tf` przechodzi na nową metrykę z progiem trzech okresów i traci
  `skip_metric_validation = true` — wyłączenie założone, gdy `market-data` nie było jeszcze
  wdrożone, z komentarzem „revisit once market-data is deployed".
- Kolejność wdrożenia przestaje być dowolna i jest zapisana: najpierw `market-data` z nową
  metryką, dopiero potem `terraform apply`. Odwrotnie Azure odrzuca regułę, bo waliduje
  istnienie metryki, której nikt jeszcze nie wysłał.

## Capabilities

### New Capabilities
- `market-data-monitoring`: co moduł raportuje o własnym zbieraniu na zewnątrz — metryki, po
  których poznaje się, że para przestała być uzupełniana, i w jakiej jednostce, żeby dały się
  porównywać między rozdzielczościami.

### Modified Capabilities
<!-- Żadna istniejąca zdolność nie zmienia wymagania: `market-data-tracking` mówi o stanie
     pary czytanym przez API i ten zostaje dokładnie taki, jaki był. -->

## Impact

- `modules/market-data/market_data/telemetry.py` — druga metryka obok istniejącej, licznik
  spóźnienia w okresach.
- `modules/market-data/market_data/tracking.py` — `DELIVERY_GRACE` i `STALE_AFTER_PERIODS`
  stają się czytane także przez telemetrię; dziś są prywatne dla stanu pary.
- `infra/monitoring.tf` — nazwa metryki, próg, opis alarmu, zdjęte `skip_metric_validation`.
- Wdrożenie: dwa kroki w ustalonej kolejności, wykonywane przez operatora (`terraform apply`
  nigdy nie należy do CI).
- Bez zmian: kontrakt HTTP modułu, terminal, baza.
