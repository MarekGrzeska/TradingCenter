# polymarket-data-ingest Specification

## Purpose
Opisuje, skąd biorą się ceny w archiwum: w jakim takcie próbkowane są obserwowane rynki, jak
dociągana jest przeszłość, jak domykana luka po przerwie i co się dzieje, gdy dostawca odmawia.
## Requirements
### Requirement: Obserwowany rynek jest próbkowany w stałym takcie

Moduł MUST próbkować cenę każdego wyniku nierozstrzygniętego rynku należącego do obserwowanego
wydarzenia, w takcie branym z konfiguracji. Próbkowanie MUST ruszyć dla nowo objętego obserwacją
wydarzenia bez restartu modułu i MUST ustać dla wydarzenia, którego obserwację zakończono, oraz dla
rynku rozstrzygniętego.

Takt jest ustawieniem, nie stałą wpisaną w kod, bo jego wartość mnoży się przez liczbę
obserwowanych wyników i to ona wyznacza ruch do dostawcy.

#### Scenario: Nowa obserwacja

- **WHEN** wydarzenie zostaje objęte obserwacją
- **THEN** jego rynki są próbkowane od najbliższego taktu
- **AND** moduł nie wymaga restartu

#### Scenario: Rynek rozstrzygnięty w trakcie pracy

- **WHEN** obserwowany rynek zostaje rozstrzygnięty
- **THEN** przestaje być próbkowany
- **AND** pozostałe rynki tego wydarzenia są próbkowane dalej

### Requirement: Przeszłość jest dociągana, a nie tylko próbkowana

Moduł MUST umieć uzupełnić historię ceny wyniku wstecz z szeregu czasowego udostępnianego przez
dostawcę, zamiast znać wyłącznie chwile, w których jego własne próbkowanie akurat działało.
Uzupełnianie MUST ruszać przy objęciu wydarzenia obserwacją i MUST sięgać wstecz najwyżej do
skonfigurowanej głębokości albo do granicy tego, co dostawca ma.

Uzupełnianie MUST być wykonywane oknami, z których każde osobno się udaje, osobno zawodzi i osobno
jest ponawiane. Nieudane okno MUST NOT zatrzymywać pozostałych ani MUST NOT zostać zapisane jako
zakres zebrany. Szerokość okna MUST wynikać z tego, co dostawca przyjmuje w jednym żądaniu, i MUST
być ustawieniem, a nie liczbą wpisaną w kod — dostawca MAY ją zmienić, a moduł MUST NOT wtedy
przestać uzupełniać w milczeniu.

Obie krawędzie okna MUST być sprawdzone **przy zapisie**, nie tylko wysłane w żądaniu. Odpowiedź
dostawcy MAY wykraczać poza okno, o które zapytano — to, co ląduje w archiwum, jest obietnicą tego
modułu, nie obietnicą do oddelegowania, a punkt zapisany poza sprawdzonym oknem czyni „zebrany
zakres" twierdzeniem szerszym niż to, co zweryfikowano.

#### Scenario: Odpowiedź wykracza poza żądane okno

- **WHEN** dostawca oddaje dla okna uzupełniania punkty spoza jego krawędzi
- **THEN** moduł zapisuje wyłącznie punkty mieszczące się w oknie
- **AND** zebrany zakres obejmuje to okno, a nie zakres, który odpowiedź przyniosła

#### Scenario: Nowo objęte obserwacją wydarzenie

- **WHEN** wydarzenie zostaje objęte obserwacją, a archiwum nie ma dla niego nic
- **THEN** moduł dociąga historię jego wyników wstecz
- **AND** zapisuje zakres, który udało się pokryć

#### Scenario: Jedno okno zawodzi

- **WHEN** uzupełnianie jednego okna kończy się błędem
- **THEN** pozostałe okna są uzupełniane dalej
- **AND** zakres nieudanego okna MUST NOT uchodzić za zebrany

### Requirement: Przerwa jest domykana, a nie porzucana

Każde zatrzymanie modułu zostawia okres bez próbek. Moduł MUST przy starcie, dla każdego
obserwowanego, nierozstrzygniętego wyniku, uzupełnić okres między najświeższą posiadaną próbką
a chwilą bieżącą. Ta sama reguła MUST obowiązywać po przerwie w dostępie do dostawcy, która trwała
dłużej niż takt próbkowania.

#### Scenario: Start po przerwie

- **WHEN** moduł startuje, a najświeższa próbka obserwowanego wyniku jest starsza niż takt
  próbkowania
- **THEN** moduł uzupełnia brakujący przedział

#### Scenario: Start bez przerwy

- **WHEN** moduł startuje, a próbki obserwowanych wyników są bieżące
- **THEN** moduł nie wysyła żadnego żądania uzupełniającego

### Requirement: Porażka próbkowania nie jest ceną

Moduł MUST NOT zapisywać próbki zastępczej, gdy dostawca nie odpowiedział, odmówił albo oddał
odpowiedź, której nie da się zinterpretować jako ceny. W szczególności MUST NOT powtarzać
ostatniej znanej ceny jako próbki bieżącego momentu — seria z powtórzoną ceną wygląda jak rynek,
który stoi, a nie jak zbieranie, które zawiodło.

Powtarzające się porażki MUST być widoczne w stanie obserwacji, a nie wyłącznie w logu.

#### Scenario: Dostawca nie odpowiada

- **WHEN** odpytanie o cenę wyniku kończy się błędem
- **THEN** żadna próbka dla tego momentu nie zostaje zapisana
- **AND** moduł ponawia w kolejnym takcie

#### Scenario: Porażki się powtarzają

- **WHEN** próbkowanie wyniku zawodzi przez kilka taktów pod rząd
- **THEN** stan tej obserwacji stwierdza, że zbieranie nie działa, wraz z przyczyną

### Requirement: Ruch do dostawcy ma budżet

Dostawca ogranicza tempo odpytywania, a jego limity nie są udokumentowane. Moduł MUST ograniczać
liczbę równoczesnych wywołań i tempo ich wysyłania wartościami z konfiguracji oraz MUST wycofywać
się z rosnącym odstępem po odpowiedzi mówiącej o przekroczeniu limitu. Uzupełnianie przeszłości
MUST NOT zagłodzić bieżącego próbkowania ani odczytu wywołanego przez operatora albo model.

#### Scenario: Uzupełnianie w toku, a takt nadchodzi

- **WHEN** trwa uzupełnianie przeszłości, a nadchodzi takt próbkowania obserwowanych rynków
- **THEN** próbkowanie zostaje wykonane

#### Scenario: Dostawca zgłasza przekroczenie limitu

- **WHEN** dostawca odrzuca wywołanie z powodu przekroczenia limitu tempa
- **THEN** moduł zwalnia tempo i ponawia z rosnącym odstępem
- **AND** MUST NOT ponawiać natychmiast w pętli

#### Scenario: Odczyt w trakcie uzupełniania

- **WHEN** konsument odczytuje historię w trakcie trwającego uzupełniania
- **THEN** odczyt jest obsłużony z archiwum i nie czeka na jego zakończenie

