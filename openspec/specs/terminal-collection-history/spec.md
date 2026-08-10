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
ukończonych wobec wszystkich, liczbę świec zapisanych do tej pory oraz czas, jaki upłynął od
ostatniej aktywności zlecenia. Zakładka MUST NOT pokazywać paska, który rusza się sam z upływem
czasu.

Czas od ostatniej aktywności jest tym, co odróżnia pracę od stania w miejscu — udział ukończonej
pracy i liczba świec wyglądają w obu przypadkach identycznie, więc zlecenie, które stanęło,
poznaje się dopiero po tym, że nic się w nim nie ruszyło. Zakładka MUST wyróżnić trwające
dociąganie, w którym nic nie wydarzyło się dłużej niż przez próg bezczynności przyjęty dla
terminala, tak by odróżniało się na pierwszy rzut oka od takiego, w którym praca postępuje.

#### Scenario: Zlecenie w toku

- **WHEN** dociąganie trwa
- **THEN** zakładka pokazuje udział ukończonej pracy i liczbę świec zapisanych do tej pory
- **AND** stwierdza, która para jest właśnie obsługiwana
- **AND** podaje, ile czasu upłynęło od ostatniej aktywności zlecenia

#### Scenario: Postęp stoi

- **WHEN** żaden kawałek nie ukończył się od ostatniego odświeżenia
- **THEN** pokazany udział nie rośnie
- **AND** zakładka nadal stwierdza, że praca trwa

#### Scenario: Nic się nie dzieje dłużej niż przez próg bezczynności

- **WHEN** trwające dociąganie nie odnotowało żadnej aktywności dłużej niż przez ten próg
- **THEN** zakładka wyróżnia je spośród dociągnięć, w których praca postępuje
- **AND** czas od ostatniej aktywności jest widoczny bez otwierania czegokolwiek

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
instrumentu z archiwizowanych.

Ponowienie obejmuje całe zlecenie — wszystkie jego pary, każdy kawałek, który zawiódł — i dlatego
MUST być wywoływane z dialogu zlecenia, a nie z wiersza pojedynczej pary. Przycisk stojący przy
wierszu jednej pary obiecuje ponowienie tej pary; położenie mówi to głośniej niż jakikolwiek podpis,
a wykonuje się co innego. Zakładka MUST nazwać ponowienie ponowieniem zlecenia i MUST powiedzieć,
ile kawałków i w ilu parach zostanie ponowionych, zanim to zrobi.

#### Scenario: Operator ponawia

- **WHEN** operator wybiera ponowienie w dialogu zlecenia zakończonego porażką
- **THEN** dialog mówi, które pary i zakresy zostaną ponowione
- **AND** po zatwierdzeniu dociąganie rusza, a wiersze tego zlecenia przechodzą w stan trwającego

#### Scenario: Ponowienie stoi przy całości, nie przy parze

- **WHEN** operator patrzy na wiersz pary, której kawałki zawiodły
- **THEN** przy tym wierszu MUST NOT stać przycisk ponawiający zlecenie
- **AND** droga do ponowienia prowadzi przez dialog zlecenia

#### Scenario: Ponowienie samo zawodzi

- **WHEN** żądanie ponowienia nie dochodzi do archiwum
- **THEN** dialog zlecenia mówi, że ponowienia nie udało się zlecić, i zostawia możliwość
  spróbowania raz jeszcze
- **AND** MUST NOT pokazywać wierszy tego zlecenia jako trwających

### Requirement: Zakładka odróżnia brak historii od braku odpowiedzi

Zakładka MUST odróżnić „nic jeszcze nie było dociągane" od „nie udało się o to zapytać".

#### Scenario: Archiwum nieosiągalne

- **WHEN** zakładka nie może odczytać historii dociągania
- **THEN** mówi, że archiwum jest nieosiągalne, wraz z możliwością ponowienia odczytu
- **AND** MUST NOT pokazywać pustej listy

#### Scenario: Nic jeszcze nie dociągano

- **WHEN** archiwum odpowiada, że żadne dociąganie nie miało miejsca
- **THEN** zakładka stwierdza to wprost i wskazuje, gdzie dodać instrument do archiwizowanych

### Requirement: Skasowanie danych widać w historii

