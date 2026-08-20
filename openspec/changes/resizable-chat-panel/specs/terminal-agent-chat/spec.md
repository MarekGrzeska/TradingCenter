## ADDED Requirements

### Requirement: Operator ustawia szerokość panelu

Panel rozwinięty MUST dać się rozszerzać i zwężać ciągnięciem za jego krawędź. Szerokość,
którą operator ustawi, MUST być zabrana albo oddana treści zakładki obok — panel odsuwa
ją i wpuszcza z powrotem, a MUST NOT jej zakrywać.

Szerokość MUST przetrwać przeładowanie terminala, tak samo jak stan zwinięcia. Panel
zwinięty i rozwinięty z powrotem MUST wrócić do szerokości, którą operator ustawił, a nie
do domyślnej.

Szerokość MUST być ograniczona z obu stron. Panel MUST NOT dać się zwęzić poniżej miary, w
której przestaje być czytelny, ani rozszerzyć tak, by treść zakładki zniknęła — obie
skrajności zostawiają operatora bez drogi powrotnej inaczej niż przez wyczyszczenie
pamięci przeglądarki. Szerokość zapamiętana wcześniej, a niemieszcząca się w oknie, którym
terminal został właśnie otwarty, MUST zostać sprowadzona do granicy, a nie odtworzona
dosłownie.

Chwyt MUST dać się obsłużyć klawiaturą i MUST nieść dostępną nazwę mówiącą, co robi.

#### Scenario: Operator poszerza panel

- **WHEN** operator ciągnie krawędź panelu w lewo
- **THEN** panel staje się szerszy
- **AND** treść zakładki obok dostaje odpowiednio mniej miejsca, pozostając widoczna

#### Scenario: Szerokość przeżywa przeładowanie

- **WHEN** operator ustawia szerokość panelu i przeładowuje terminal
- **THEN** panel ma tę samą szerokość

#### Scenario: Zwinięcie i rozwinięcie nie gubi miary

- **WHEN** operator zwija panel i rozwija go z powrotem
- **THEN** panel wraca do szerokości, którą operator ustawił

#### Scenario: Ciągnięcie poza granicę

- **WHEN** operator ciągnie krawędź poza dopuszczalną szerokość
- **THEN** panel zatrzymuje się na granicy
- **AND** treść zakładki obok pozostaje widoczna

#### Scenario: Okno węższe niż zapamiętana szerokość

- **WHEN** terminal zostaje otwarty w oknie węższym, niż pozwala zapamiętana szerokość
  panelu
- **THEN** panel dostaje szerokość sprowadzoną do granicy dla tego okna

#### Scenario: Chwyt z klawiatury

- **WHEN** operator ustawia fokus na chwycie i używa klawiszy strzałek
- **THEN** szerokość panelu zmienia się krok po kroku
