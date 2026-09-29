## Purpose

Zakładka terminala z newsami: co operator widzi po jej otwarciu, jak podane jest opóźnienie każdego
newsa i każdego źródła, oraz co ekran mówi, gdy źródło stoi albo odmawia.

## ADDED Requirements

### Requirement: Zakładka pokazuje newsy z nazwanego okna

Zakładka MUST pokazywać newsy z wybranego okna, najnowsze na górze, z domyślnym oknem ostatnich
6 godzin. MUST nazywać okno i liczbę newsów wprost, a gdy kontrakt obciął listę, MUST to
powiedzieć. Operator MUST móc zawęzić listę do wybranych źródeł i do tekstu.

#### Scenario: Otwarcie zakładki

- **WHEN** operator otwiera zakładkę
- **THEN** widzi newsy z ostatnich 6 godzin, najnowsze na górze, wraz z liczbą i nazwą okna

#### Scenario: Lista obcięta

- **WHEN** kontrakt odpowiada, że lista jest obcięta
- **THEN** ekran MUST to powiedzieć, zamiast udawać, że pokazuje całe okno

### Requirement: News pokazuje swoje opóźnienie

Karta newsa MUST pokazywać tytuł i lead w języku źródła, wydawcę, czas publikacji, opóźnienie
i drogę do oryginału. Opóźnienie MUST być pokazane jako zakres od granicy dolnej do górnej. Gdy go
nie ma, karta MUST pokazać powód, na przykład „zastany” albo „brak czasu publikacji”. MUST NOT
pokazywać zera ani pustego miejsca bez wyjaśnienia.

#### Scenario: News ze zmierzonym opóźnieniem

- **WHEN** news ma granicę dolną 3 minuty i górną 5 minut
- **THEN** karta MUST pokazać oba końce zakresu

#### Scenario: News bez czasu publikacji

- **WHEN** feed nie podał czasu publikacji
- **THEN** karta MUST pokazać, że opóźnienia nie da się zmierzyć i dlaczego

### Requirement: Operator zachowuje news jednym przyciskiem

Karta newsa MUST mieć przycisk, który stawia albo zdejmuje znacznik zachowania, i MUST pokazywać,
czy news jest zachowany. Dla niezachowanego MUST pokazywać, kiedy zniknie. Zakładka MUST dawać widok
samych newsów zachowanych. Nieudana zmiana znacznika MUST zostawić kartę w stanie sprzed kliknięcia
i MUST powiedzieć, że się nie udało.

#### Scenario: Zachowanie newsa

- **WHEN** operator klika przycisk zachowania na karcie
- **THEN** karta MUST pokazać news jako zachowany, bez momentu zniknięcia

#### Scenario: Zdjęcie znacznika ze starego newsa

- **WHEN** operator zdejmuje znacznik z newsa starszego niż okres retencji
- **THEN** ekran MUST powiedzieć, że news zniknie przy najbliższym czyszczeniu

#### Scenario: Zmiana znacznika się nie udała

- **WHEN** kontrakt odmawia albo nie odpowiada na zmianę znacznika
- **THEN** karta MUST wrócić do poprzedniego stanu i MUST pokazać błąd

### Requirement: Zestawienie źródeł odpowiada, komu ufać

Zakładka MUST pokazywać zestawienie wszystkich źródeł. Przy każdym MUST być:

- stan,
- moment ostatniego udanego pobrania,
- mediana i 90. percentyl opóźnienia z doby,
- wiek najnowszego newsa,
- liczba newsów.

Źródło stojące, odmawiające albo z nieczytelnym feedem MUST być wyróżnione, wraz z powodem
i momentem ostatniego udanego pobrania.

#### Scenario: Jedno źródło odmawia

- **WHEN** jedno ze źródeł od godziny odpowiada odmową
- **THEN** zestawienie MUST je wyróżnić z powodem i momentem ostatniego udanego pobrania
- **AND** newsy pozostałych źródeł MUST być pokazywane normalnie

### Requirement: Pusta lista mówi, dlaczego jest pusta

Zakładka MUST odróżniać brak newsów w oknie przy działających źródłach od sytuacji, w której
żadne źródło nie ma świeżego udanego pobrania. MUST NOT odpowiadać na obie tą samą pustą listą.

#### Scenario: Wszystkie źródła stoją

- **WHEN** żadne źródło nie ma udanego pobrania z ostatnich kilku odstępów
- **THEN** ekran MUST powiedzieć, że zbiór stoi, zamiast pokazywać pustą listę

### Requirement: Lista odświeża się sama i nie gubi tego, co pokazuje

Zakładka MUST odświeżać newsy i stan źródeł bez czynności operatora. Nieudane odświeżenie MUST NOT
skasować tego, co jest już na ekranie.

#### Scenario: Odświeżenie nie dochodzi

- **WHEN** odświeżenie kończy się błędem, a lista jest już wypełniona
- **THEN** poprzednie newsy MUST zostać na ekranie
