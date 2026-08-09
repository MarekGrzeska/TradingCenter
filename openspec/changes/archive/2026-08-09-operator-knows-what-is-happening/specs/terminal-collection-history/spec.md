## ADDED Requirements

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

## MODIFIED Requirements

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
