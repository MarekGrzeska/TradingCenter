## ADDED Requirements

### Requirement: Odczyt rewizji podaje serię wykonania

Każdy odczyt rewizji i odpowiedź `POST /validate` dla poprawnego dokumentu MUST podawać serię wykonania, na której
dokument się wykona: interwał decyzji albo `MINUTE`. Sufit długości zakresu w odpowiedzi stanu pakietu MUST być liczbą
świec serii wykonania i MUST mieć tę nazwę w kontrakcie, a nie nazwę liczby minut.

#### Scenario: Rewizja bez poziomów

- **WHEN** operator czyta rewizję strategii na `MINUTE_5`, która wchodzi zleceniem rynkowym i wychodzi tylko przez `when`
- **THEN** odpowiedź MUST podawać serię wykonania `MINUTE_5`

#### Scenario: Rewizja ze stopem

- **WHEN** operator czyta rewizję tej samej strategii z dodanym stopem
- **THEN** odpowiedź MUST podawać serię wykonania `MINUTE`
