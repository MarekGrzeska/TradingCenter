## ADDED Requirements

### Requirement: Saldo konta demo daje się skorygować

Moduł MUST pozwalać skorygować saldo konta demo o zadaną kwotę. Kwota ujemna MUST być
przyjmowana tak samo jak dodatnia: ustawienie chudego rachunku jest częścią ustawiania
warunku eksperymentu, a nie pomyłką, przed którą trzeba bronić.

Korekta MUST dotyczyć konta aktywnego — tego samego, na którym działa handel i odczyt
pozycji — żeby „ile mam" i „ile dosypuję" nigdy nie dotyczyły dwóch różnych rachunków.

Moduł MUST NOT powtarzać we własnym kodzie granic, które stawia dostawca: sufitu salda,
zakresu kwoty ani limitu dobowego. Dostawca je zna i zmienia bez pytania nas, a kopia
przestaje być prawdą w dniu, w którym się rozejdzie. Odmowa dostawcy MUST dotrzeć do
wywołującego jako odmowa nazywająca powód, odróżnialna od awarii dostępu do dostawcy.

Możliwość ta MUST być dostępna wyłącznie w środowisku demo, co wynika z hosta, do którego
moduł jest związany, i nie wymaga osobnego sprawdzenia.

#### Scenario: Dosypanie środków

- **WHEN** konsument koryguje saldo konta demo o kwotę dodatnią
- **THEN** moduł potwierdza wykonanie
- **AND** kolejny odczyt kont pokazuje saldo powiększone o tę kwotę

#### Scenario: Zabranie środków

- **WHEN** konsument koryguje saldo konta demo o kwotę ujemną
- **THEN** moduł wykonuje korektę tak samo jak dodatnią

#### Scenario: Dostawca odmawia korekty

- **WHEN** dostawca odrzuca korektę, bo kwota wykracza poza przyjmowany zakres, saldo
  przekroczyłoby sufit albo limit dobowy został wyczerpany
- **THEN** moduł odpowiada odmową nazywającą powód podany przez dostawcę
- **AND** odmowa jest odróżnialna od awarii dostępu do dostawcy

## MODIFIED Requirements

### Requirement: Konta są wyliczane, jedno jest aktywne

Moduł MUST publikować konta osiągalne skonfigurowanymi poświadczeniami, oznaczać które jest
aktywne i pozwalać je przełączyć. Handel oraz odczyt pozycji MUST działać na koncie aktywnym.

Przełączenie konta zrywa strumień notowań u dostawcy. Moduł MUST to powiedzieć wywołującemu
— w tym, co publikuje o tej operacji — zamiast zostawiać przerwę w danych do odkrycia po
fakcie. Sam strumień MUST wrócić bez udziału wywołującego, tą samą drogą, którą moduł
odzyskuje każde inne zerwanie połączenia.

#### Scenario: Wylistowanie kont

- **WHEN** konsument wylistowuje konta
- **THEN** każde konto niesie identyfikator, nazwę, walutę, saldo, środki dostępne oraz wynik
- **AND** dokładnie jedno jest oznaczone jako aktywne

#### Scenario: Przełączenie aktywnego konta

- **WHEN** konsument przełącza się na znany identyfikator konta
- **THEN** moduł zwraca to konto oznaczone jako aktywne
- **AND** kolejne operacje na pozycjach i zleceniach działają na nim

#### Scenario: Przełączenie na nieznane konto

- **WHEN** konsument przełącza się na identyfikator, którego provider nie przyjmuje
- **THEN** moduł odpowiada błędem klienta nazywającym odrzucony identyfikator
- **AND** dotychczas aktywne konto pozostaje aktywne

#### Scenario: Strumień po przełączeniu konta

- **WHEN** konsument przełącza aktywne konto, gdy strumień notowań jest zestawiony
- **THEN** zerwanie strumienia jest tym samym zdarzeniem, co każde inne zerwanie: konsument
  strumienia dostaje stan mówiący, że połączenie jest odtwarzane
- **AND** moduł zestawia je ponownie sam, bez żądania od wywołującego
