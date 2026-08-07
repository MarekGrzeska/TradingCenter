## Purpose

Znajdowanie instrumentu i wstawianie go tam, gdzie ma być oglądany: wyszukiwarka po frazie oraz
droga z wyniku wyszukiwania do konkretnego slotu siatki.

## ADDED Requirements

### Requirement: Instrumenty wyszukuje się po frazie

Terminal MUST pozwalać wyszukać instrumenty po frazie i MUST pokazać dla każdego wyniku symbol,
nazwę, klasę aktywów oraz informację, czy da się nim handlować. Bieżące bid i ask MUST być pokazane
tam, gdzie źródło je podaje.

#### Scenario: Wyszukiwanie po frazie

- **WHEN** operator wpisuje frazę
- **THEN** terminal pokazuje pasujące instrumenty z symbolem, nazwą, klasą aktywów i flagą
  handlowalności

#### Scenario: Fraza bez wyników

- **WHEN** żaden instrument nie pasuje do frazy
- **THEN** terminal stwierdza, że nic nie znaleziono, zamiast pokazywać pustą listę bez komentarza

#### Scenario: Wyszukiwanie zawodzi

- **WHEN** źródło danych nie odpowiada na wyszukiwanie
- **THEN** terminal pokazuje, co zawiodło, wraz z możliwością ponowienia

#### Scenario: Pisanie w polu wyszukiwania

- **WHEN** operator pisze frazę znak po znaku
- **THEN** terminal MUST NOT wysyłać zapytania po każdym znaku
- **AND** pokazuje wynik ostatniej wpisanej frazy, nawet gdy wcześniejsza odpowiedź wróci później

### Requirement: Wynik wyszukiwania trafia do slotu

Z wyniku wyszukiwania MUST dać się wstawić instrument do slotu siatki. Terminal MUST powiedzieć, do
którego slotu instrument trafił, i MUST pokazać go tam bez ręcznego przechodzenia między zakładkami.

#### Scenario: Wstawienie instrumentu do slotu

- **WHEN** operator wybiera instrument z listy wyników
- **THEN** instrument trafia do aktywnego slotu siatki
- **AND** terminal pokazuje zakładkę wykresów z narysowaną serią tego instrumentu

#### Scenario: Instrument nie jest handlowalny

- **WHEN** wybrany instrument nie jest handlowalny
- **THEN** wykres i tak go pokazuje, a informacja o braku handlowalności zostaje przy nim widoczna

### Requirement: Katalog instrumentów mówi, gdy jest niepełny

Terminal MUST pozwalać wyliczyć katalog instrumentów i MUST pokazać, że wynik został ucięty, gdy
źródło to zgłasza. Lista ucięta MUST NOT wyglądać jak kompletna.

#### Scenario: Katalog ucięty

- **WHEN** źródło zgłasza, że wyliczenie katalogu zostało ucięte
- **THEN** terminal stwierdza to obok listy

#### Scenario: Katalog kompletny

- **WHEN** źródło zwraca katalog bez ucięcia
- **THEN** terminal podaje liczbę instrumentów bez ostrzeżenia o niekompletności
