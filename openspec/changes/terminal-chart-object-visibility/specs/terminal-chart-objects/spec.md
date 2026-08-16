## MODIFIED Requirements

### Requirement: Wskazany obiekt mówi, czym jest

Wskazanie obiektu MUST pokazać jego opis **przy nim**, a nie w miejscu, którego operator
musiałby szukać: kształt, ceny, etykietę oraz chwilę powstania. To jest odpowiedź na
pytanie „co to za linia", które dziś wymaga otwarcia listy i odnalezienia obiektu po cenie.

Opis MUST pozwalać poprawić, zgasić i usunąć obiekt bez przechodzenia do listy, i MUST to
robić z tym samym skutkiem, co lista: skutek widoczny na wykresie od razu, nieudana
operacja powiedziana wprost, a lista i wykres zostawione takie, jakie były
(`terminal-chart`, „Operator zarządza naniesionymi obiektami z listy").

Zgaszenie MUST być odróżnialne od usunięcia w samym opisie — dwie operacje, z których
jedna jest odwracalna, a druga nie, MUST NOT wyglądać na jedną.

Zgaszenie wskazanego obiektu MUST zostawić jego opis otwarty, a opis MUST od razu
oferować zapalenie go z powrotem. Gaszenie jest odwracalne i najbliższa droga powrotna
MUST być tam, gdzie padło — opis znikający razem z obiektem odsyłałby operatora do listy
po cofnięcie tego, co właśnie zrobił jednym kliknięciem.

Usunięcie wskazanego obiektu MUST zdjąć wskazanie razem z nim: obiektu, którego nie ma,
nie da się wskazać. To jest ta różnica między usunięciem a zgaszeniem, która MUST być
widoczna także w tym, co zostaje na ekranie.

#### Scenario: Opis wskazanego obiektu

- **WHEN** operator wskazuje poziom z etykietą
- **THEN** widzi jego kształt, cenę, etykietę i chwilę powstania obok niego

#### Scenario: Poprawienie z opisu

- **WHEN** operator zmienia cenę wskazanego obiektu w jego opisie
- **THEN** obiekt rysuje się na nowej cenie
- **AND** lista obiektów pokazuje tę samą nową cenę

#### Scenario: Zgaszenie z opisu

- **WHEN** operator gasi wskazany obiekt w jego opisie
- **THEN** obiekt znika z wykresu
- **AND** jego opis jest nadal otwarty i oferuje zapalenie go z powrotem
- **AND** obiekt jest nadal na liście, oznaczony jako zgaszony

#### Scenario: Zapalenie z opisu tuż po zgaszeniu

- **WHEN** operator gasi wskazany obiekt, a potem zapala go z tego samego opisu
- **THEN** obiekt jest znowu narysowany

#### Scenario: Usunięcie z opisu

- **WHEN** operator usuwa wskazany obiekt z jego opisu
- **THEN** obiekt znika z wykresu i z listy
- **AND** nic nie jest wskazane

#### Scenario: Nieudane poprawienie z opisu

- **WHEN** poprawienie wskazanego obiektu kończy się błędem
- **THEN** terminal mówi, że się nie powiodło
- **AND** obiekt zostaje taki, jaki był

#### Scenario: Nieudane zgaszenie z opisu

- **WHEN** zgaszenie wskazanego obiektu kończy się błędem
- **THEN** terminal mówi, że się nie powiodło
- **AND** obiekt jest nadal narysowany i nadal wskazany

#### Scenario: Wskazany obiekt zgaszony skądinąd

- **WHEN** wskazany obiekt zostaje zgaszony z listy albo przez agenta
- **THEN** znika z wykresu
- **AND** jego opis jest nadal otwarty i oferuje zapalenie go z powrotem
