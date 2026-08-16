# terminal-chart-objects Specification

## Purpose
Wybór naniesionego obiektu wprost na wykresie: trafienie w niego wskaźnikiem myszy, stan
zaznaczenia, opis pokazywany obok niego oraz to, jak ten wybór łączy się z listą obiektów
w nagłówku. Rysowanie i przeciąganie myszą pozostaje poza tą zdolnością — zaznaczenie
służy obejrzeniu i poprawieniu, nie manipulacji na płótnie.

## Requirements
### Requirement: Operator wskazuje obiekt na wykresie

Terminal MUST pozwalać wskazać naniesiony obiekt kliknięciem w niego na wykresie —
wszystkie trzy kształty, nie tylko poziom. Wykres jest miejscem, w którym operator na
obiekt patrzy, więc MUST być też miejscem, w którym może go dotknąć; lista w nagłówku
MUST NOT być jedyną drogą (`terminal-chart`, „Operator zarządza naniesionymi obiektami
z listy" pozostaje w mocy jako droga druga, nie jedyna).

Trafienie MUST mieć tolerancję: linia ma grubość kilku pikseli, a wskaźnik myszy nie jest
precyzyjny co do piksela, więc kliknięcie tuż obok linii MUST liczyć się jako kliknięcie
w nią.

Najechanie na obiekt MUST być widoczne, zanim padnie kliknięcie — obiekt, w który można
kliknąć, i obiekt, w który nie można, MUST NOT wyglądać tak samo pod kursorem. Miejsce
wykresu bez żadnego obiektu MUST NOT udawać, że coś tam jest.

Gdy dwa obiekty nachodzą na siebie w klikniętym punkcie, wskazany MUST zostać dokładnie
jeden — kliknięcie jest wyborem, a nie zaznaczeniem wszystkiego, co leży pod kursorem.

#### Scenario: Kliknięcie w poziom

- **WHEN** operator klika w narysowany poziom
- **THEN** ten poziom zostaje wskazany

#### Scenario: Kliknięcie obok linii, w granicach tolerancji

- **WHEN** operator klika kilka pikseli od linii obiektu
- **THEN** obiekt zostaje wskazany tak samo, jakby trafił dokładnie

#### Scenario: Najechanie na obiekt

- **WHEN** wskaźnik myszy znajdzie się nad obiektem
- **THEN** widać, że da się w niego kliknąć, zanim operator kliknie

#### Scenario: Kliknięcie w puste miejsce

- **WHEN** operator klika tam, gdzie nie ma żadnego obiektu
- **THEN** nic nie zostaje wskazane, a to co było wskazane przestaje być

#### Scenario: Kliknięcie w linię trendu i w strefę

- **WHEN** operator klika w linię trendu albo w strefę
- **THEN** zostaje wskazana tak samo jak poziom

### Requirement: Wskazany obiekt widać, że jest wskazany

Wskazany obiekt MUST być odróżnialny od pozostałych na pierwszy rzut oka, a pozostałe
MUST ustąpić mu pierwszeństwa — obiekt „wskazany", którego nie widać, jest stanem, którego
operator nie umie potwierdzić.

Wskazanie MUST dać się cofnąć bez sięgania po mysz do konkretnego miejsca: klawiszem
`Escape` oraz kliknięciem w puste miejsce wykresu.

Wskazanie MUST NOT zmieniać samego obiektu: nie przesuwa go, nie zmienia jego cen, etykiety
ani koloru w zapisie. Jest stanem ekranu, nie zapisem — i MUST NOT przeżyć zmiany symbolu
slotu, bo obiekty poprzedniego instrumentu przestają być na wykresie.

#### Scenario: Obiekt zostaje wskazany

- **WHEN** operator wskazuje obiekt
- **THEN** rysuje się inaczej niż przed wskazaniem
- **AND** pozostałe obiekty są mniej wyraziste niż on

#### Scenario: Odznaczenie klawiszem

- **WHEN** operator naciska `Escape` przy wskazanym obiekcie
- **THEN** żaden obiekt nie jest wskazany, a wszystkie rysują się jak przedtem

#### Scenario: Wskazanie nie jest zmianą obiektu

- **WHEN** operator wskazuje obiekt, a potem go odznacza
- **THEN** obiekt ma te same ceny, etykietę i kolor co przed wskazaniem

#### Scenario: Zmiana symbolu przy wskazanym obiekcie

- **WHEN** operator zmienia symbol slotu, mając wskazany obiekt
- **THEN** nic nie jest wskazane na nowym instrumencie

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

### Requirement: Wskazanie jest jedno, wspólne z listą

Wskazanie na wykresie i podświetlenie na liście obiektów MUST być tym samym stanem, nie
dwoma. Operator, który wskazał obiekt na wykresie, MUST widzieć go wyróżnionego na liście,
a obiekt wybrany z listy MUST zostać wskazany na wykresie.

Dwa niezależne wskazania byłyby dwiema odpowiedziami na pytanie „który obiekt jest teraz
wybrany", z których jedna zawsze byłaby nieaktualna.

#### Scenario: Z wykresu na listę

- **WHEN** operator wskazuje obiekt na wykresie
- **THEN** jego wiersz jest wyróżniony na liście obiektów

#### Scenario: Z listy na wykres

- **WHEN** operator wybiera obiekt z listy
- **THEN** obiekt jest wskazany na wykresie

#### Scenario: Odznaczenie sięga obu

- **WHEN** operator odznacza obiekt
- **THEN** ani wykres, ani lista nie wyróżniają już żadnego
