## Purpose

Wykres świecowy jako jeden komponent używany wszędzie tak samo: dostaje symbol i rozdzielczość,
rysuje historię, dokleja to, co przychodzi na żywo, i uczciwie mówi, gdy nie ma czego narysować.

## ADDED Requirements

### Requirement: Wykres jest sterowany symbolem i rozdzielczością

Wykres MUST przyjmować symbol i rozdzielczość jako wejście i MUST być tym w pełni określony — ten
sam komponent MUST działać zarówno jako pojedynczy wykres, jak i jako zawartość slotu siatki, bez
osobnego wariantu dla każdego z tych zastosowań.

#### Scenario: Ten sam komponent w dwóch miejscach

- **WHEN** ten sam wykres zostaje umieszczony solo i w slocie siatki
- **THEN** zachowuje się identycznie, różniąc się wyłącznie rozmiarem

#### Scenario: Zmiana symbolu

- **WHEN** wykres dostaje inny symbol
- **THEN** rysuje historię nowego symbolu i porzuca subskrypcję poprzedniego

### Requirement: Rozdzielczość zmienia się bez przeładowania

Wykres MUST pozwalać wybrać rozdzielczość z listy `MINUTE`, `MINUTE_5`, `MINUTE_15`, `MINUTE_30`,
`HOUR`, `HOUR_4`, `DAY`, `WEEK`. Zmiana MUST zaciągać historię w nowej rozdzielczości i
przepinać subskrypcję na żywo, bez przeładowania strony i bez utraty pozostałych widoków.

#### Scenario: Wybór innego interwału

- **WHEN** operator wybiera inną rozdzielczość
- **THEN** wykres pokazuje serię w tej rozdzielczości
- **AND** subskrypcja na żywo dotyczy już nowej rozdzielczości, a nie poprzedniej

#### Scenario: Szybka zmiana kilku rozdzielczości pod rząd

- **WHEN** operator przełącza rozdzielczość kilka razy szybciej, niż wraca odpowiedź
- **THEN** wykres pokazuje serię ostatnio wybranej rozdzielczości
- **AND** spóźniona odpowiedź na wcześniejszy wybór MUST NOT nadpisać tego, co widać

### Requirement: Świeca na żywo dokłada się do historii

Wykres MUST wstawiać świece przychodzące na żywo do serii po znaczniku czasu: świeca z okresu już
narysowanego podmienia istniejącą, świeca z okresu nowego dopisuje się na końcu. Seria MUST NOT
zawierać dwóch świec o tym samym znaczniku czasu.

#### Scenario: Ruch wewnątrz bieżącej świecy

- **WHEN** przychodzi świeca w budowie dla bieżącego okresu
- **THEN** ostatnia świeca na wykresie zmienia się, zamiast pojawić się jako kolejna

#### Scenario: Otwarcie nowego okresu

- **WHEN** przychodzi świeca dla okresu późniejszego niż ostatnia narysowana
- **THEN** wykres dokłada ją na końcu serii

### Requirement: Świeca w budowie jest oznaczona na ekranie

Świeca w budowie repaintuje i po restarcie źródła zaniża swój zakres. Wykres MUST oznaczać na
ekranie, że ostatnia świeca jest w budowie, żeby nikt nie wziął jej za rozstrzygniętą.

#### Scenario: Ostatnia świeca jeszcze się nie zamknęła

- **WHEN** ostatnia świeca serii jest w budowie
- **THEN** wykres to widocznie stwierdza

#### Scenario: Świeca się zamyka

- **WHEN** ta świeca zostaje zamknięta
- **THEN** oznaczenie znika, a wartości świecy są tymi od źródła

### Requirement: Wykres mówi, w jakim jest stanie

Wykres MUST rozróżniać na ekranie: trwa ładowanie historii, seria jest pusta, odczyt się nie
powiódł, strumień jest zerwany. Pusty prostokąt MUST NOT być odpowiedzią na żaden z tych stanów.

#### Scenario: Trwa zaciąganie historii

- **WHEN** historia jeszcze nie przyszła
- **THEN** wykres pokazuje, że trwa ładowanie

#### Scenario: Odczyt się nie powiódł

- **WHEN** odczyt historii kończy się błędem
- **THEN** wykres pokazuje komunikat mówiący, co zawiodło, wraz z możliwością ponowienia

#### Scenario: Instrument nie ma świec

- **WHEN** źródło zwraca pustą serię
- **THEN** wykres stwierdza, że dla tego instrumentu i tej rozdzielczości nie ma danych

#### Scenario: Strumień zerwany

- **WHEN** strumień przestaje odpowiadać
- **THEN** wykres oznacza dane jako nieaktualne, zamiast pokazywać zastygłą świecę bez komentarza

### Requirement: Wykres podaje wartości spod kursora

Wykres MUST pokazywać otwarcie, maksimum, minimum, zamknięcie i czas świecy wskazywanej kursorem.
Wolumen MUST być pokazany tam, gdzie źródło go niesie, a jego brak MUST być odróżnialny od zera.

#### Scenario: Kursor nad świecą

- **WHEN** operator najeżdża na świecę
- **THEN** wykres pokazuje jej otwarcie, maksimum, minimum, zamknięcie i czas

#### Scenario: Świeca bez wolumenu

- **WHEN** świeca pochodzi ze strumienia, który wolumenu nie niesie
- **THEN** wykres pokazuje brak wolumenu jako brak danej, a nie jako wartość zero

### Requirement: Wykres sprząta po sobie

Wykres MUST zwalniać swoje zasoby, gdy znika z ekranu: kończyć subskrypcję i usuwać nasłuchy.
Zmiana układu siatki MUST NOT zostawiać działających subskrypcji po slotach, których już nie ma.

#### Scenario: Slot znika po zmianie układu

- **WHEN** układ siatki zmienia się na mniejszy i część slotów przestaje istnieć
- **THEN** subskrypcje tych slotów zostają zakończone

#### Scenario: Zmiana rozmiaru okna

- **WHEN** okno przeglądarki zmienia rozmiar
- **THEN** wykres dopasowuje się do nowego rozmiaru kontenera
