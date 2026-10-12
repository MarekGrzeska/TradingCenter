## MODIFIED Requirements

### Requirement: Dostawca jest ustawieniem, nie kodem

Moduł MUST pobierać transkrypcje przez uporządkowaną listę dostawców z ustawień. Każdy dostawca
MUST deklarować, czy czyta istniejące napisy, czy słucha filmu. Moduł MUST przechodzić do
następnego dostawcy po blokadzie albo błędzie poprzedniego. Po braku napisów u dostawcy napisów
moduł MUST przejść do najbliższego dostawcy słuchającego i MUST NOT pytać o ten film kolejnych
dostawców napisów. Brak tekstu od dostawcy słuchającego MUST być odpowiedzią łańcucha w tym
przebiegu. Każda transkrypcja MUST nieść nazwę dostawcy, język i to, czy tekst był automatyczny.
Dołożenie dostawcy MUST NOT zmieniać kontraktu.

#### Scenario: Pierwszy dostawca zablokowany

- **WHEN** pierwszy dostawca odpowiada blokadą, a drugi zwraca tekst
- **THEN** transkrypcja MUST zostać zapisana z nazwą drugiego dostawcy
- **AND** blokada pierwszego MUST zostać zapisana w stanie dostawców

#### Scenario: Brak napisów, a dalej jest dostawca słuchający

- **WHEN** dostawca napisów odpowiada, że film nie ma napisów, a później na liście stoi dostawca słuchający
- **THEN** moduł MUST zapytać dostawcę słuchającego w tym samym przebiegu

#### Scenario: Brak napisów i żadnego dostawcy słuchającego

- **WHEN** dostawca napisów odpowiada, że film nie ma napisów, a dalej stoją tylko dostawcy napisów
- **THEN** moduł MUST NOT pytać kolejnych dostawców w tym przebiegu i MUST zaplanować ponowienie

### Requirement: Moduł liczy zużycie każdego dostawcy i ma dzienny sufit

Moduł MUST zapisywać zużycie każdego dostawcy w jego własnej jednostce — jednostki API, zapytania,
sekundy filmu, tokeny — za każde wywołanie, także zakończone brakiem tekstu. Każdy dostawca MUST
podawać przed wywołaniem cenę filmu w swojej jednostce i MUST mieć własny dzienny sufit z ustawień.
Moduł MUST NOT wywoływać dostawcy, gdy reszta jego doby UTC nie pokrywa ceny filmu; film MUST wtedy
czekać bez zużycia próby, a trasa stanu MUST podać sufit i zużycie. Zapis zużycia MUST przetrwać
usunięcie treści, której dotyczył.

#### Scenario: Sufit osiągnięty w środku przebiegu

- **WHEN** zużycie dostawcy osiąga dzienny sufit
- **THEN** pozostałe filmy MUST czekać do następnej doby
- **AND** trasa stanu MUST podać sufit i zużycie

#### Scenario: Film droższy niż reszta doby

- **WHEN** dostawca płacony sekundami filmu ma na dziś mniej sekund, niż trwa film
- **THEN** moduł MUST NOT pytać go o ten film, a liczba prób filmu MUST zostać bez zmian

## ADDED Requirements

### Requirement: Dostawca słuchający przepisuje film bez napisów

Moduł MUST mieć dostawcę `gemini`, który przekazuje modelowi Gemini adres publicznego filmu i
dostaje dosłowny zapis wypowiedzi w języku filmu, bez tłumaczenia i bez streszczenia. Film dłuższy
niż próg z ustawień MUST być przepisywany kawałkami, a czasy w tekście MUST być liczone od początku
filmu. Ograniczenie zapytań, błąd serwera, przekroczony czas i odmowa klucza MUST być blokadą.
Film niedostępny MUST być brakiem tekstu bez opłaty, a odpowiedź pusta albo ucięta — brakiem tekstu
z opłatą. Dostawca `gemini` bez klucza albo przy źródle filmów, które nie zna długości filmu, MUST
być odmową startu nazywającą ustawienie.

#### Scenario: Godzinny film

- **WHEN** film trwa 60 minut, a próg kawałka to 30 minut
- **THEN** moduł MUST zapytać o dwa kawałki i zapisać jeden tekst, w którym druga połowa ma czasy od 30:00

#### Scenario: Limit zapytań u Google

- **WHEN** Gemini odpowiada kodem 429
- **THEN** film MUST zostać oczekujący z nietkniętą liczbą prób, a przebieg MUST przestać pytać

### Requirement: Napisy tylko w języku filmu

Gdy źródło filmów zna język, w którym film mówi, dostawca napisów MUST prosić wyłącznie o napisy w tym
języku. Gdy języka nie zna, MUST prosić o języki z ustawień w ich kolejności.

Ręczne napisy w innym języku to tłumaczenie, a odczyt rynkowy z tłumaczenia gubi nazwy i liczby.

#### Scenario: Polski film z angielskimi napisami

- **WHEN** film mówi po polsku i ma tylko angielskie napisy
- **THEN** dostawca napisów MUST odpowiedzieć brakiem napisów, a tekst MUST przyjść od dostawcy słuchającego, jeśli jest na liście

### Requirement: Zablokowany dostawca odpoczywa

Dostawca, którego ostatnia odpowiedź była blokadą młodszą niż czas odpoczynku z ustawień, MUST NOT być
pytany. Po upływie tego czasu MUST zostać zapytany znowu. Gdy żaden dostawca nie zostaje do zapytania,
przebieg MUST przestać transkrybować, a filmy MUST zostać oczekujące z nietkniętą liczbą prób.

Z chmury blokada napisów jest stała, a pytanie o nią przy każdym filmie kosztuje zapytanie i czas.

#### Scenario: Napisy zablokowane z chmury

- **WHEN** dostawca napisów zablokował zapytanie godzinę temu, a odpoczynek trwa sześć godzin
- **THEN** kolejne filmy MUST trafić od razu do dostawcy słuchającego

### Requirement: Transkrypcja niesie czas i pochodzenie

Tekst transkrypcji MUST być zapisany w akapitach poprzedzonych znacznikiem czasu od początku filmu w
postaci `[MM:SS]` albo `[G:MM:SS]`. Transkrypcja od dostawcy słuchającego MUST nieść nazwę modelu,
a kontrakt strony transkrypcji MUST ją podawać.

#### Scenario: Strona transkrypcji z Gemini

- **WHEN** klient czyta stronę transkrypcji filmu przepisanego przez Gemini
- **THEN** odpowiedź MUST podać dostawcę `gemini`, tekst automatyczny i nazwę modelu