Zakładka MUST pokazywać skasowania danych obok dociągnięć, w jednym porządku czasu — dociągnięcie i
skasowanie tej samej pary to dwa zdarzenia z tej samej historii, a rozdzielone na dwie listy nie
dałyby się przeczytać jako ciąg przyczyn. Wpis o skasowaniu MUST podawać, kiedy nastąpiło, jakiej
pary dotyczyło, ile świec zostało usuniętych i jaki zakres czasu obejmowały.

Wpis o skasowaniu MUST być odróżnialny od dociągnięcia na pierwszy rzut oka i MUST NOT być pokazany
kolorem zarezerwowanym dla powodzenia — skasowanie nie jest ani sukcesem, ani porażką, tylko
odjęciem danych.

#### Scenario: Historia pary po skasowaniu

- **WHEN** operator patrzy na historię pary, której dane skasowano po wcześniejszym dociągnięciu
- **THEN** widzi oba zdarzenia, od najnowszego
- **AND** wpis o skasowaniu podaje moment, liczbę usuniętych świec i zakres czasu, który obejmowały

#### Scenario: Skasowanie odróżnia się od dociągnięcia

- **WHEN** w historii sąsiadują wpis o dociągnięciu i wpis o skasowaniu
- **THEN** operator rozróżnia je bez czytania szczegółów
- **AND** wpis o skasowaniu MUST NOT wyglądać jak zakończone powodzeniem dociąganie

#### Scenario: Instrument skasowany w całości

- **WHEN** operator skasował wszystkie interwały instrumentu
- **THEN** historia tego instrumentu jest nadal odczytywalna wraz z wpisami o skasowaniu
- **AND** MUST NOT znikać wraz z instrumentem z listy archiwizowanych

### Requirement: Historia jest ułożona od najnowszego zdarzenia

Zakładka MUST układać wszystkie wpisy jednym porządkiem czasu, od najnowszego do najstarszego,
niezależnie od instrumentu i interwału. Symbol ani interwał MUST NOT być kluczem sortowania —
wiersze pozostają per para, ale to nie one decydują, gdzie wiersz wypadnie.

Zakładka odpowiada przede wszystkim na pytanie „co się właśnie stało", a odpowiedzią na nie jest
zawsze najnowsze zdarzenie. Układ alfabetyczny stawia je w miejscu zależnym od tego, jak nazywa się
instrument, czyli — z punktu widzenia tego pytania — w przypadkowym.

#### Scenario: Zdarzenia różnych par

- **WHEN** operator zlecił dociągnięcie `US100`, a potem skasował dane `GOLD`
- **THEN** wpis o skasowaniu `GOLD` jest wyżej niż wpis o dociągnięciu `US100`
- **AND** kolejność MUST NOT zależeć od tego, jak nazywają się te instrumenty

#### Scenario: Najnowsze zdarzenie jest pierwsze

- **WHEN** operator otwiera zakładkę po zleceniu dociągnięcia
- **THEN** to dociągnięcie jest pierwszym wierszem tabeli
- **AND** operator nie musi go szukać wśród wpisów o innych instrumentach

#### Scenario: Zdarzenia z tego samego momentu

- **WHEN** dwa wpisy niosą ten sam moment
- **THEN** zakładka pokazuje oba, w kolejności stabilnej między odświeżeniami
- **AND** MUST NOT pomijać żadnego ani zmieniać ich miejscami przy kolejnym odczycie

### Requirement: Wiersz dociągnięcia otwiera dialog całego zlecenia

Wiersz zakładki pokazuje jedną parę, ale zlecenie, z którego pochodzi, obejmuje zwykle więcej par.
Zakładka MUST pozwalać otworzyć z wiersza dociągnięcia dialog całego zlecenia, w którym widać każdą
parę tego zlecenia — jej stan, postęp i liczbę świec — przyczyny wszystkich porażek oraz moment
ostatniej aktywności zlecenia.

Dialog jest jedynym miejscem, w którym zlecenie widać jako całość, i dlatego jedynym, z którego
sensownie ponawia się je w całości. Zakładka MUST NOT grupować wierszy według zleceń, żeby otwarcie
tego dialogu nie zmieniało porządku „od najnowszego zdarzenia", którym cała lista jest ułożona.

Wpis o skasowaniu danych nie pochodzi ze zlecenia i MUST NOT otwierać tego dialogu.

