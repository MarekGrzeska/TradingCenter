## MODIFIED Requirements

### Requirement: Strumień przeżywa zerwanie

Moduł MUST utrzymywać połączenie z providerem przy życiu, dopóki są subskrybenci, i MUST je
odtworzyć po zerwaniu, bez ponownego łączenia się konsumenta.

Zerwaniem jest też cisza. Połączenie, przez które provider przestał przysyłać dane, wygląda
z zewnątrz identycznie jak rynek, który stanął — a jest awarią, po której nic samo nie wróci:
zmierzone 24 sierpnia 2026, gdy jeden pokój milczał czternaście godzin, podczas gdy 28 innych,
w tym pokoje tego samego instrumentu, publikowało od 47 do 265 kwotowań na 25 sekund. Moduł MUST
więc uznać brak danych rynkowych przez czas dłuższy niż własny próg za zerwanie i przejść tą samą
drogą co po zamknięciu połączenia — status, ponowne połączenie, odtworzone subskrypcje.

Mierzone MUST być **dane** — kwotowania i świece — a nie każda ramka. Utrzymanie połączenia przy
życiu jest wymianą, na którą provider odpowiada niezależnie od tego, czy nadal obsługuje
subskrypcję, więc próg liczony od dowolnej ramki przespałby całą tamtą awarię. Tego, czy żyje
sam transport, moduł MUST NOT używać jako odpowiedzi na to pytanie: transport w tamtych
czternastu godzinach był zdrowy.

Próg MUST być dobrany tak, żeby rynek zamknięty — cichy z definicji — nie zamieniał się w pętlę
wznowień: ruch do providera jest liczony na konto i dzielony z każdym innym odczytem tego modułu.

#### Scenario: Połączenie z providerem pada

- **WHEN** połączenie z providerem zamyka się, gdy konsumenci wciąż subskrybują
- **THEN** moduł publikuje wiadomość statusu mówiącą, że wznawia połączenie, łączy się ponownie
  i wraca do publikowania, a konsument nie musi się przełączać

#### Scenario: Bezczynny strumień

- **WHEN** z providerem nie wymieniono żadnej wiadomości dłużej, niż provider toleruje
- **THEN** moduł sam utrzymuje połączenie przy życiu

#### Scenario: Połączenie żyje, ale milczy

- **WHEN** połączenie z providerem jest otwarte, a nie przyszły przez nie żadne dane rynkowe
  dłużej niż próg ciszy, podczas gdy konsumenci wciąż subskrybują
- **THEN** moduł traktuje je jak zerwane: publikuje status wznawiania, zamyka je i łączy się
  ponownie
- **AND** po ponownym połączeniu wraca do publikowania bez udziału konsumenta

#### Scenario: Provider odpowiada na utrzymanie połączenia, ale nie przysyła danych

- **WHEN** przez połączenie idą wyłącznie odpowiedzi na utrzymanie połączenia albo odmowy
- **THEN** MUST NOT być to czytane jako dowód, że subskrypcja jest obsługiwana

#### Scenario: Rynek zamknięty

- **WHEN** cisza trwa, bo rynek instrumentu jest zamknięty
- **THEN** moduł MUST NOT wznawiać połączenia w kółko z częstotliwością progu ciszy

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

Zamknięcie od providera nie jest jedynym dowodem, że okres minął — i czekanie na nie jako na
jedyny dowód zostało zmierzone 24 sierpnia 2026: wszystkie cztery pokoje tygodniowe trzymały
świecę otwartą 17 sierpnia i doklejały do niej ceny z 24 sierpnia, bo zamknięcie tamtego tygodnia
nie przyszło. Nominalna długość okresu jest bezpiecznym **górnym** ograniczeniem upływu czasu,
więc kwotowanie późniejsze niż początek trzymanej świecy o całą tę długość MUST być czytane jako
okres, który na pewno się skończył: moduł MUST NOT rozciągnąć nim tamtej świecy i MUST ustalić
granicę na nowo.

Ustalenie granicy MUST NOT zależeć od tego, czy akurat przyszło kwotowanie. Pokój bez granicy pyta
o nią z własnego zegara — inaczej pojedyncza cisza kosztuje całą dobę bez świecy w budowie, a nie
tyle, ile ta cisza naprawdę trwała.

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

#### Scenario: Kwotowanie starsze niż cała długość okresu trzymanej świecy

- **WHEN** na rozdzielczości bez stałej granicy przychodzi kwotowanie późniejsze niż początek
  trzymanej świecy o całą nominalną długość jej okresu, a provider nie zamknął tamtej świecy
- **THEN** moduł MUST NOT rozciągnąć nim trzymanej świecy
- **AND** ustala granicę na nowo od providera, zanim opublikuje cokolwiek dla nowego okresu

#### Scenario: Pokój bez granicy i bez kwotowań

- **WHEN** moduł nie ma ustalonej granicy okresu dla pary w rozdzielczości dziennej albo
  tygodniowej, a kwotowania nie przychodzą
- **THEN** moduł pyta providera o bieżący okres z własnego zegara, nie czekając na kwotowanie

#### Scenario: Provider nie odpowiada na pytanie o granicę

- **WHEN** moduł nie jest w stanie ustalić bieżącego okresu od providera
- **THEN** moduł nie publikuje świecy w budowie dla tej rozdzielczości i nie publikuje wartości
  opartej na zgadniętej granicy
- **AND** kwotowania są publikowane dalej, bo one granicy okresu nie potrzebują

#### Scenario: Dołączający dostaje świecę złożoną przez moduł

- **WHEN** konsument subskrybuje parę, dla której moduł trzyma świecę okresu już zakończonego,
  a świecy tej nie zamknął provider
- **THEN** moduł podaje ją jako świecę w budowie, nie jako ostateczną
- **AND** jako ostateczną MUST podawać wyłącznie świecę zamkniętą przez providera, bo konsument
  zapisuje to, co ostateczne

#### Scenario: Subskrybent dołącza w środku okresu

- **WHEN** konsument subskrybuje w trakcie trwania okresu
- **THEN** świeca w budowie, którą dostaje, odzwierciedla wyłącznie kwotowania widziane od
  podłączenia modułu, a moduł stwierdza, że świeca jest w budowie, a nie ostateczna
