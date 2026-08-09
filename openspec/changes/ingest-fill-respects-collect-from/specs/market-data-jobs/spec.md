## ADDED Requirements

### Requirement: Kawałek jest ograniczony swoim oknem, nie tylko liczbą świec

Kawałek ma dwie krawędzie i obie MUST być wiążące. Sama liczba świec, na jaką kawałek został
wyliczony, starszej krawędzi nie pilnuje: liczba liczy świece, a okno liczy kalendarz, i dla
instrumentu zamkniętego przez część tygodnia te dwie rzeczy rozjeżdżają się o połowę — kawałek
policzony na okno od stycznia do sierpnia dostaje tyle świec, ile jest w oknie sięgającym jesieni
poprzedniego roku. Moduł MUST nazwać starszą krawędź kawałka jako moment w żądaniu do gatewaya
(`capital-market-data` spec, „Historia jest stronicowana poza limit providera") i MUST NOT zapisać
ani jednej świecy starszej niż okno tego kawałka, niezależnie od tego, co przyszło w odpowiedzi.

#### Scenario: Odpowiedź sięga poniżej okna kawałka

- **WHEN** gateway odda dla kawałka świece starsze niż początek jego okna
- **THEN** moduł zapisuje wyłącznie te mieszczące się w oknie kawałka
- **AND** pokrycie odnotowane dla kawałka obejmuje jego okno, a nie okres, który świece przypadkiem
  zajęły

#### Scenario: Interwał, w którym rynek stoi przez część tygodnia

- **WHEN** operator zleca zebranie instrumentu notowanego w części doby i części tygodnia, od
  wskazanej daty
- **THEN** archiwum MUST NOT skończyć ze świecami starszymi niż ta data
- **AND** liczba faktycznie zapisanych świec MAY być mniejsza od wyceny, bo wycena liczy okresy
  kalendarza, a rynek ich wszystkich nie wypełnia

### Requirement: Kawałki pomija się w hurcie tylko na granicy providera

Kawałek, który natrafił na koniec historii providera, pozwala pominąć wszystkie kawałki stojące za
nim w kolejce — z konstrukcji starsze, z konstrukcji poza tą granicą — zamiast wydawać po żądaniu
na ponowne odkrycie tej samej krawędzi. To pominięcie jest nieodwracalne w ramach zlecenia: kawałek
pominięty nie zostanie ponowiony, bo nic nie zawiodło.

Dlatego moduł MUST pomijać w hurcie wyłącznie wtedy, gdy koniec historii stwierdził provider. Odczyt
zatrzymany na granicy, którą sam kawałek podał gatewayowi jako swoją starszą krawędź, MUST NOT
uruchomić pominięcia — o danych poniżej tej granicy taki odczyt nie dowiedział się niczego, a stoją
za nią właśnie te kawałki, które miałyby zostać pominięte.

#### Scenario: Kawałek zatrzymany na własnej krawędzi

- **WHEN** kawałek zbierze świece aż do początku swojego okna i tam się zatrzyma
- **THEN** kawałki starsze od niego w tym samym zleceniu zostają do wykonania
- **AND** zlecenie kończy się z pokryciem sięgającym daty, którą podał operator

#### Scenario: Provider kończy się w środku zakresu zlecenia

- **WHEN** kawałek dostanie od gatewaya stwierdzenie, że historia instrumentu się skończyła
- **THEN** moduł odnotowuje tę granicę i pomija kawałki tego zlecenia sięgające poniżej niej
- **AND** zlecenie kończy się jako ukończone, a nie nieudane
