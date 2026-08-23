# strategy-runtime Specification

## Purpose
Wspólna maszyneria wokół wpisów: skąd biorą się fakty, kiedy wolno oceniać, co jest
zapisywane i czego moduł nie robi nigdy — w szczególności: nie dotyka konta.
## Requirements
### Requirement: Ocena zapada wyłącznie na domkniętej świecy

Pętla platformy MUST oceniać strategię dopiero wtedy, gdy świeca jej rozdzielczości jest
domknięta. Świeca formująca się MUST NOT uczestniczyć w faktach.

Sygnał pojawiający się i znikający w trakcie świecy to najstarsza pułapka tej klasy
systemów; świeca formująca się w archiwum dodatkowo zaniża swój zasięg po restarcie
strumienia — jest do patrzenia, nie do decydowania.

#### Scenario: Fakty dla świecy formującej się

- **WHEN** bieżąca świeca rozdzielczości strategii nie jest domknięta
- **THEN** ocena dla tej świecy nie zostaje wykonana

### Requirement: Fakty pochodzą z archiwum, jedną drogą

Fakty MUST pochodzić z opublikowanego kontraktu archiwum świec — z tego samego katalogu
wskaźników, który czyta terminal i agenci. Platforma MUST NOT liczyć własnych wskaźników
ani sięgać po świece inną drogą. Wpis deklarujący wskaźnik, którego katalog archiwum nie
ogłasza, MUST być odrzucony przy rejestracji z powodem nazywającym ten wskaźnik.

Drugie wyliczenie tej samej matematyki to dwie odpowiedzi na jedno pytanie, rozjeżdżające
się przy pierwszej poprawce po tamtej stronie — ta sama racja, dla której wyzwalacze
zespołów czytają rynek narzędziami, a nie własnym kodem.

#### Scenario: Wpis nazywa wskaźnik spoza katalogu archiwum

- **WHEN** rejestrowany wpis deklaruje fakt o wskaźniku, którego archiwum nie ogłasza
- **THEN** rejestracja zostaje odrzucona z powodem nazywającym wskaźnik

### Requirement: Dziura w danych nie jest odpowiedzią

Gdy zakres potrzebny do oceny niesie niedopokryte okno, ocena MUST zakończyć się odmową
z powodem nazywającym pokrycie — nie sygnałem policzonym na tym, co akurat było. Odmowa
z tego powodu MUST być odróżnialna w zapisie od odmowy strategii.

Wskaźnik policzony przez dziurę wygląda jak wskaźnik; różnica wychodzi dopiero w księgowości.
Odmowa z powodu danych musi być widoczna osobno, bo jej lekarstwem jest zlecenie dociągnięcia
historii, a nie strojenie strategii.

#### Scenario: Zakres z niedopokrytym oknem

- **WHEN** fakty dla oceny wymagają zakresu, w którym archiwum zgłasza niedopokrycie
- **THEN** ocena kończy się odmową nazywającą pokrycie jako powód
- **AND** odmowa jest w zapisie odróżnialna od odmowy strategii

### Requirement: Platforma nie ma drogi do konta

Moduł MUST NOT wykonywać niczego na rachunku: nie składa, nie zmienia i nie zamyka zleceń,
nie woła bramy dostawcy ani narzędzi konta. Tryb obserwacyjny jest jedynym trybem tego
modułu; wykonanie pozostaje przy zespołach agentów i ich limitach. Nie SHALL istnieć
konfiguracja, ustawienie ani tryb, który tę granicę przesuwa.

Granica przebiega w specyfikacji, a jej przesunięcie kosztuje zmianę tego dokumentu —
dokładnie tak, jak w powierzchni narzędzi archiwum. Sygnał i wykonanie w jednym procesie
to system, którego wyłączenie wymaga odwagi; sygnał osobno to system, którego wyłączenie
wymaga usunięcia wyzwalacza.

#### Scenario: Strategia produkuje sygnał wejścia

- **WHEN** ocena kończy się decyzją o wejściu
- **THEN** decyzja zostaje zapisana i opublikowana powierzchniami modułu
- **AND** żadne zlecenie nie powstaje

### Requirement: Każda ocena zostaje zapisana i daje się odtworzyć

Każda ocena MUST zostać zapisana wraz z faktami, na których stanęła, i wersją zestawu
parametrów. Odtworzenie oceny z zapisu MUST dawać decyzję identyczną z zapisaną.

To jest dziennik systemowy strategii: bez snapshotu wejścia decyzja jest anegdotą, a spór
„czemu system wszedł" nie ma rozstrzygnięcia.

#### Scenario: Odtworzenie zapisanej oceny

- **WHEN** zapisana ocena zostaje odtworzona z jej faktów i wersji parametrów
- **THEN** wynik odtworzenia jest identyczny z decyzją zapisaną

### Requirement: Platforma bez strategii jest stanem wspieranym

Moduł MUST startować i serwować swoje powierzchnie także wtedy, gdy katalog nie ma żadnej
aktywnej strategii; powierzchnie odpowiadają wtedy pustką, nie błędem. Zatrzymanie jednej
strategii MUST NOT zatrzymywać pozostałych.

To samo wsparcie ma workbench bez narzędzi: stan „nic nie obserwujemy" jest poprawną
konfiguracją, a droga odwrotu od strategii to jej dezaktywacja, nie wdrożenie.

#### Scenario: Start bez aktywnych strategii

- **WHEN** moduł startuje, a żadna strategia nie jest aktywna
- **THEN** moduł serwuje, a powierzchnie odpowiadają pustymi listami

#### Scenario: Dezaktywacja jednej z wielu strategii

- **WHEN** operator dezaktywuje jedną z aktywnych strategii
- **THEN** pozostałe strategie oceniają dalej bez przerwy

