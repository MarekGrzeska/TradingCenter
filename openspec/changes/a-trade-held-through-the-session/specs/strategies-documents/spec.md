## MODIFIED Requirements

### Requirement: Kształt dokumentu strategii

Dokument strategii MUST składać się z sekcji: `schema` (wersja języka), `name`, `hypothesis`, `notes`,
`symbol` (dokładnie jeden instrument), `timeframe` (interwał decyzji, jedna z rozdzielczości archiwum),
`params` (nazwa → wartość domyślna, minimum, maksimum, krok), `let` (zmienne nazwane jako formuły), `entries`
(co najmniej jedno wejście: strona `long` albo `short`, warunek `when`, zlecenie `market`, `limit` albo `stop`,
z formułą ceny dla dwóch ostatnich i opcjonalnym wygaśnięciem w świecach), `exits` (opcjonalnie `stop`, `target`,
`trail` z progiem w R i odległością, `when`, `max_bars`), `sizing` (`risk_fraction`, `fixed_units`,
`margin_fraction` z wartością od 0 do 1 włącznie albo `notional_fraction`) oraz `limits` (`daily_stop_r`,
`no_entry`). Sekcja albo pole spoza tej listy MUST być odrzucone, a nie pominięte.

#### Scenario: Dokument bez stopu

- **WHEN** dokument nie ma `exits.stop`, `exits.when` ani `exits.max_bars`
- **THEN** dokument MUST zostać odrzucony z wyjaśnieniem, że pozycja bez stopu potrzebuje wyjścia `when` albo
  `max_bars`

#### Scenario: Nieznane pole

- **WHEN** dokument zawiera pole `universe`
- **THEN** dokument MUST zostać odrzucony z błędem w tej ścieżce zamiast przyjęcia z pominięciem pola

## ADDED Requirements

### Requirement: Dokument bez stopu nie mierzy niczego w R

Dokument bez `exits.stop` MUST mieć `exits.when` albo `exits.max_bars`. Taki dokument MUST zostać odrzucony, gdy
używa czegoś, co mierzy się w R: `sizing.mode` równego `risk_fraction`, `exits.trail`, `limits.daily_stop_r` albo
nazw `open_r` lub `last_trade_r` w dowolnej formule. Każde takie użycie MUST być osobnym błędem w swojej ścieżce,
z wyjaśnieniem, że bez stopu nie ma 1 R. Dokument ze stopem MUST być sprawdzany tak jak dotąd.

#### Scenario: Strategia sesyjna bez stopu

- **WHEN** dokument na US100 i `MINUTE_5` ma wejścia z warunkiem `session_bar(NEW_YORK) == 1 and close > ema(12)`
  (long) i `session_bar(NEW_YORK) == 1 and close < ema(12)` (short), `exits.when` równe
  `minutes_to_session_close(NEW_YORK) <= 5`, nie ma stopu i ma `sizing` `margin_fraction` 0,05
- **THEN** dokument MUST zostać przyjęty

#### Scenario: Ułamek ryzyka bez stopu

- **WHEN** dokument bez `exits.stop` ma `sizing.mode` równe `risk_fraction` i `exits.when` z `open_r > 2`
- **THEN** dokument MUST zostać odrzucony z dwoma błędami: w `sizing.mode` i w `exits.when`
