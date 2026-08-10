## MODIFIED Requirements

### Requirement: Data OD jest przycinana do tego, co provider ma

Operator MUST móc podać dowolnie wczesną datę początku, łącznie z datą sprzed istnienia rynku.
Data wcześniejsza niż historia dostępna u providera MUST zostać przycięta do najstarszego
osiągalnego momentu i MUST NOT być odrzucona jako błąd — wpisanie odległej daty znaczy „wszystko,
co się da".

Przycięcie MUST wynikać z tego, co provider odpowiedział w ramach tego samego zlecenia, a nie
z granicy zapamiętanej wcześniej. Data wcześniejsza niż granica, którą archiwum trzyma, MUST
uruchomić sprawdzenie jej na nowo i MUST NOT zostać po cichu podniesiona do niej — inaczej para,
której granicę raz zapisano za wysoko, nie daje się już pogłębić żadną prośbą, a operator dostaje
zlecenie ukończone, które nic nie zebrało.

Wycena zlecenia i jego wykonanie MUST podawać ten sam zakres. Wycena nie zapisuje niczego, więc
MUST liczyć tak, jakby granica została zdjęta, choć sama jej nie zdejmuje — inaczej dialog
obiecuje pracę, której zlecenie nie wykona, albo odwrotnie.

#### Scenario: Data sprzed historii providera

- **WHEN** operator podaje datę początku wcześniejszą niż najstarsza świeca, którą provider potrafi
  podać dla tej pary
- **THEN** moduł przycina zakres do tego najstarszego osiągalnego momentu
- **AND** zlecenie odnotowuje, że zakres został przycięty, wraz z datą faktycznie użytą

#### Scenario: Data wcześniejsza niż granica zapamiętana przez archiwum

- **WHEN** operator podaje datę początku wcześniejszą niż zapisana dla tej pary granica
  najstarszego osiągalnego momentu
- **THEN** zlecenie planuje cały zakres od podanej daty, bez przycięcia do tej granicy
- **AND** kawałki idą od najnowszego, więc pierwszy, który trafi na krawędź historii, pozwala
  pominąć w hurcie resztę stojącą za nim

#### Scenario: Wycena tej samej prośby

- **WHEN** operator wycenia zlecenie z datą początku wcześniejszą niż zapisana granica
- **THEN** wycena podaje ten sam zakres i tę samą liczbę świec, którą zaplanuje zlecenie
- **AND** wycena MUST NOT zmienić zapisanej granicy ani niczego innego w archiwum

#### Scenario: Data w przyszłości

- **WHEN** operator podaje datę początku późniejszą niż chwila bieżąca
- **THEN** moduł odmawia utworzenia zlecenia i nazywa powód
