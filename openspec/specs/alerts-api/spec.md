# alerts-api Specification

## Purpose
Kontrakt pakietu alertów z terminalem i z resztą procesu: kto co może wołać, co mówi trasa stanu i co
widzi rozmowa.

## Requirements

### Requirement: Rozmowa może zapytać, co zmiana zrobiłaby z regułą

Powierzchnia narzędziowa MUST zawierać narzędzie, które dla istniejącej reguły i zmiany opisanej słowami zwraca regułę w
postaci po zmianie, z powodami, dla których nie zadziała. Narzędzie MUST NOT zapisywać ani zmieniać żadnej reguły i MUST
mówić w odpowiedzi, że reguła nie została zmieniona. Zużycie tokenów MUST wchodzić w ten sam dobowy sufit co szkice z
terminala. Narzędzie MUST NOT być oznaczone jako tylko do odczytu.

#### Scenario: Operator prosi o podniesienie progu

- **WHEN** operator mówi w rozmowie „podnieś próg reguły 4 do 1,12”, a agent woła narzędzie
- **THEN** odpowiedź MUST zawierać regułę z progiem 1,12 i resztą bez zmian
- **AND** reguła w bazie MUST pozostać z dotychczasowym progiem

#### Scenario: Reguły nie ma

- **WHEN** agent woła narzędzie z identyfikatorem, którego nie ma
- **THEN** MUST dostać odmowę „nie ma takiej reguły”, a model MUST NOT zostać zapytany
