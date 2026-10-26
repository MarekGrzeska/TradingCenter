## ADDED Requirements

### Requirement: Transakcje uruchomienia jako CSV

Pakiet MUST publikować `GET /runs/{run_id}/trades.csv`, który oddaje wszystkie transakcje uruchomienia jako plik CSV
(`text/csv`, UTF-8 ze znacznikiem BOM, przecinek jako separator, kropka dziesiętna, wiersz nagłówka, nazwa pliku z
numerem uruchomienia w nagłówku odpowiedzi). Wiersz MUST nieść numer, stronę, czas wejścia i wyjścia w UTC i w strefie
`Europe/Warsaw` (w ISO 8601 z przesunięciem), ceny wejścia i wyjścia, wielkość, początkowy stop, wynik w pieniądzu, w
procentach i w R, najgłębszą stratę otwartą, koszty w trzech kolumnach, przyczynę wyjścia i oznaczenie rozstrzygnięcia
pesymistycznego. Wartość pusta MUST być pustym polem, nie zerem. Odpowiedź MUST zawierać wszystkie transakcje, nie
stronę, i MUST NOT wymagać trzymania całego pliku w pamięci. Uruchomienie, którego nie ma, MUST dawać 404 z jego numerem,
a uruchomienie bez transakcji MUST dawać sam nagłówek. Trasa MUST podlegać tej samej liście wołających i tej samej roli
co reszta tras pakietu.

#### Scenario: Pobranie transakcji

- **WHEN** operator pobiera `GET /runs/{run_id}/trades.csv` uruchomienia z 154 transakcjami
- **THEN** odpowiedź MUST mieć kod 200 i typ `text/csv`
- **AND** MUST mieć nagłówek i 154 wiersze

#### Scenario: Dwie strefy czasu

- **WHEN** transakcja weszła o 13:35 UTC 2 lipca 2026
- **THEN** jej wiersz MUST pokazywać 13:35 UTC i 15:35 w Warszawie

#### Scenario: Transakcja bez stopu

- **WHEN** uruchomienie strategii bez stopu ma transakcje
- **THEN** pola początkowego stopu i wyniku w R każdego wiersza MUST być puste

#### Scenario: Brak uruchomienia

- **WHEN** operator prosi o CSV uruchomienia, którego nie ma
- **THEN** odpowiedź MUST mieć kod 404 z numerem uruchomienia
