# polymarket-data-api Specification

## Purpose
Kontrakt REST, którym terminal rozmawia z modułem: co jest obserwowane, jak to zmienić, jakie są
ceny, jak wyglądała historia i jak zmieniła się w oknach — oraz to, że kasowanie danych jest tutaj.
## Requirements
### Requirement: Obserwacje są zarządzalne przez kontrakt

Kontrakt MUST pozwalać odczytać listę obserwacji, objąć wydarzenie obserwacją i zakończyć
obserwację. Wskazanie wydarzenia MUST przyjmować zarówno adres strony dostawcy, jak i sam
identyfikator wydarzenia, i MAY nieść grupę, do której wydarzenie ma trafić.

Objęcie obserwacją MUST być niepodzielne: albo powstaje obserwacja wraz z całą strukturą rynków
i wyników, albo nie powstaje nic. Wydarzenie już obserwowane MUST NOT tworzyć drugiej obserwacji —
powtórzone żądanie MAY zaktualizować grupę i MUST powiedzieć, że obserwacja już trwała.

#### Scenario: Objęcie obserwacją po adresie

- **WHEN** operator wskazuje adres strony wydarzenia
- **THEN** powstaje obserwacja wraz z rynkami i wynikami tego wydarzenia
- **AND** odpowiedź niesie to, co zostało zapisane

#### Scenario: Wydarzenie już obserwowane

- **WHEN** operator wskazuje wydarzenie, które jest już obserwowane
- **THEN** nie powstaje druga obserwacja
- **AND** odpowiedź stwierdza, że obserwacja już trwała

#### Scenario: Zakończenie obserwacji

- **WHEN** operator kończy obserwację wydarzenia
- **THEN** próbkowanie ustaje
- **AND** historia tego wydarzenia pozostaje odczytywalna

#### Scenario: Zakończenie obserwacji, której nie ma

- **WHEN** operator kończy obserwację wydarzenia, które nie jest obserwowane
- **THEN** odpowiedź nazywa to wprost, zamiast zgłaszać awarię

### Requirement: Grupy są zarządzalne przez kontrakt

Kontrakt MUST pozwalać utworzyć grupę, odczytać grupy, przypisać do grupy wydarzenie i grupę
skasować. Skasowanie grupy MUST NOT kasować obserwacji ani danych.

#### Scenario: Utworzenie grupy i przypisanie

- **WHEN** operator tworzy grupę i przypisuje do niej obserwowane wydarzenie
- **THEN** odczyt tej grupy zwraca to wydarzenie

#### Scenario: Skasowanie grupy z wydarzeniami

- **WHEN** operator kasuje grupę, do której przypisane są wydarzenia
- **THEN** wydarzenia pozostają obserwowane, bez grupy

### Requirement: Ceny obserwowanych rynków są odczytywalne migawką i historią

Kontrakt MUST udostępniać jednym żądaniem migawkę ostatnich cen wszystkich obserwowanych wyników —
to jest widok, od którego zaczyna się każda strona terminala i który MUST NOT wymagać żądania na
wydarzenie. Każda cena w migawce MUST nieść moment, z którego pochodzi.

Kontrakt MUST udostępniać historię ceny wyniku w zadanym zakresie czasu, uporządkowaną od
najstarszej, wraz z tym, dokąd zebrany zakres sięga.

#### Scenario: Migawka wszystkich obserwacji

- **WHEN** terminal odczytuje migawkę
- **THEN** dostaje ostatnią cenę każdego obserwowanego wyniku wraz z jej momentem

#### Scenario: Historia poza zebranym zakresem

- **WHEN** terminal prosi o historię za okres wykraczający poza zebrany zakres
- **THEN** odpowiedź zwraca to, co jest, i stwierdza, dokąd zebrany zakres sięga
- **AND** MUST NOT przedstawić braku danych jako ciszy na rynku

### Requirement: Zmiany w oknach są liczone przy odczycie

Kontrakt MUST udostępniać zmianę ceny wyniku w oknach 5 minut, godziny, 4 godzin, doby
i 7 dni. Zestaw jest gęsty przy teraz i rzadki dalej, i to jest wybór, nie przeoczenie: rynek
predykcyjny rusza się wolno, więc drugie okno rzędu kwadransa powtarza to, co mówi pierwsze.

