## ADDED Requirements

### Requirement: Wykres przyjmuje kadr z zewnątrz

Wykres MUST przyjmować kadr — żądanie, żeby pokazać wskazany fragment osi czasu — obok
symbolu i rozdzielczości, którymi jest sterowany. Kadr MUST dać się wskazać zakresem
„od–do", punktem w czasie wraz z liczbą świec wokół niego, albo liczbą ostatnich świec.

Kadr sięgający przed najstarszą narysowaną świecę MUST spowodować dociągnięcie starszej
historii, zanim widok zostanie ustawiony. Wykres MUST NOT ustawiać widoku na fragment osi,
którego świec jeszcze nie ma — pusty ekran w miejscu, o które operator prosił, czyta się
jak brak danych, a nie jak trwające wczytywanie. Dociąganie MUST mieć kres: kadr, którego
archiwum nie umie zapełnić, MUST skończyć się pokazaniem tego, co udało się dociągnąć,
i powiedzeniem o tym, a nie odpytywaniem bez końca.

Kadr MUST być żądaniem jednorazowym, nie trwałym stanem slotu: po jego zastosowaniu
operator MUST móc przewijać i przybliżać swobodnie, a wykres MUST NOT wracać do
zastosowanego kadru sam z siebie.

Kadr żądający fragmentu, w którym archiwum nie ma ani jednej świecy, MUST zostać
pominięty, a wykres MUST zostać tam, gdzie był. Pominięcie MUST być powiedziane tą samą
drogą, którą terminal mówi o pominiętej części polecenia agenta.

#### Scenario: Kadr na fragment już narysowany

- **WHEN** wykres dostaje kadr obejmujący świece, które ma już w serii
- **THEN** widok przesuwa się na nie bez odczytu z archiwum

#### Scenario: Kadr sięgający przed narysowaną historię

- **WHEN** wykres dostaje kadr zaczynający się wcześniej niż jego najstarsza świeca
- **THEN** dociąga starszą historię
- **AND** ustawia widok dopiero wtedy, gdy świece z tego fragmentu są narysowane

#### Scenario: Kadr na okres, którego archiwum nie ma

- **WHEN** wykres dostaje kadr na fragment osi, w którym archiwum nie ma świec
- **THEN** widok zostaje taki, jaki był
- **AND** terminal mówi, że kadr został pominięty

#### Scenario: Operator przewija po zastosowanym kadrze

- **WHEN** operator przewija wykres po tym, jak kadr został zastosowany
- **THEN** wykres przewija się normalnie i nie wraca do kadru

## MODIFIED Requirements

### Requirement: Rozdzielczość zmienia się bez przeładowania

Wykres MUST pozwalać wybrać rozdzielczość z listy `MINUTE`, `MINUTE_5`, `MINUTE_15`, `MINUTE_30`,
`HOUR`, `HOUR_4`, `DAY`, `WEEK`. Zmiana MUST zaciągać historię w nowej rozdzielczości i
przepinać subskrypcję na żywo, bez przeładowania strony i bez utraty pozostałych widoków.

Zmiana rozdzielczości MUST zachować fragment osi czasu, który był widoczny przed nią:
operator patrzący na wybicie sprzed trzech dni MUST po zmianie interwału patrzeć nadal na
nie, a nie na całą świeżo wczytaną historię. Liczba świec w kadrze MUST zostać przycięta
do granic, w których wykres pozostaje czytelny — odcinek, który w nowej rozdzielczości
mieści dwie świece albo dziesięć tysięcy, MUST zostać rozszerzony albo zawężony wokół
swojego środka, zamiast być pokazany dosłownie.

Wykres stojący przy prawej krawędzi serii MUST przy niej zostać: zmiana interwału na
wykresie pokazującym bieżącą świecę MUST skończyć się wykresem pokazującym bieżącą świecę
nowego interwału.

Zachowanie kadru MUST dotyczyć zmiany zrobionej ręką operatora tak samo jak tej, która
przyszła poleceniem agenta — to ta sama zmiana rozdzielczości, wykonana z dwóch miejsc.

#### Scenario: Wybór innego interwału

- **WHEN** operator wybiera inną rozdzielczość
- **THEN** wykres pokazuje serię w tej rozdzielczości
- **AND** subskrypcja na żywo dotyczy już nowej rozdzielczości, a nie poprzedniej

#### Scenario: Szybka zmiana kilku rozdzielczości pod rząd

- **WHEN** operator przełącza rozdzielczość kilka razy szybciej, niż wraca odpowiedź
- **THEN** wykres pokazuje serię ostatnio wybranej rozdzielczości
- **AND** spóźniona odpowiedź na wcześniejszy wybór MUST NOT nadpisać tego, co widać

#### Scenario: Zmiana interwału nad fragmentem historii

- **WHEN** operator przewinięty na dzień sprzed tygodnia zmienia MINUTE_5 na HOUR
- **THEN** wykres pokazuje ten sam dzień w interwale godzinnym
- **AND** nie wraca ani na prawą krawędź, ani na całą wczytaną historię

#### Scenario: Zmiana interwału przy prawej krawędzi

- **WHEN** operator patrzący na bieżącą świecę zmienia rozdzielczość
- **THEN** wykres pokazuje bieżącą świecę nowej rozdzielczości przy prawej krawędzi

#### Scenario: Odcinek zbyt krótki dla nowego interwału

- **WHEN** operator patrzący na godzinę danych w MINUTE_5 zmienia rozdzielczość na DAY
- **THEN** wykres pokazuje czytelną liczbę świec dziennych wokół tej godziny, a nie jedną
