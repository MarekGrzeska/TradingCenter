## Why

Dziewięć alertów pisze dziś na jeden adres jednego operatora. Rachunek po refactorze
(kierunek D) wyliczył „alerty 9 → 3" jako pozycję *zdecydowaną* i przez cały refactor nic
z nią nie zrobiono — czyli dokładnie wzorzec nr 3 z tamtego rozliczenia. Ta zmiana ją
wykonuje, ale nie z tego powodu: „dziewięć to za dużo" nie jest argumentem, bo nie mówi,
**który** alert jest zbędny.

Argument, który to mówi, wyszedł dopiero z przeczytania `infra/monitoring.tf` w całości.
**Dwa z sześciu usuwanych alertów mają nieaktualny powód** — nie „słaby", tylko taki,
którego zdarzenie nie może się już powtórzyć w tej postaci:

- **`alert-database-storage-high`** ostrzega o 80% z 32 GB, a jego własny opis nazywa
  ryzyko, dla którego powstał: *„local work and production share this one server, and dev
  data counts against the same free-tier limit"*. Dev nie pisze już do tego serwera —
  `scripts/dev.py` odmawia zdalnej bazy wprost (*„compose.yaml container (localhost),
  never a remote database"*), odkąd baza deweloperska wróciła do kontenera 9 sierpnia
  2026. Alert pilnuje ryzyka odwróconego jedenaście dni przed tą propozycją.
- **`alert-app-exceptions-high`** powstał po burzy 45× `UndefinedColumnError` z 10
  sierpnia: migracja `0007` wylądowała *po* kodzie, który jej potrzebował, zabiła ingest
  na 23 minuty i sama się rozeszła, a nic nie zapłonęło. Ten tryb awarii został zamknięty
  konstrukcyjnie 16 sierpnia — każdy moduł migruje we własnym `lifespan`, zanim zacznie
  cokolwiek serwować (`market_data/app.py`, `migrate.run(MIGRATIONS)`). Migracja lądująca
  po kodzie, który jej potrzebuje, nie jest już możliwa. Sam plik przyznaje przy tym, że
  próg jest *„an estimate from one night, not a tuned value"*.

Pozostałe cztery to osąd, nie pomiar, i tak są tu opisane. Wspólny mianownik: alert ma
kogoś **obudzić**. Metryka, którą się czyta, podejmując decyzję, nie jest alertem — jest
wykresem, i pozostaje dostępna po zdjęciu powiadomienia.

## What Changes

Zostają trzy, każdy odpowiada na inne pytanie:

| Alert | Sev | Na jakie pytanie odpowiada |
|---|---|---|
| `alert-database-unreachable` | 0 | baza nie przyjmuje połączeń — staje wszystko |
| `alert-candle-age-high` | 1 | archiwum cicho kłamie przy otwartym rynku, a archiwum jest produktem |
| `alert-market-data-availability` | 1 | kontener nie odpowiada na `/ping` z zewnątrz |

Znika sześć:

- `alert-database-storage-high` — powód nieaktualny (wyżej);
- `alert-app-exceptions-high` — powód zamknięty konstrukcyjnie (wyżej);
- `alert-plan-memory-high` — to jest wejście do decyzji o SKU, nie zdarzenie. Metryka
  `MemoryPercentage` zostaje w portalu i to ją się czyta, decydując o planie; komentarz
  przy niej mówi wprost, że próg 92 nie ruszył się przez dwie zmiany SKU i że jego
  zmiana jest osobną decyzją z osobnym pomiarem. Taka pozycja nie budzi nikogo o 3 w nocy;
- `alert-market-data-requests-low` — zero żądań i zdrowy bezczynny proces to z tej metryki
  jedno i to samo, co plik sam mówi. Rozstrzyga to `alert-market-data-availability`, który
  zostaje. Przy jednym operatorze cisza w nocy jest normą, więc ten alert produkuje
  fałszywe zapalenia dokładnie wtedy, gdy nikt nie patrzy;
- `alert-gateway-http-5xx` — gateway jest jedynym modułem bez sondy wdrożeniowej
  (`deploy-gateway.yml`, `probe_path: ""`), więc traci swój jedyny sygnał produkcyjny.
  Zostaje sygnał pośredni i jest nim `candle_age`: market-data woła gateway przy każdej
  świecy, co ten sam plik workflow nazywa („market-data's own probe covers the end of this
  path");
- `alert-market-data-http-5xx` — i to jest **najdroższa pozycja tej listy**, opisana niżej
  jako świadomie oddana.

`azurerm_application_insights_standard_web_test.market_data_ping` **zostaje** — jest
podstawą alertu dostępności, nie osobnym alertem.

**Co się oddaje, nazwane wprost.** Moduł odpowiadający `500` na każdą trasę REST nadal
odda `200` na `/ping`, bo `/ping` jest trasą trywialną. Jeżeli przy tym ingest działa,
`candle_age` milczy — i wtedy terminal jest zepsuty, archiwum zdrowe, a nic nie płonie.
Dziś łapie to `alert-market-data-http-5xx`. To jest realna dziura, nie retoryczna, i
zostaje otwarta świadomie: przy jednym operatorze, który sam jest jedynym użytkownikiem
terminala, zepsuty terminal zgłasza się sam, w ciągu minut, przez człowieka przy klawiaturze
— a alert, który po roku odezwał się raz, kosztuje więcej uwagi, niż oszczędza. Gdyby
terminal kiedykolwiek miał drugiego użytkownika, ta linia wraca pierwsza.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

Brak. `market-data-monitoring` żąda, żeby powiadomienie o zatrzymanym zbieraniu dało się
skonfigurować **jedną** granicą wspólną dla wszystkich rozdzielczości — to jest
`alert-candle-age-high`, i on zostaje nietknięty, razem z obiema metrykami, które karmi.
Żadne wymaganie nie wylicza alertów, więc `skip_specs: true`. Zmiana kwalifikuje się przez
**trzecią** kategorię wyzwalacza — `infra/**`.

## Impact

**Infrastruktura.** `infra/monitoring.tf` i nic poza nim: sześć bloków
`azurerm_monitor_metric_alert` / `azurerm_monitor_scheduled_query_rules_alert_v2` znika
razem z komentarzami, które je uzasadniały. Dwa komentarze przy zostających zasobach trzeba
przepisać, a nie tylko zostawić: ten nad `market_data_ping` tłumaczy się przez parę z
`requests_low`, którego już nie będzie, a nagłówek `alert-on-dead-backend` mówi „five alerts
existed and none could tell dead from quiet" o zestawie, który przestaje istnieć.

**`terraform plan` pokaże sześć skasowań i zero zmian poza nimi** — to jest cała
weryfikacja tej zmiany i dlatego nie ma tu `tasks.md`.

**Czego nie dotyka.** Żadnego modułu, żadnej migracji, żadnego kontraktu, żadnego workflow.
Metryki i web test zostają — znikają wyłącznie powiadomienia.

**Apply jest operatora**, jak każdy tutaj: CI planuje, nie stosuje.

## Artefakty tej zmiany

`design.md` — **nie**: nie ma decyzji z alternatywą, którą warto ważyć. Wybór „które trzy"
podjął operator, a uzasadnienie każdego skreślenia mieści się w jednym zdaniu i stoi wyżej;
osobny dokument powtórzyłby proposal.md innym nagłówkiem.

`tasks.md` — **nie**: praca to skasowanie sześciu bloków w jednym pliku i przepisanie dwóch
komentarzy. Lista byłaby listą jednopozycyjną, czyli checkboxem, nie planem.

`review.md` — **do decyzji po wdrożeniu**, i jest kandydatem z jednego powodu: ta zmiana
usuwa obronę, a repo ma zapisaną zasadę, że obrona bez testu własnego trybu awarii jest tym,
czego nie przyjmuje. Tu nie ma testu do napisania — Azure Monitor nie jest w CI — więc
jedynym śladem, że skreślenia były przemyślane, jest ten dokument i `terraform plan`.
