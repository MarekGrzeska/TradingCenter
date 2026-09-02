# terminal-strategy Specification

## Purpose
Ekran operatora nad platformą strategii: co widzi, co może zacząć i zatrzymać, i dlaczego
jest w przeważającej części listą odmów, a nie listą okazji.
## Requirements
### Requirement: Odmowy są treścią ekranu, nie jego szumem

Lista decyzji MUST domyślnie pokazywać także decyzje odmowne i MUST NOT wymagać od
operatora włączenia ich osobno. Rodzaj odmowy — czy odmówiła strategia, czy zabrakło
pokrycia danych, czy uciął ją limit platformy — MUST być widoczny przy decyzji, nie tylko
w jej szczegółach.

Dobrze zaprojektowana strategia odrzuca zdecydowaną większość obserwowanych świec, więc
ekran pokazujący wyłącznie setupy byłby pusty przez większość czasu — i pusty dokładnie
wtedy, gdy operator pyta „czemu nic się nie dzieje". To pytanie jest odpowiadane czytaniem
odmów, a nie ich ukrywaniem.

Rodzaj ma być widoczny, bo lekarstwa są różne: brak pokrycia odpowiada się zleceniem
uzupełnienia historii, odmowę strategii — przeczytaniem strategii. Ekran mieszający je
w jedno „brak sygnału" wysyła operatora w złą stronę.

#### Scenario: Ekran po dniu bez setupów

- **WHEN** operator otwiera listę decyzji dla strategii, która przez cały dzień odmawiała
- **THEN** widzi te odmowy wraz z powodem każdej z nich
- **AND** nie widzi pustej listy

#### Scenario: Odmowa z braku danych obok odmowy strategii

- **WHEN** lista zawiera decyzję odrzuconą z powodu niedopokrytego zakresu i decyzję
  odrzuconą przez samą strategię
- **THEN** operator rozróżnia je bez otwierania szczegółów

### Requirement: Obserwację da się założyć i zatrzymać z ekranu

Operator MUST móc założyć obserwację — wskazać strategię, instrument i zestaw parametrów —
oraz włączyć ją i wyłączyć. Wyłączenie MUST zatrzymywać ocenianie tej pary i MUST NOT
usuwać zapisanych decyzji: to, co system zdecydował, pozostaje czytelne po tym, jak
przestał obserwować.

Bez tego moduł nie ma jak zacząć pracować. W chwili powstania tego ekranu platforma nie
obserwuje ani jednej pary i nie istnieje żadna droga, którą pierwsza obserwacja mogłaby
powstać.

#### Scenario: Pierwsza obserwacja

- **WHEN** operator zakłada obserwację nad strategią i instrumentem
- **THEN** obserwacja jest aktywna
- **AND** kolejne decyzje tej pary pojawiają się na liście decyzji

#### Scenario: Zatrzymanie jednej z wielu

- **WHEN** operator wyłącza jedną z aktywnych obserwacji
- **THEN** pozostałe pracują dalej
- **AND** decyzje wyłączonej pozostają czytelne

#### Scenario: Parametr poza zakresem

- **WHEN** operator zakłada obserwację z wartością parametru spoza zadeklarowanego zakresu
- **THEN** ekran odmawia, nazywając parametr
- **AND** obserwacja nie powstaje

### Requirement: Katalog strategii jest do czytania, nie do edycji

Ekran MUST przedstawiać katalog strategii jako stan tego obrazu — wpisy, ich fakty
i zakresy parametrów — i MUST NOT oferować tworzenia, zmieniania ani usuwania wpisu.

Wpis strategii jest kodem w obrazie, nie wierszem w tabeli. Przycisk sugerujący inaczej
obiecywałby operatorowi coś, czego ten moduł nie potrafi, i to obietnicę o logice, która
decyduje o pieniądzach.

#### Scenario: Operator szuka sposobu na zmianę strategii

- **WHEN** operator ogląda wpis w katalogu
- **THEN** widzi jego fakty i zakresy parametrów
- **AND** nie ma na ekranie akcji zmieniającej sam wpis

### Requirement: Ekran niczego nie zleca na rachunku

Ekran MUST NOT oferować złożenia, zmiany ani zamknięcia zlecenia, i MUST NOT przedstawiać
setupu jako pozycji. Setup jest odczytem.

Moduł pod tym ekranem nie ma drogi do rachunku i mieć jej nie będzie; ekran sugerujący
inaczej byłby jedynym miejscem w systemie, które obiecuje wykonanie tam, gdzie go nie ma.

#### Scenario: Setup na ekranie

- **WHEN** ekran pokazuje decyzję o wejściu
- **THEN** nie ma przy niej akcji składającej zlecenie
- **AND** nie jest ona przedstawiona jako otwarta pozycja

### Requirement: Decyzję da się przeczytać do tego, na czym stanęła

Szczegóły decyzji MUST pokazywać powód, a dla decyzji o wejściu także kierunek, poziomy
i stosunek zysku do ryzyka. Dla każdej decyzji MUST być dostępne odczytanie faktów, na
których stanęła, oraz wersji parametrów, którą została policzona.

Decyzja bez tego jest anegdotą. Spór „czemu system wszedł" rozstrzyga się odczytaniem tego,
co system wtedy widział, a nie tego, co widać dzisiaj.

#### Scenario: Operator sprawdza setup

- **WHEN** operator otwiera decyzję o wejściu
- **THEN** widzi kierunek, wejście, obronę, cel i stosunek zysku do ryzyka
- **AND** ma dostęp do odczytów, na których ta decyzja stanęła

### Requirement: Raporty backtestu są czytane, a nie uruchamiane

Zachowane raporty backtestu MUST być czytelne z ekranu wraz z modelem kosztów, wersją
parametrów i zakresem danych, na których powstały. Ekran MUST NOT oferować uruchomienia
przebiegu.

Przebieg po latach świec to minuty pracy i trzymanie żądania przez cały ten czas; jest
komendą właśnie po to, żeby długi przebieg nie był czymś, co da się odpalić przypadkiem.
Raport bez modelu kosztów nie jest wynikiem, więc ekran pokazujący raport bez nich
pokazywałby liczbę, nie odpowiedź.

#### Scenario: Operator czyta raport

- **WHEN** operator otwiera zachowany raport backtestu
- **THEN** widzi metryki wraz z modelem kosztów, wersją parametrów i zakresem danych

#### Scenario: Operator szuka przycisku uruchamiającego przebieg

- **WHEN** operator ogląda listę raportów
- **THEN** nie ma na ekranie akcji uruchamiającej backtest
