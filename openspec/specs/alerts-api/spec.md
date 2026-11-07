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

### Requirement: Kontrakt REST rozdziela operatora od producentów

Kontrakt REST MUST udostępniać operatorowi: katalog źródeł (typy zdarzeń ze schematem, narzędzia
tylko do odczytu ze schematem argumentów i wyniku, adresatów bramy), reguły z ich stanem, historię
odpaleń, szkic ze zdania i trasę stanu. Ogłoszenie typu i publikacja zdarzenia MUST być trasami
przyjmowanymi wyłącznie od wołających z procesu (`alerts-events`).

#### Scenario: Terminal czyta katalog

- **WHEN** terminal prosi o katalog źródeł
- **THEN** odpowiedź MUST zawierać ogłoszone typy zdarzeń z atrybutami i narzędzia tylko do odczytu z polami liczbowymi wyniku

### Requirement: Wołający są sprawdzani przez pakiet

Pakiet MUST prowadzić własny rekord wołających. Do tras operatora MUST mieć dostęp wyłącznie
aplikacje z listy z ustawień, rozpoznawane po identyfikatorze aplikacji z tokenu, a nie po
zalogowanej osobie. Każda trasa, której rekord nie wymienia, MUST być odmową.

#### Scenario: Nieznana aplikacja

- **WHEN** żądanie z ważnym tokenem aplikacji spoza listy prosi o listę reguł
- **THEN** pakiet MUST odmówić

### Requirement: Trasa stanu mówi, czego pakiet nie robi

Trasa stanu MUST podawać: liczbę reguł włączonych i wyłączonych, liczbę reguł z wadą (nieistniejący
adresat, schemat, który przestał pasować), czy pakiet doręcza (brama obecna), czy szkice są dostępne,
czas ostatniego obrotu zegara oraz liczbę odpaleń czekających na ponowienie.

#### Scenario: Zegar stoi

- **WHEN** zegar pakietu nie wykonał obrotu od trzech swoich interwałów
- **THEN** trasa stanu MUST pokazywać wiek ostatniego obrotu tak, żeby dało się odróżnić stojący zegar od braku odpaleń

### Requirement: Rozmowa widzi reguły i odpalenia, nie zmienia ich

Powierzchnia narzędziowa MUST zawierać narzędzie wyliczające reguły z ich stanem i narzędzie czytające
ostatnie odpalenia. MUST NOT zawierać narzędzi zapisujących (`alerts-rules`).

#### Scenario: Operator pyta, czemu nie dostał alertu

- **WHEN** operator pyta w rozmowie, dlaczego nie przyszedł alert o EURUSD
- **THEN** model MUST móc odczytać historię odpaleń tej reguły z powodami pominięć i niedostępności

