## Purpose

Cel wiadomości: otwarta nazwa rodzaju zdarzenia, którą producent podaje zamiast adresata, i
przypisanie, przez które operator decyduje w terminalu, który adresat — a więc który bot — mówi o czym.

## ADDED Requirements

### Requirement: Producent adresuje celem, a cel jest otwarty

Wywołujący MUST móc wysłać wiadomość, podając cel zamiast nazwy adresata. Cel MUST być nazwą
kropkowaną z małych liter, cyfr, `_` i `-`, o segmentach niepustych, nie dłuższą niż 120 znaków.
Brama MUST przyjąć cel, którego wcześniej nie widziała — MUST NOT wymagać, żeby ktokolwiek
zarejestrował go z góry.

Producent może wymyślić cel w chwili wysyłki: reguła alertu ustawiona przez operatora może nieść
własny (`market.price.eurusd`). Zamknięty katalog celów oznaczałby zmianę bramy przy każdym nowym
rodzaju zdarzenia, a o to właśnie chodzi, żeby jej nie było.

#### Scenario: Cel nigdy wcześniej niewidziany

- **WHEN** wywołujący wysyła wiadomość z celem, którego brama nie zna, a przypisanie domyślne istnieje
- **THEN** brama MUST wysłać wiadomość do adresata przypisania domyślnego

#### Scenario: Cel o niedozwolonym kształcie

- **WHEN** wywołujący podaje cel z wielką literą, spacją albo pustym segmentem
- **THEN** brama MUST odmówić, nazywając dozwolony kształt, i MUST NOT wysłać niczego

### Requirement: Brama pamięta cele, nie wiadomości

Brama MUST zapamiętać każdy cel, z jakim przyszła wiadomość: kiedy zobaczyła go pierwszy i ostatni
raz oraz który wywołujący go użył. Wywołujący MUST móc zgłosić cel z opisem bez wysyłania
wiadomości, żeby operator zobaczył go i przypisał, zanim nastąpi pierwsze zdarzenie. Brama MUST NOT
zapamiętywać treści wiadomości.

`telegram-gateway-delivery` dalej obowiązuje: lista celów mówi, o czym system **umie** mówić, a nie
co powiedział.

#### Scenario: Pierwsza wiadomość z nowym celem

- **WHEN** przychodzi wiadomość z celem, którego brama dotąd nie widziała
- **THEN** cel MUST pojawić się na liście celów z czasem i nazwą wywołującego, bez treści wiadomości

#### Scenario: Cel zgłoszony z góry

- **WHEN** pakiet przy starcie zgłasza cel z opisem
- **THEN** cel MUST być na liście z tym opisem, choć żadna wiadomość z nim nie przyszła

### Requirement: Jeden cel ma co najwyżej jednego adresata

Operator MUST móc przypisać adresata do celu, do przedrostka celu albo do przypisania domyślnego
`*`. Jeden klucz przypisania MUST wskazywać co najwyżej jednego adresata. Zmiana przypisania MUST
obowiązywać od następnej wiadomości, bez restartu i bez zmiany ustawień.

#### Scenario: Przepięcie celu

- **WHEN** operator przepina cel na innego adresata, a chwilę później przychodzi wiadomość z tym celem
- **THEN** wiadomość MUST trafić do nowego adresata

#### Scenario: Przypisanie do adresata przed tapnięciem

- **WHEN** operator przypisuje cel adresatowi, który czeka jeszcze na tapnięcie
- **THEN** brama MUST przyjąć przypisanie, a wysyłka pod ten cel MUST być odmową mówiącą, że adresat jeszcze nie odbiera

### Requirement: Rozstrzyga najdłuższy pasujący przedrostek

Brama MUST wybrać adresata z przypisania o najdłuższym kluczu, który jest celem albo jego
przedrostkiem liczonym po całych segmentach, a gdy takiego nie ma — z przypisania domyślnego.

#### Scenario: Przedrostek łapie cele pod sobą

- **WHEN** istnieje przypisanie `youtube` i przychodzi wiadomość z celem `youtube.film`
- **THEN** wiadomość MUST trafić do adresata przypisania `youtube`

#### Scenario: Dokładniejsze przypisanie wygrywa

- **WHEN** istnieją przypisania `youtube` i `youtube.film`, a przychodzi wiadomość z celem `youtube.film`
- **THEN** wiadomość MUST trafić do adresata przypisania `youtube.film`

#### Scenario: Przedrostek nie tnie segmentu

- **WHEN** istnieje przypisanie `market.price` i przychodzi wiadomość z celem `market.prices`
- **THEN** przypisanie `market.price` MUST NOT zostać użyte

### Requirement: Cel bez adresata to odpowiedź, nie awaria

Gdy żadne przypisanie nie pasuje do celu, brama MUST odpowiedzieć odmową odróżnialną od każdej
innej — w szczególności od nieznanego adresata, adresata, który nie odbiera, i awarii Telegrama —
i MUST NOT wysłać niczego.

Producent musi umieć powiedzieć „nikt nie słucha” bez zgadywania z treści błędu, bo od tego zależy,
czy stawia znacznik.

#### Scenario: Brak przypisań

- **WHEN** brama nie ma żadnego przypisania i przychodzi wiadomość z celem
- **THEN** odpowiedź MUST mówić, że cel nie ma adresata, i MUST nazywać ten cel

### Requirement: Przypisania zmienia tylko operator

Przypisania MUST być zmieniane wyłącznie przez kontrakt REST. Powierzchnia narzędziowa MAY
wyliczać cele i ich adresatów, ale MUST NOT ich zmieniać.

Przypisanie przeżywa rozmowę, która by je zmieniła — tak samo jak bot i wiązanie adresata.

#### Scenario: Model szuka narzędzia przypisującego

- **WHEN** przeszukuje się powierzchnię narzędziową bramy
- **THEN** MUST NOT znaleźć się w niej narzędzie tworzące, zmieniające ani usuwające przypisanie
