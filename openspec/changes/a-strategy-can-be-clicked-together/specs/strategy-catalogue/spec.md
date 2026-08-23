## MODIFIED Requirements

### Requirement: Strategia jest wpisem katalogu, nie zmianą platformy

Strategia MUST być wpisem katalogu deklarującym: fakty, których potrzebuje (wskaźnik
z katalogu archiwum, rozdzielczość, parametry), własne parametry z zakresami oraz funkcję
oceny. Wpis MAY pochodzić z dwóch źródeł — z obrazu, jako kod, albo z zapisanej rewizji
definicji — i oba źródła MUST spełniać ten sam kontrakt: runtime MUST NOT rozróżniać ich
w żaden sposób poza miejscem, z którego wpis został odczytany. Dodanie nowego wpisu z obu
źródeł MUST NOT wymagać zmiany we wspólnym runtime — pętli, bramkach, zapisie decyzji,
powierzchniach. Wymóg ten MUST być sprawdzany testem, nie pilnowany przy review.

To jest ten sam ruch, którym archiwum rozwiązało wskaźniki: kontrakt wpisu raz, maszyneria
raz, każdy kolejny wpis to jeden plik. Platforma, w której druga strategia wymaga poprawek
w pętli, nie jest platformą — jest pierwszą strategią z ambicjami. Dwa źródła wpisu nie
osłabiają tej reguły, tylko ją sprawdzają: gałąź „jeżeli wyklikana" w pętli albo
w backteście oznaczałaby, że kontrakt jednak nie wystarczał.

#### Scenario: Druga strategia wchodzi do katalogu

- **WHEN** do katalogu zostaje dodany drugi wpis strategii
- **THEN** żaden plik wspólnego runtime nie zmienia się
- **AND** obie strategie pracują równolegle na tych samych zasadach

#### Scenario: Parametr poza zadeklarowanym zakresem

- **WHEN** zestaw parametrów niesie wartość poza zakresem zadeklarowanym we wpisie
- **THEN** zestaw zostaje odrzucony z powodem nazywającym parametr i zakres

#### Scenario: Wpis z rewizji obok wpisu z obrazu

- **WHEN** platforma ocenia obserwację wskazującą rewizję definicji zapisaną w bazie
- **THEN** przechodzi ona tę samą pętlę, te same bramki i ten sam zapis decyzji co wpis kodowy
- **AND** identyfikator strategii jest odczytywany z jednej przestrzeni nazw, wspólnej dla
  obu źródeł

### Requirement: Ocena jest czystą funkcją

Funkcja oceny strategii MUST wyliczać decyzję wyłącznie z podanych faktów i parametrów:
MUST NOT wykonywać we/wy, MUST NOT czytać zegara ani innego stanu spoza argumentów. Te same
fakty i te same parametry MUST dawać tę samą decyzję. Wymóg ten MUST obowiązywać tak samo
funkcję napisaną ręcznie, jak i tę powstałą z rewizji definicji: interpreter reguły MUST być
czysty i totalny — MUST NOT wykonywać we/wy, MUST NOT czytać zegara, MUST NOT wykonywać
pętli o nieograniczonej liczbie kroków, i MUST kończyć się decyzją dla każdego wejścia,
które przeszło walidację.

Na tej własności stoi wszystko dalej: test jednostkowy na ręcznych faktach, odtworzenie
decyzji z zapisu i backtest wołający tę samą funkcję. Strategia, która „doczytuje" cokolwiek
sama, jest nietestowalna i nieodtwarzalna — czyli nie do przyjęcia w całości, nie w części.
Interpreter, który nie byłby czysty, odbierałby tę własność wszystkim wyklikanym regułom
naraz, więc jest sprawdzany tym samym testem warstwy co wpisy katalogu.

#### Scenario: Dwa wywołania na tych samych wejściach

- **WHEN** funkcja oceny zostaje wywołana dwukrotnie z identycznymi faktami i parametrami
- **THEN** obie decyzje są identyczne

#### Scenario: Wpis sięga poza argumenty

- **WHEN** funkcja oceny wpisu wykonuje we/wy lub czyta zegar
- **THEN** MUST to wywrócić testy modułu, zanim zmiana zostanie wdrożona

#### Scenario: Odczyt, który się nie ustabilizował

- **WHEN** wyrażenie reguły opiera się na odczycie, którego archiwum nie policzyło
- **THEN** ocena kończy się odmową, a nie wejściem
- **AND** powód odmowy jest tym, który definicja zadeklarowała dla nieustalonego odczytu

### Requirement: Decyzja zawsze niesie powód i pochodzenie

Wynikiem oceny MUST być decyzja: wejście albo odmowa. Odmowa MUST nieść powód. Decyzja
o wejściu MUST nieść kierunek, poziomy (wejście, obrona, cel) oraz nazwane cechy, z których
powstała jej punktacja. Każda decyzja MUST wskazywać strategię i wersję zestawu parametrów,
którą została policzona. Decyzja policzona wpisem pochodzącym z rewizji definicji MUST
wskazywać także tę rewizję; rewizja raz zapisana MUST NOT się zmienić.

„System nie handlował trzy tygodnie" musi być diagnozowalne jednym zapytaniem, a raport
z backtestu musi umieć powiedzieć, które cechy niosą przewagę — obie rzeczy stoją na tym
wymogu. Sama wersja parametrów przestaje wystarczać w chwili, gdy reguła też jest danymi:
bez rewizji pytanie „czemu to weszło" nie ma odpowiedzi, bo liczby są znane, a reguła, która
je zważyła, już nie.

#### Scenario: Setup odrzucony przez bramkę strategii

- **WHEN** ocena kończy się odmową
- **THEN** decyzja niesie powód odmowy nazywający bramkę, która ją ucięła

#### Scenario: Decyzja wraca do swojego zestawu parametrów

- **WHEN** operator czyta zapisaną decyzję
- **THEN** decyzja wskazuje wersję zestawu parametrów, którą była policzona
- **AND** ten zestaw jest odczytywalny w brzmieniu z chwili decyzji

#### Scenario: Decyzja wraca do swojej rewizji reguły

- **WHEN** operator czyta decyzję policzoną wyklikaną strategią
- **THEN** decyzja wskazuje rewizję definicji, którą była policzona
- **AND** ta rewizja jest odczytywalna w brzmieniu z chwili decyzji, mimo późniejszych zmian
  w tej samej definicji
