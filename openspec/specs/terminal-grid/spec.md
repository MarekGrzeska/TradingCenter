## Purpose

Siatka wykresów na zakładce Graph: ile wykresów widać naraz, co pokazuje każdy z nich i dlaczego
ten sam układ zastaje się po powrocie do terminala następnego dnia.

## Requirements

### Requirement: Układ siatki wybiera operator

Zakładka wykresów MUST pozwalać wybrać układ z zestawu `1x1`, `2x1`, `2x2` i `3x2`, gdzie liczby
oznaczają kolumny i wiersze. Sloty MUST wypełniać dostępną wysokość, a wykresy MUST przerysować się
do nowego rozmiaru po zmianie układu.

#### Scenario: Wybór układu

- **WHEN** operator wybiera układ z paska
- **THEN** siatka pokazuje dokładnie tyle slotów, ile wynika z układu
- **AND** każdy wykres dopasowuje się do nowego rozmiaru slotu

#### Scenario: Przejście na mniejszy układ

- **WHEN** operator przechodzi z układu większego na mniejszy
- **THEN** widoczne pozostają sloty mieszczące się w nowym układzie, licząc od pierwszego
- **AND** konfiguracja slotów, które zniknęły, zostaje zapamiętana i wraca po powrocie do
  większego układu

### Requirement: Slot ma własny instrument i własny interwał

Każdy slot MUST nieść własny symbol i własną rozdzielczość, ustawiane niezależnie od pozostałych
slotów. Zmiana w jednym slocie MUST NOT ruszać żadnego innego.

#### Scenario: Ten sam instrument w kilku interwałach

- **WHEN** operator ustawia w kilku slotach ten sam symbol z różnymi rozdzielczościami
- **THEN** każdy slot pokazuje własną serię
- **AND** zmiana rozdzielczości w jednym z nich nie zmienia pozostałych

#### Scenario: Slot pusty

- **WHEN** slot nie ma jeszcze przypisanego instrumentu
- **THEN** pokazuje zaproszenie do wybrania instrumentu, a nie pusty wykres ani błąd

### Requirement: Konfiguracja siatki przeżywa sesję

Wybrany układ oraz zawartość każdego slotu MUST być zapisywane po stronie przeglądarki i MUST być
odtwarzane przy kolejnym otwarciu terminala. Zapis MUST NOT wymagać żadnej akcji operatora.

#### Scenario: Powrót do terminala

- **WHEN** operator zamyka terminal i otwiera go ponownie
- **THEN** widzi ten sam układ i te same instrumenty z tymi samymi rozdzielczościami

#### Scenario: Zapisany stan jest nieczytelny

- **WHEN** zapisana konfiguracja jest uszkodzona albo pochodzi z niezgodnej wersji
- **THEN** terminal startuje z układem domyślnym, zamiast odmówić uruchomienia

#### Scenario: Zapisany symbol jest nieznany źródłu

- **WHEN** odtwarzany slot wskazuje symbol, którego bieżące źródło danych nie zna
- **THEN** slot mówi, że tego instrumentu nie ma w wybranym źródle, i pozwala wybrać inny
- **AND** pozostałe sloty działają dalej

### Requirement: Slot wskazuje, czego dotyczy

Każdy slot MUST nieść widoczny nagłówek z symbolem i rozdzielczością oraz MUST pozwalać zmienić
jedno i drugie bez opuszczania siatki.

#### Scenario: Zmiana instrumentu w slocie

- **WHEN** operator zmienia instrument z poziomu nagłówka slotu
- **THEN** slot pokazuje serię nowego instrumentu, a nagłówek jego symbol

#### Scenario: Który slot jest aktywny

- **WHEN** operator wskazuje slot
- **THEN** siatka oznacza go jako aktywny, żeby akcje kierowane do slotu miały jawny cel
