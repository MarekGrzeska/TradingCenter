## Purpose

Jak późno news dotarł do archiwum i ile z tego spóźnienia jest winą źródła, a ile własnej pętli —
mierzone przy każdym newsie i zbierane per źródło, żeby operator wiedział, któremu feedowi ufać
w wyścigu z rynkiem.

## ADDED Requirements

### Requirement: News niesie trzy momenty, z których liczy się opóźnienie

Każdy news MUST mieć zapisane trzy momenty: czas publikacji według źródła (może go nie być),
moment pierwszego zobaczenia przez pakiet i moment poprzedniego udanego pobrania tego źródła przed
tym, w którym news się pojawił. Wszystkie trzy MUST być wydawane klientowi obok newsa.

#### Scenario: News z kompletem momentów

- **WHEN** klient odczytuje news zebrany podczas obserwacji źródła
- **THEN** odpowiedź MUST nieść czas publikacji, moment pierwszego zobaczenia i moment poprzedniego pobrania

### Requirement: Opóźnienie ma granicę dolną i górną

Pakiet MUST podawać opóźnienie newsa jako dwie liczby, a nie jedną.

- **Granica górna** to czas od publikacji do pierwszego zobaczenia: ile czekał operator.
- **Granica dolna** to czas od publikacji do poprzedniego pobrania, nie mniej niż zero. Tyle co
  najmniej spóźnił się sam feed, bo przy poprzednim pobraniu newsa w nim jeszcze nie było.

Jedna liczba mieszałaby spóźnienie źródła z odstępem pobierania. Różnica między granicami MUST NOT
przekraczać odstępu między dwoma pobraniami. To jest miara tego, ile kosztuje własny rytm pętli.

#### Scenario: Feed spóźniony

- **WHEN** news opublikowano o 10:00, poprzednie pobranie było o 10:03, a news zobaczono o 10:05
- **THEN** granica dolna MUST wynosić 3 minuty, a górna 5 minut

#### Scenario: Feed natychmiastowy

- **WHEN** news opublikowano o 10:04, poprzednie pobranie było o 10:03, a news zobaczono o 10:05
- **THEN** granica dolna MUST wynosić zero, a górna 1 minutę

### Requirement: Opóźnienia nie da się zmierzyć, to nie jest zero

News bez czasu publikacji, news zastany przy pierwszym pobraniu źródła i news, którego czas
publikacji wypada później niż jego zobaczenie o więcej niż tolerancja zegarów, MUST mieć
opóźnienie puste, każdy z nazwanym powodem. Żaden z nich MUST NOT wchodzić do statystyk źródła
jako zero ani jako liczba.

#### Scenario: Czas publikacji z przyszłości

- **WHEN** feed podaje czas publikacji o godzinę późniejszy niż moment zobaczenia newsa
- **THEN** opóźnienie MUST być puste z powodem „czas źródła w przyszłości”
- **AND** news MUST NOT wpływać na medianę ani percentyl źródła

#### Scenario: News zastany

- **WHEN** news został zapisany przy pierwszym udanym pobraniu źródła
- **THEN** opóźnienie MUST być puste z powodem „zastany”, a nie równe wiekowi newsa

### Requirement: Źródło ma swój rachunek opóźnień

Stan każdego źródła MUST nieść w oknie ostatnich 24 godzin:

- liczbę newsów,
- medianę i 90. percentyl granicy dolnej i górnej,
- liczbę newsów z opóźnieniem niezmierzalnym.

Poza oknem MUST nieść:

- odstęp pobierania,
- moment ostatniego udanego pobrania,
- moment i powód ostatniej porażki,
- czas publikacji najnowszego newsa w feedzie.

Źródło bez żadnego zmierzonego newsa MUST mieć statystyki puste, a nie zerowe.

#### Scenario: Porównanie dwóch źródeł

- **WHEN** operator odczytuje stan źródeł
- **THEN** dla każdego źródła MUST widzieć medianę i 90. percentyl obu granic z ostatniej doby

#### Scenario: Źródło dopiero dodane

- **WHEN** źródło ma za sobą tylko pierwsze pobranie
- **THEN** jego statystyki opóźnienia MUST być puste, a liczba newsów MUST obejmować newsy zastane

### Requirement: Stojące źródło jest nazwane

Stan źródła MUST pozwalać klientowi rozpoznać, że źródło stoi: ostatnie udane pobranie jest starsze
niż kilka jego odstępów albo nie było go nigdy. Źródło, które odpowiada, ale od dawna nie ma nowych
newsów, MUST być odróżnialne od źródła, które nie odpowiada.

#### Scenario: Źródło odmawia od godziny

- **WHEN** źródło przy każdym pobraniu od godziny odpowiada odmową
- **THEN** stan MUST nieść moment ostatniego udanego pobrania sprzed godziny i powód ostatniej porażki

#### Scenario: Źródło ciche, ale żywe

- **WHEN** źródło odpowiada poprawnie, a jego najnowszy news ma sześć godzin
- **THEN** stan MUST nieść świeże udane pobranie i sześciogodzinny wiek najnowszego newsa
