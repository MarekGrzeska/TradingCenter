## Purpose

Strumień na żywo: co konsument dostaje po WebSockecie, gdy rynek się rusza, łącznie ze świecą,
która jeszcze się nie zamknęła, oraz co dzieje się z tym strumieniem, gdy połączenie z providerem
padnie.

## Requirements

### Requirement: Konsument subskrybuje po symbolu i rozdzielczości

Moduł MUST przyjmować subskrypcje WebSocketa wskazujące symbol i rozdzielczość świecy oraz MUST
dostarczać wyłącznie wiadomości dotyczące tej pary.

#### Scenario: Subskrypcja

- **WHEN** konsument otwiera strumień na symbol i rozdzielczość
- **THEN** dostaje wiadomość statusu, gdy strumień od providera jest żywy
- **AND** każda kolejna wiadomość dotyczy tego symbolu i tej rozdzielczości

#### Scenario: Subskrypcja bez symbolu

- **WHEN** konsument otwiera strumień, nie wskazując symbolu
- **THEN** moduł odmawia połączenia

### Requirement: Strumień niesie świece i kwotowania

Moduł MUST publikować dwa rodzaje wiadomości z danymi: świecę oznaczoną jako w budowie albo
zamkniętą oraz kwotowanie niosące bid i ask. MUST publikować także wiadomości statusu i błędu.
Żadna wiadomość MUST NOT ujawniać własnego kształtu wiadomości providera ani jego tokenów.

#### Scenario: Świeca się zamyka

- **WHEN** provider raportuje zamkniętą świecę
- **THEN** moduł publikuje wiadomość świecy oznaczoną jako zamknięta, niosącą otwarcie,
  maksimum, minimum, zamknięcie i czas początku świecy

#### Scenario: Rynek rusza się wewnątrz świecy

- **WHEN** między zamknięciami świec przychodzi kwotowanie
- **THEN** moduł publikuje wiadomość kwotowania niosącą bid, ask i znacznik czasu

#### Scenario: Provider zgłasza awarię

- **WHEN** połączenie z providerem albo subskrypcja zawodzi
- **THEN** moduł publikuje wiadomość błędu mówiącą, co zawiodło, bez poświadczeń providera w niej

### Requirement: Świeca w budowie jest składana przez moduł

Provider raportuje świecę dopiero przy jej zamknięciu, więc między zamknięciami konsument nie
widziałby żadnej świecy. Moduł MUST składać świecę w budowie z kwotowań: pierwsze kwotowanie
w okresie ją otwiera, kolejne rozciągają maksimum i minimum oraz przesuwają zamknięcie. Zamknięta
świeca od providera jest autorytatywna i MUST zastąpić tę złożoną.

Dla rozdzielczości, których granica okresu nie wynika z zegara, moduł MUST NOT jej zgadywać —
granica dzienna wyliczona z północy UTC wygląda poprawnie i jest błędna. Nie znaczy to jednak, że
moduł ma czekać na nią bezczynnie: zamknięta świeca dla rozdzielczości dziennej pada raz na dobę,
a dla tygodniowej raz na tydzień, więc konsument czekający na nią nie widzi bieżącej ceny przez
całą tę dobę albo cały ten tydzień. Moduł MUST ustalić bieżący okres od providera — tak samo jak
robi to dla świecy zamkniętej — zamiast go wyliczać, i MUST zrobić to od razu, gdy zaczyna
obsługiwać parę.

Granica raz ustalona nie obowiązuje wiecznie. Kwotowanie z okresu późniejszego niż świeca, którą
moduł trzyma, MUST NOT rozciągać tamtej świecy: świeca, której okres już minął, jest ostateczna,
a doklejenie do niej ceny z następnego okresu daje wartość, jakiej nie było w żadnym z nich. Moduł
MUST wtedy ustalić granicę na nowo od providera, zanim opublikuje cokolwiek dla nowego okresu.

#### Scenario: Pierwsze kwotowanie nowego okresu

- **WHEN** przychodzi kwotowanie, którego znacznik czasu wypada w okresie późniejszym niż bieżąca
  świeca
- **THEN** moduł publikuje świecę w budowie otwartą na tej cenie

#### Scenario: Kwotowania wewnątrz okresu

- **WHEN** w tym samym okresie przychodzą kolejne kwotowania
- **THEN** moduł publikuje świecę w budowie z rozciągniętym maksimum i minimum oraz zamknięciem
  przesuniętym na ostatnią cenę

#### Scenario: Przychodzi świeca od providera

