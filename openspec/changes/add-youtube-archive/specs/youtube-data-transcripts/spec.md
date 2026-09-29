## Purpose

Skąd archiwum YouTube bierze tekst filmu: dostawca transkrypcji za jednym interfejsem, wybierany
ustawieniem, z rozróżnieniem braku napisów od blokady i z budżetem, który liczy sam moduł.

## ADDED Requirements

### Requirement: Dostawca jest ustawieniem, nie kodem

Moduł MUST pobierać transkrypcje przez uporządkowaną listę dostawców z ustawień i MUST przechodzić
do następnego dostawcy wyłącznie po blokadzie albo błędzie poprzedniego, nie po braku napisów.
Każda transkrypcja MUST nieść nazwę dostawcy, język i to, czy napisy były automatyczne.
Dołożenie dostawcy MUST NOT zmieniać schematu przechowywania ani kontraktu.

#### Scenario: Pierwszy dostawca zablokowany

- **WHEN** pierwszy dostawca odpowiada blokadą, a drugi zwraca tekst
- **THEN** transkrypcja MUST zostać zapisana z nazwą drugiego dostawcy

#### Scenario: Brak napisów u pierwszego dostawcy

- **WHEN** pierwszy dostawca odpowiada, że film nie ma napisów
- **THEN** moduł MUST NOT pytać kolejnych dostawców w tym przebiegu i MUST zaplanować ponowienie

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

Moduł MUST zapisywać zużycie każdego dostawcy w jego własnej jednostce — jednostki API, kredyty,
tokeny — za każde wywołanie, także zakończone brakiem napisów. Każdy dostawca MUST mieć dzienny
sufit z ustawień; po jego osiągnięciu moduł MUST NOT wywoływać tego dostawcy do końca doby UTC,
a trasa stanu MUST to mówić. Zapis zużycia MUST przetrwać usunięcie treści, której dotyczył.

#### Scenario: Sufit osiągnięty w środku przebiegu

- **WHEN** zużycie dostawcy osiąga dzienny sufit
- **THEN** pozostałe filmy MUST czekać do następnej doby
- **AND** trasa stanu MUST podać sufit i zużycie

### Requirement: Sekret dostawcy nie trafia do adresu

Poświadczenie dostawcy MUST być przekazywane nagłówkiem, nigdy w adresie żądania. Moduł MUST NOT
logować, zwracać ani zapisywać poświadczenia. MUST istnieć test, który sprawdza, że żaden adres
wychodzący z modułu nie niesie sekretu.

Adres żądania trafia do logów biblioteki HTTP — tak do telemetrii trafiły już tokeny botów.

#### Scenario: Żądanie z kluczem

- **WHEN** moduł woła dostawcę wymagającego klucza
- **THEN** klucz MUST być w nagłówku, a adres żądania MUST NOT go zawierać
