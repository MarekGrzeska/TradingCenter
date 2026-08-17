## ADDED Requirements

### Requirement: Zestaw obejmuje zarządzanie harmonogramem, nie samo jego założenie

Zestaw MUST pozwalać modelowi zatrzymać, wznowić, poprawić i usunąć harmonogram oraz
wyzwalacz — nie tylko go założyć. Poprawka MUST NOT wymagać usunięcia i założenia od nowa:
harmonogram poprawiony zachowuje swoją historię wyzwoleń, a założony od nowa jej nie ma.

Operator, który zakłada harmonogram zdaniem, poprawia go też zdaniem. Zestaw, który umie
tylko zakładać, zostawia katalog rosnący w jedną stronę i odsyła do terminala po każdą
zmianę — a wtedy zdanie w rozmowie jest krótszą drogą do drugiego harmonogramu niż do
poprawienia pierwszego.

Narzędzie usuwające MUST nazywać w swoim opisie to, co usunięcie zabiera nieodwracalnie
(historię wyzwoleń) i czego nie rusza (przebiegi), bo model nie ma innego źródła tej wiedzy.

#### Scenario: Model zatrzymuje harmonogram

- **WHEN** operator prosi, żeby harmonogram przestał na razie chodzić
- **THEN** model ma narzędzie, którym go wyłącza, bez usuwania
- **AND** ten sam harmonogram daje się wznowić

#### Scenario: Poprawka zachowuje wpis

- **WHEN** model zmienia porę harmonogramu
- **THEN** harmonogram zostaje ten sam, z tą samą historią
- **AND** nie powstaje drugi wpis

#### Scenario: Model usuwa wyzwalacz

- **WHEN** operator prosi o usunięcie wyzwalacza
- **THEN** model ma narzędzie, którym go usuwa
- **AND** odpowiedź mówi, że historia wyzwoleń zniknęła razem z nim

#### Scenario: Opis narzędzia usuwającego mówi, co znika

- **WHEN** model czyta opis narzędzia usuwającego harmonogram
- **THEN** opis mówi, że historia wyzwoleń znika bezpowrotnie
- **AND** mówi, że przebiegi i ich koszt zostają
