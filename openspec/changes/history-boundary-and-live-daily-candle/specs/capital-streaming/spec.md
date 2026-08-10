## MODIFIED Requirements

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