- **WHEN** provider raportuje zamkniętą świecę okresu, który moduł składał
- **THEN** wartości providera zastępują złożone, a świeca jest publikowana jako zamknięta

#### Scenario: Rozdzielczość bez stałej granicy okresu

- **WHEN** rozdzielczość jest dzienna albo tygodniowa, a jej granica zależy od sesji rynku, nie od
  zegara
- **THEN** kwotowania rozciągają świecę bieżącego okresu, zamiast otwierać nową na granicy
  wyliczonej z zegara
- **AND** granica pochodzi wyłącznie od providera, nigdy z arytmetyki na znaczniku czasu

#### Scenario: Pierwsze kwotowanie na rozdzielczości bez stałej granicy

- **WHEN** moduł zaczyna obsługiwać parę w rozdzielczości dziennej albo tygodniowej i przychodzi
  kwotowanie, zanim provider zdążył zamknąć jakąkolwiek świecę
- **THEN** moduł ustala bieżący okres od providera i publikuje świecę w budowie dla tego okresu
- **AND** konsument MUST NOT czekać na publikację do najbliższego zamknięcia okresu

#### Scenario: Okres się przetacza, zanim provider go zamknie

- **WHEN** na rozdzielczości bez stałej granicy przychodzi kwotowanie z okresu późniejszego niż
  świeca, którą moduł trzyma, a provider nie zamknął jeszcze tamtej świecy
- **THEN** moduł ustala granicę na nowo od providera i publikuje świecę w budowie nowego okresu
- **AND** świeca poprzedniego okresu MUST NOT zostać rozciągnięta ceną z nowego

#### Scenario: Provider nie odpowiada na pytanie o granicę

- **WHEN** moduł nie jest w stanie ustalić bieżącego okresu od providera
- **THEN** moduł nie publikuje świecy w budowie dla tej rozdzielczości i nie publikuje wartości
  opartej na zgadniętej granicy
- **AND** kwotowania są publikowane dalej, bo one granicy okresu nie potrzebują

#### Scenario: Subskrybent dołącza w środku okresu

- **WHEN** konsument subskrybuje w trakcie trwania okresu
- **THEN** świeca w budowie, którą dostaje, odzwierciedla wyłącznie kwotowania widziane od
  podłączenia modułu, a moduł stwierdza, że świeca jest w budowie, a nie ostateczna

### Requirement: Jedno połączenie z providerem obsługuje wszystkich subskrybentów pary

Moduł MUST trzymać najwyżej jedno połączenie z providerem na symbol i rozdzielczość, dzielone
przez wszystkich konsumentów tej pary, i MUST je zamknąć, gdy odejdzie ostatni konsument.

#### Scenario: Dołącza drugi konsument

- **WHEN** drugi konsument subskrybuje symbol i rozdzielczość już streamowane
- **THEN** nie jest otwierane dodatkowe połączenie z providerem
- **AND** obaj konsumenci dostają te same wiadomości

#### Scenario: Odchodzi ostatni konsument

- **WHEN** rozłącza się ostatni konsument danego symbolu i rozdzielczości
- **THEN** moduł zamyka połączenie z providerem dla tej pary

### Requirement: Strumień przeżywa zerwanie

Moduł MUST utrzymywać połączenie z providerem przy życiu, dopóki są subskrybenci, i MUST je
odtworzyć po zerwaniu, bez ponownego łączenia się konsumenta.

#### Scenario: Połączenie z providerem pada

- **WHEN** połączenie z providerem zamyka się, gdy konsumenci wciąż subskrybują
- **THEN** moduł publikuje wiadomość statusu mówiącą, że wznawia połączenie, łączy się ponownie
  i wraca do publikowania, a konsument nie musi się przełączać

#### Scenario: Bezczynny strumień

- **WHEN** z providerem nie wymieniono żadnej wiadomości dłużej, niż provider toleruje
- **THEN** moduł sam utrzymuje połączenie przy życiu

### Requirement: Strona ceny zgodna z historią

Świece publikowane na strumieniu MUST używać tej samej strony ceny co świece podawane z historii.
Gdy provider raportuje obie strony zamkniętej świecy, publikowana MUST być tylko jedna.

#### Scenario: Provider raportuje obie strony ceny

- **WHEN** provider raportuje tę samą zamkniętą świecę dwa razy, po razie na stronę ceny
- **THEN** moduł publikuje dokładnie jedną świecę tego okresu, po tej samej stronie, której używa
  jego historia
