## ADDED Requirements

### Requirement: Tura wie, którą strategię operator ma otwartą

Żądanie tury MAY nieść strategię, którą konsument ma otwartą: jej identyfikator (pusty dla nowej, jeszcze niezapisanej),
rewizję, na której opiera się edytor, oraz tekst edytora, gdy różni się od tej rewizji. Moduł MUST podać to modelowi jako
kontekst tury i MUST NOT zapisywać tego w transkrypcie. Tekst edytora ma nazwany sufit długości. Dłuższy MUST dać
odmowę żądania z tym sufitem i MUST NOT trafić do modelu obcięty. Żądanie bez strategii MUST działać jak dotąd.

#### Scenario: Prośba o zmianę otwartej strategii

- **WHEN** operator prosi „zmień stop na 1,5 ATR”, a tura niesie strategię 7 opartą na rewizji 4
- **THEN** model MUST dostać identyfikator 7 i rewizję 4 jako kontekst tury

#### Scenario: Niezapisany tekst edytora

- **WHEN** tura niesie tekst edytora różny od rewizji, na której się opiera
- **THEN** model MUST dostać ten tekst, a nie tylko zapisaną rewizję

#### Scenario: Strategia nie trafia do transkryptu

- **WHEN** tura niosła otwartą strategię
- **THEN** transkrypt MUST nieść pytanie operatora i wypowiedź agenta, bez strategii
