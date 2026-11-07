# youtube-data-transcripts Specification

## Purpose
TBD - created by archiving change add-youtube-archive. Update Purpose after archive.
## Requirements
### Requirement: Dostawca jest ustawieniem, nie kodem

Moduł MUST pobierać transkrypcje od jednego dostawcy wybranego ustawieniem: Gemini, który słucha filmu
z jego adresu, albo symulacji. Moduł MUST NOT czytać napisów YouTube. Każda transkrypcja MUST nieść
nazwę dostawcy, język, nazwę modelu i to, że tekst jest automatyczny. Wyjątek zgłoszony przez dostawcę
MUST być traktowany jak blokada.

#### Scenario: Film przepisany przez Gemini

- **WHEN** dostawcą jest Gemini, a film ma znaną długość
- **THEN** transkrypcja MUST zostać zapisana z dostawcą `gemini` i nazwą modelu

#### Scenario: Dostawca zgłasza wyjątek

- **WHEN** wywołanie dostawcy kończy się wyjątkiem
- **THEN** film MUST zostać oczekujący z nietkniętą liczbą prób, a przebieg MUST przestać pytać

### Requirement: Blokada i brak napisów to dwa różne stany

Moduł MUST odróżniać „film nie ma napisów" od „dostawca nie wpuszcza". Blokada MUST NOT zmieniać
stanu filmu ani zużywać jego prób; MUST być widoczna w trasie stanu jako stan dostawcy wraz z
momentem ostatniej blokady.

Z domowego adresu pobieranie działa, a z chmury bywa blokowane w całości — bez tego rozróżnienia
produkcja wyglądałaby jak seria filmów bez napisów.

#### Scenario: Każde zapytanie kończy się blokadą

- **WHEN** jedyny dostawca blokuje każde zapytanie
- **THEN** filmy MUST pozostać oczekujące, z nietkniętą liczbą prób
- **AND** trasa stanu MUST nazwać dostawcę zablokowanym

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

### Requirement: Sekret dostawcy nie trafia do adresu

Poświadczenie dostawcy MUST być przekazywane nagłówkiem, nigdy w adresie żądania. Moduł MUST NOT
logować, zwracać ani zapisywać poświadczenia. MUST istnieć test, który sprawdza, że żaden adres
wychodzący z modułu nie niesie sekretu.

Adres żądania trafia do logów biblioteki HTTP — tak do telemetrii trafiły już tokeny botów.

#### Scenario: Żądanie z kluczem

- **WHEN** moduł woła dostawcę wymagającego klucza
- **THEN** klucz MUST być w nagłówku, a adres żądania MUST NOT go zawierać

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

### Requirement: Zablokowany dostawca odpoczywa

Dostawca, którego ostatnia odpowiedź była blokadą młodszą niż czas odpoczynku z ustawień, MUST NOT być
pytany. Po upływie tego czasu MUST zostać zapytany znowu. Dopóki odpoczywa, przebieg MUST NOT
transkrybować, a filmy MUST zostać oczekujące z nietkniętą liczbą prób.

Odmowa Gemini to przeciążony model albo limit zapytań — mija w minuty.

#### Scenario: Przeciążony model

- **WHEN** Gemini odmówił dziesięć minut temu, a odpoczynek trwa piętnaście
- **THEN** film MUST NOT zostać zapytany teraz i MUST zostać zapytany po upływie odpoczynku

### Requirement: Transkrypcja niesie czas i pochodzenie

Tekst transkrypcji MUST być zapisany w akapitach poprzedzonych znacznikiem czasu od początku filmu w
postaci `[MM:SS]` albo `[G:MM:SS]`. Transkrypcja od dostawcy słuchającego MUST nieść nazwę modelu,
a kontrakt strony transkrypcji MUST ją podawać.

#### Scenario: Strona transkrypcji z Gemini

- **WHEN** klient czyta stronę transkrypcji filmu przepisanego przez Gemini
- **THEN** odpowiedź MUST podać dostawcę `gemini`, tekst automatyczny i nazwę modelu