Wartości MUST być liczone z zebranej historii w chwili odczytu, a nie odczytywane z tabeli
utrzymywanej osobnym zadaniem — nie ma zadania, które by ją utrzymywało, i utrzymanie takiej
tabeli MUST NOT być wymagane, dopóki pomiar nie pokaże, że liczenie przy odczycie kosztuje za
dużo. Każde okno to osobne zapytanie na wynik, więc liczba okien jest mnożnikiem kosztu odczytu
i MUST NOT rosnąć bez odbiorcy, który je czyta.

Okno, dla którego historia nie sięga wystarczająco wstecz, MUST być zwrócone jako brak wartości
nazywający swój powód, a MUST NOT jako zero ani jako zmiana liczona od najstarszego punktu, jaki
jest — pierwsze kłamie o rynku, drugie o oknie.

Punkt bazowy MUST być wybierany z tolerancją na nierówny takt próbkowania i odpowiedź MUST nieść
moment, z którego faktycznie pochodzi.

#### Scenario: Odczyt zmian dla wydarzenia

- **WHEN** terminal odczytuje zmiany dla obserwowanego wydarzenia
- **THEN** dostaje dla każdego wyniku zmianę w pięciu oknach
- **AND** przy każdym oknie moment punktu bazowego, z którego została policzona

#### Scenario: Historia krótsza niż okno

- **WHEN** zebrana historia wyniku jest krótsza niż okno 7 dni
- **THEN** wartość dla tego okna jest brakiem nazywającym przyczynę
- **AND** MUST NOT być zerem ani zmianą liczoną od najstarszego posiadanego punktu

#### Scenario: Okno spoza zestawu

- **WHEN** konsument spodziewa się okna, którego kontrakt nie wylicza
- **THEN** kontrakt MUST NOT go zwrócić
- **AND** zestaw okien MUST być odczytywalny z kontraktu, a nie zapisany drugi raz po stronie konsumenta

### Requirement: Kasowanie danych jest czynnością kontraktu, a nie narzędzia

Kasowanie zebranej historii MUST być osiągalne wyłącznie przez kontrakt REST i MUST być odrębną
czynnością od zakończenia obserwacji. Żądanie MUST wskazywać, czego dotyczy, i MUST NOT być
skutkiem ubocznym niczego innego.

Skasowanie MUST usunąć próbki i zapis zebranego zakresu razem, w jednej niepodzielnej operacji —
zakres uchodzący za zebrany po usunięciu próbek jest wiążący dla planowania i sprawi, że
uzupełnianie już tam nie wróci.

#### Scenario: Operator kasuje historię wydarzenia

- **WHEN** operator kasuje zebraną historię wydarzenia
- **THEN** ani jedna jego próbka nie pozostaje w archiwum
- **AND** ani jeden zapis zebranego zakresu tego wydarzenia nie pozostaje w archiwum

#### Scenario: Kasowanie przerwane w połowie

- **WHEN** kasowanie nie może dojść do końca
- **THEN** archiwum zostaje w stanie sprzed kasowania

#### Scenario: Zapytanie o okres po skasowaniu

- **WHEN** konsument pyta o okres, który przed skasowaniem był zebrany
- **THEN** archiwum stwierdza, że tego okresu nie zebrało
- **AND** MUST NOT stwierdzać, że nie było wtedy notowań

### Requirement: Odpowiedzi nazywają swoje porażki

Odpowiedź kontraktu MUST odróżniać porażkę własną modułu od porażki dostawcy i od żądania, które
było niepoprawne. Konsument MUST móc rozpoznać, czy ma ponowić, poprawić żądanie, czy czekać.

#### Scenario: Baza nieosiągalna

- **WHEN** moduł nie może sięgnąć do własnej bazy
- **THEN** odpowiedź nazywa to awarią modułu, a nie brakiem danych

#### Scenario: Dostawca nieosiągalny przy obejmowaniu obserwacją

- **WHEN** operator obejmuje obserwacją wydarzenie, a dostawca nie odpowiada
- **THEN** odpowiedź nazywa dostawcę jako przyczynę
- **AND** żadna niekompletna obserwacja nie zostaje zapisana

