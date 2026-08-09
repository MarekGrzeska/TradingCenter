# terminal-collection-history Specification

## Purpose
Zakładka terminala, w której widać dociąganie danych: co i kiedy zostało zebrane dla każdego
instrumentu i każdego interwału, jak daleko zaszła praca trwająca, i skąd ponowić to, co zawiodło,
bez zdejmowania i ponownego dodawania instrumentu.
## Requirements
### Requirement: Historia dociągania jest zakładką terminala

Podgląd dociągania MUST być dostępny jako zakładka terminala, adresowalna własną ścieżką i wpisana
do rejestru zakładek na tych samych zasadach co pozostałe.

#### Scenario: Operator otwiera zakładkę

- **WHEN** operator wchodzi na ścieżkę zakładki
- **THEN** widzi dociągnięcia pogrupowane po instrumencie i interwale

#### Scenario: Odświeżenie strony

- **WHEN** operator odświeża stronę na ścieżce zakładki
- **THEN** wraca do niej, a nie do widoku domyślnego

### Requirement: Widok jest per instrument i per interwał

Zakładka MUST pokazywać dociągnięcia rozbite na instrument i interwał, a nie jedną listę zleceń.
Dla każdej takiej pary MUST być widoczne: kiedy dociąganie się odbyło, jaki zakres czasu pokryło,
ile świec zostało zapisanych oraz w jakim jest stanie.

#### Scenario: Instrument w kilku interwałach

- **WHEN** ten sam instrument był dociągany w trzech interwałach
- **THEN** operator widzi trzy osobne wiersze wyniku, po jednym na interwał
- **AND** każdy z własnym zakresem, liczbą świec i stanem

#### Scenario: Wiele dociągnięć tej samej pary

- **WHEN** ta sama para była dociągana wielokrotnie
- **THEN** zakładka pokazuje te dociągnięcia w kolejności od najnowszego
- **AND** MUST NOT pokazywać wyłącznie ostatniego, jakby wcześniejszych nie było

### Requirement: Praca w toku pokazuje mierzony postęp

Dla dociągania trwającego zakładka MUST pokazywać udział pracy ukończonej, wzięty z liczby kawałków
ukończonych wobec wszystkich, oraz liczbę świec zapisanych do tej pory. Zakładka MUST NOT pokazywać
paska, który rusza się sam z upływem czasu.

#### Scenario: Zlecenie w toku

- **WHEN** dociąganie trwa
- **THEN** zakładka pokazuje udział ukończonej pracy i liczbę świec zapisanych do tej pory
- **AND** stwierdza, która para jest właśnie obsługiwana

#### Scenario: Postęp stoi

- **WHEN** żaden kawałek nie ukończył się od ostatniego odświeżenia
- **THEN** pokazany udział nie rośnie
- **AND** zakładka nadal stwierdza, że praca trwa

### Requirement: Zakładka odświeża się sama

Zakładka MUST odpytywać o stan dociągania co dziesięć sekund, dopóki jest otwarta, żeby operator
nie odświeżał strony ręcznie. Odpytywanie MUST ustawać, gdy operator opuszcza zakładkę. Odczyt
MUST iść do bazy archiwum, nigdy do gatewaya, żeby częstsze odpytywanie nie uszczuplało budżetu
żądań do providera, za którym stoją same kawałki.

#### Scenario: Operator patrzy na trwające zlecenie

- **WHEN** zakładka jest otwarta, a zlecenie trwa
- **THEN** pokazany stan odświeża się co dziesięć sekund bez działania operatora

#### Scenario: Nieudane odświeżenie

- **WHEN** odpytanie zawodzi, a na ekranie są już wiersze
- **THEN** wiersze pozostają, a zakładka mówi, że ostatnie odświeżenie się nie udało
- **AND** MUST NOT zastępować danych pustym ekranem z powodu jednego nieudanego odpytania

#### Scenario: Operator przechodzi na inną zakładkę

- **WHEN** operator opuszcza zakładkę
- **THEN** odpytywanie ustaje

### Requirement: Zakończone dociąganie jest wyraźnie zakończone

Dociąganie zakończone powodzeniem MUST być pokazane w sposób jednoznacznie odróżniający je od
trwającego i od nieudanego, wraz z liczbą zebranych świec i pokrytym zakresem. Pokrycie częściowe
MUST NOT wyglądać jak pełny sukces.

#### Scenario: Wszystko się udało

- **WHEN** dociąganie kończy się bez ani jednego nieudanego kawałka
- **THEN** zakładka pokazuje je jako zakończone powodzeniem, kolorem zarezerwowanym dla powodzenia
- **AND** podaje liczbę zebranych świec i pokryty zakres

#### Scenario: Pokrycie częściowe

- **WHEN** dociąganie kończy się z częścią kawałków nieudanych
- **THEN** zakładka pokazuje je jako częściowe, z udziałem zakresu faktycznie pokrytego
- **AND** wylicza przyczyny porażek

### Requirement: Nieudane dociąganie ponawia się z zakładki

Zakładka MUST pozwalać ponowić dociąganie zakończone porażką albo częściowo, bez zdejmowania
instrumentu z archiwizowanych. Ponowienie MUST dotyczyć wyłącznie tego, co zawiodło, a zakładka
MUST powiedzieć, co zostanie ponowione, zanim to zrobi.

#### Scenario: Operator ponawia

- **WHEN** operator wybiera ponowienie przy dociąganiu zakończonym porażką
- **THEN** zakładka mówi, które pary i zakresy zostaną ponowione
- **AND** po zatwierdzeniu dociąganie rusza, a wiersz przechodzi w stan trwającego

#### Scenario: Ponowienie samo zawodzi

- **WHEN** żądanie ponowienia nie dochodzi do archiwum
- **THEN** zakładka mówi, że ponowienia nie udało się zlecić, i zostawia możliwość spróbowania raz
  jeszcze
- **AND** MUST NOT pokazywać wiersza jako trwającego

### Requirement: Zakładka odróżnia brak historii od braku odpowiedzi

Zakładka MUST odróżnić „nic jeszcze nie było dociągane" od „nie udało się o to zapytać".

#### Scenario: Archiwum nieosiągalne

- **WHEN** zakładka nie może odczytać historii dociągania
- **THEN** mówi, że archiwum jest nieosiągalne, wraz z możliwością ponowienia odczytu
- **AND** MUST NOT pokazywać pustej listy

#### Scenario: Nic jeszcze nie dociągano

- **WHEN** archiwum odpowiada, że żadne dociąganie nie miało miejsca
- **THEN** zakładka stwierdza to wprost i wskazuje, gdzie dodać instrument do archiwizowanych