#### Scenario: Operator otwiera zlecenie z wiersza

- **WHEN** operator wybiera wiersz dociągnięcia
- **THEN** terminal otwiera dialog zlecenia, z którego ten wiersz pochodzi
- **AND** dialog wymienia wszystkie pary tego zlecenia, także te, których nie ma na ekranie pod nim

#### Scenario: Zlecenie z porażkami

- **WHEN** operator otwiera zlecenie, w którym część kawałków zawiodła
- **THEN** dialog podaje, ile kawałków zawiodło, w których parach i z jakich powodów

#### Scenario: Wiersz osiągalny klawiaturą

- **WHEN** operator porusza się po zakładce klawiaturą
- **THEN** wiersz dociągnięcia da się otworzyć bez użycia wskaźnika

#### Scenario: Wpis o skasowaniu

- **WHEN** operator wybiera wpis o skasowaniu danych
- **THEN** żaden dialog zlecenia się nie otwiera

### Requirement: Wpis dociągnięcia da się usunąć z zakładki

Zakładka MUST pozwalać usunąć z historii wpis dociągnięcia, żeby lista dawała się
uporządkować bez zdejmowania instrumentu i bez kasowania jego danych.

Usunięcie obejmuje całe zlecenie — wszystkie jego pary, każdy kawałek — więc MUST być
wywoływane z dialogu zlecenia, a nie z wiersza pojedynczej pary, dokładnie z tego powodu,
z którego stoi tam ponowienie: przycisk przy wierszu jednej pary obiecuje usunięcie tej
pary, a wykonałby co innego.

Zanim cokolwiek zniknie, zakładka MUST powiedzieć, ilu par i ilu kawałków dotyczy
usunięcie, oraz MUST stwierdzić wprost, że zebrane świece zostają w archiwum. Bez tego
zdania operator ma przed sobą dwie nieodwracalne operacje o nierozróżnialnych nazwach —
skasowanie danych pary i usunięcie wpisu o dociągnięciu.

Po usunięciu zakładka MUST przestać pokazywać wiersze tego zlecenia, bez odświeżania
strony przez operatora. Usunięcie MUST NOT zostawiać po sobie wpisu w historii — wpis
o skasowaniu danych mówi, że ubyło świec, a tu nie ubyło żadnej, i lista rosłaby wtedy
tak samo jak przed tą możliwością.

Zlecenia, którego archiwum nie pozwala usunąć, bo coś się w nim jeszcze dzieje, zakładka
MUST NOT pokazywać jako usuwalnego.

#### Scenario: Operator usuwa zlecenie

- **WHEN** operator wybiera usunięcie w dialogu zlecenia i je potwierdza
- **THEN** wiersze tego zlecenia znikają z zakładki bez odświeżania strony
- **AND** wiersze pozostałych zleceń i wpisy o skasowaniach danych zostają na miejscu

#### Scenario: Potwierdzenie nazywa skutek

- **WHEN** operator wybiera usunięcie w dialogu zlecenia
- **THEN** przed usunięciem widzi, ilu par i ilu kawałków ono dotyczy
- **AND** widzi stwierdzenie, że zebrane świece pozostają w archiwum

#### Scenario: Usunięcie stoi przy całości, nie przy parze

- **WHEN** operator patrzy na wiersz pary należącej do zlecenia
- **THEN** przy tym wierszu MUST NOT stać przycisk usuwający zlecenie z historii
- **AND** droga do usunięcia prowadzi przez dialog zlecenia

#### Scenario: Zlecenie w toku

- **WHEN** operator otwiera dialog zlecenia, którego kawałki jeszcze się wykonują
- **THEN** usunięcie nie jest dostępne, a dialog mówi, dlaczego
- **AND** ponowienie i pozostała treść dialogu działają jak dotąd

#### Scenario: Usunięcie zawodzi

- **WHEN** żądanie usunięcia nie dochodzi do archiwum
- **THEN** dialog zlecenia mówi, że usunięcie się nie udało, i zostawia możliwość spróbowania raz jeszcze
- **AND** wiersze tego zlecenia pozostają w zakładce

#### Scenario: Wpis o skasowaniu danych

- **WHEN** operator patrzy na wpis o skasowaniu danych pary
- **THEN** nie prowadzi z niego żadna droga do usunięcia wpisu historii
