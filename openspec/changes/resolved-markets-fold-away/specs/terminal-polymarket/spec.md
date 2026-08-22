## MODIFIED Requirements

### Requirement: Lista pokazuje wydarzenie, nie pojedynczą monetę

Widok MUST przedstawiać obserwowane wydarzenie wraz z jego rynkami i wynikami każdego rynku.
Rynek o dwóch wynikach MUST być pokazany jako szczególny przypadek rynku wielowynikowego, a nie
odwrotnie: widok MUST NOT sprowadzać rynku do jednej ceny „za", ani pomijać rynków ani wyników,
których nie da się tak sprowadzić.

Każdy wynik MUST nieść swoje prawdopodobieństwo w skali 0..1 wraz z nazwaniem tej skali. Widok
MUST NOT przedstawiać go jako procentu bez powiedzenia tego wprost, bo odczytanie 0,62 jako 62
myli się o dwa rzędy wielkości i nie daje po drodze żadnego błędu.

**Rynek rozstrzygnięty MAY być domyślnie zwinięty**, a widok MUST wtedy podać ich liczbę i MUST
dać sposób ich pokazania. Zwinięcie MUST NOT być usunięciem: historia rynku, który się
rozstrzygnął, jest tym, czego dostawca już nie odda, więc jest najcenniejszym, a nie
najmniej ważnym, co archiwum trzyma.

Dla rynku rozstrzygniętego widok MUST NOT pokazywać wartości zmiany w oknach. Po rozstrzygnięciu
cena stoi, więc każde okno wyszłoby zerem albo brakiem pokrycia — pierwsze twierdzi, że rynek się
nie ruszył, drugie że archiwum ma dziurę, a prawdą jest, że nie ma czego mierzyć. Widok MUST
zamiast tego podać, czym rynek się rozstrzygnął.

#### Scenario: Wydarzenie o wielu rynkach

- **WHEN** obserwowane wydarzenie ma więcej niż jeden nierozstrzygnięty rynek
- **THEN** widok pokazuje każdy z nich wraz z jego wynikami

#### Scenario: Rynek o wielu wynikach

- **WHEN** rynek ma więcej niż dwa wyniki
- **THEN** widok pokazuje każdy wynik z jego własnym prawdopodobieństwem
- **AND** MUST NOT pokazywać wyłącznie najwyższego z nich

#### Scenario: Wydarzenie z rynkami rozstrzygniętymi

- **WHEN** część rynków wydarzenia jest rozstrzygnięta
- **THEN** widok domyślnie pokazuje tylko nierozstrzygnięte
- **AND** podaje liczbę rozstrzygniętych oraz sposób ich pokazania

#### Scenario: Rozstrzygnięty rynek pokazany świadomie

- **WHEN** operator każe pokazać rozstrzygnięte rynki
- **THEN** widok podaje dla każdego, czym się rozstrzygnął
- **AND** MUST NOT pokazać przy nim zmiany w żadnym oknie

#### Scenario: Wszystkie rynki wydarzenia rozstrzygnięte

- **WHEN** każdy rynek obserwowanego wydarzenia jest rozstrzygnięty
- **THEN** widok mówi to wprost
- **AND** MUST NOT wyglądać na wydarzenie bez rynków
