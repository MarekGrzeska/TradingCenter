# market-mcp-tools Specification

## Purpose
Zestaw narzędzi, które moduł publikuje klientowi MCP: na jakie pytanie o archiwum
odpowiada każde z nich, co obiecuje ich opis, i czego w zestawie nie ma — nigdy.
## Requirements
### Requirement: Zestaw narzędzi wyłącznie czyta

Moduł MUST publikować wyłącznie narzędzia, których wykonanie nie zmienia stanu żadnego
innego modułu ani archiwum. Żadne narzędzie MUST NOT rozpoczynać zbierania pary, kasować
danych, zlecać pracy ani zmieniać konfiguracji czegokolwiek.

Nie SHALL istnieć konfiguracja, ustawienie ani tryb, który dokłada do zestawu narzędzie
zapisujące. Przełącznik jest obietnicą, że kiedyś się go przestawi; granica przebiega w
specyfikacji, a jej przesunięcie kosztuje zmianę tego dokumentu.

#### Scenario: Lista narzędzi nie zawiera zapisu

- **WHEN** klient MCP prosi o listę narzędzi
- **THEN** każde narzędzie na liście odpowiada na pytanie, nie wykonuje polecenia
- **AND** na liście MUST NOT być narzędzia rozpoczynającego zbieranie pary ani kasującego
  cokolwiek

#### Scenario: Model prosi o skasowanie danych

- **WHEN** model formułuje prośbę „przestań zbierać US100 i skasuj jego świece"
- **THEN** nie ma narzędzia, którym mógłby to zrobić
- **AND** odpowiedź nazywa to zakresem modułu, a nie chwilową odmową

### Requirement: Zestaw odpowiada na pytania o archiwum

Zestaw MUST pozwalać modelowi dojść od pytania operatora do odpowiedzi bez wiedzy
zdobytej gdzie indziej: co archiwum zbiera, jak nazywa się instrument, co jest
zweryfikowane, ile wynosi ostatnia cena, jak wyglądał przebieg i co się w oknie stało.

Odpowiedź o cenie MUST nieść wiek świecy, z której pochodzi. Cena bez momentu jest
liczbą, o której nie wiadomo, czy opisuje teraz, czy piątkowe zamknięcie.

Odpowiedź o cenie MUST być najprawdziwszą ceną, jaką archiwum ma: gdy okres jest w toku,
MUST pochodzić z niego, a nie z ostatniego zamkniętego. Zamknięcie sprzed trzydziestu pięciu
godzin jest poprawną odpowiedzią na inne pytanie niż to, które operator zadał.

Cena z okresu w toku MUST być oznaczona jako taka. Model, który nie wie, że okres się nie
zamknął, poda jej maksimum i minimum jako zakres dnia — a te poszerzą się jeszcze przed
zamknięciem. Zakres okresu w toku MUST NOT być podany jako zakres zamknięty.

Gdy model nie wskaże rozdzielczości, zestaw MUST pozwolić wybrać ją archiwum. Odpowiedź MUST
nazywać rozdzielczość, z której pochodzi, bo może się różnić od domyślnej. Rozdzielczość
wskazaną przez model MUST uszanować.

Brak ceny bieżącej MUST nazywać swój powód, odróżniając rynek zamknięty od zbierania, które
stoi mimo otwartego rynku.

#### Scenario: Model zaczyna bez wiedzy o symbolach

- **WHEN** operator pyta o „Nasdaqa", a model nie zna symbolu używanego przez archiwum
- **THEN** zestaw pozwala mu znaleźć symbol i sprawdzić, czy jest zbierany, przed
  zapytaniem o cenę

#### Scenario: Ostatnia cena niesie swój wiek

- **WHEN** narzędzie odpowiada ostatnią ceną
- **THEN** odpowiedź MUST nieść moment świecy i to, ile czasu od niego minęło

#### Scenario: Cena w trakcie sesji

- **WHEN** operator pyta o cenę pary, której rynek jest otwarty i której okres trwa
- **THEN** odpowiedź pochodzi z okresu w toku, a nie z ostatniego zamkniętego
- **AND** stwierdza, że okres jest w toku
- **AND** nazywa rozdzielczość, z której pochodzi

#### Scenario: Cena po zamknięciu rynku

- **WHEN** operator pyta o cenę pary, której rynek jest zamknięty
- **THEN** odpowiedź pochodzi z ostatniej świecy zamkniętej, z jej wiekiem
- **AND** stwierdza, że rynek jest zamknięty, a nie że danych brak

#### Scenario: Rynek otwarty, a ceny bieżącej nie ma

- **WHEN** rynek pary jest otwarty, a archiwum nie ma dla niej okresu w toku
- **THEN** odpowiedź stwierdza to jako stan zbierania
- **AND** MUST NOT przedstawić tego jako ciszy rynku ani jako braku pary w archiwum

#### Scenario: Pytanie o parę, której nikt nie zbiera

- **WHEN** model pyta o symbol nieobecny wśród zbieranych par
- **THEN** odpowiedź MUST nazwać to wprost i odesłać do narzędzia wypisującego zbierane
  pary

### Requirement: Zestaw odpowiada na pytania o wskaźniki

Zestaw MUST pozwalać modelowi zbudować poprawne żądanie obliczenia wskaźnika wyłącznie z
tego, co sam publikuje: katalogu z parametrami i ich wartościami domyślnymi oraz opisu
pojedynczego wpisu. Model MUST NOT musieć znać wskaźnika z nazwy z góry.

Wynik obliczenia MUST być domyślnie zredukowany do stanu bieżącego — wartości ostatnich,
nie pełnych serii. Pełna seria MUST być rzeczą, o którą prosi się osobno.

#### Scenario: Katalog wystarcza do zbudowania żądania

- **WHEN** model czyta katalog i wybiera z niego wpis
- **THEN** ma z niego nazwy parametrów, ich wartości domyślne i dozwolone zakresy
- **AND** zbudowane z tego żądanie jest poprawne bez dodatkowego pytania

#### Scenario: Wskaźnik spoza katalogu

- **WHEN** model prosi o wskaźnik, którego w katalogu nie ma
- **THEN** odpowiedź MUST nazwać, że takiego wpisu nie ma, i odesłać do katalogu
- **AND** MUST NOT podstawić w jego miejsce wpisu podobnego z nazwy

### Requirement: Opis narzędzia jest częścią kontraktu

Opis narzędzia jest jedyną rzeczą, którą model o nim wie, więc MUST być traktowany jak
kontrakt, a nie jak komentarz. Każde publikowane narzędzie MUST nieść opis, typowane
parametry, wpisany sufit swojej odpowiedzi oraz jawnie nazwane jednostki, strefę czasową
i stronę ceny, z której liczone są świece.

#### Scenario: Narzędzie bez kompletnego opisu

- **WHEN** do zestawu trafia narzędzie bez opisu, bez wpisanego sufitu albo bez nazwanych
  jednostek
- **THEN** MUST to wywrócić test powierzchni narzędzi, zanim moduł zostanie wdrożony

#### Scenario: Czas jest jednoznaczny

- **WHEN** narzędzie przyjmuje albo zwraca moment w czasie
- **THEN** jego opis MUST nazywać strefę, a odpowiedź MUST podawać moment w UTC

### Requirement: Powierzchnia narzędzi ma zapisany sufit

Cały zestaw — opisy, schematy wejścia i schematy wyjścia razem — jest czytany przez model w
**każdej** turze rozmowy, więc jego rozmiar jest kosztem, nie szczegółem implementacji.
Moduł MUST trzymać zserializowaną postać tego, co ogłasza, poniżej sufitu zapisanego w jego
własnym teście, i MUST wywrócić ten test, gdy sufit zostanie przekroczony.

Moduł MUST NOT publikować w schemacie rzeczy, które nie niosą modelowi informacji ponad to,
co sam schemat już mówi. Sufit bez tej zasady byłby budżetem wydawanym na rusztowanie
zamiast na treść.

Sufit jest liczbą do zmierzenia i do obniżenia, a nie granicą naturalną: podniesienie go
MUST być świadomą zmianą tego testu, nie skutkiem ubocznym dodania narzędzia.

#### Scenario: Zestaw urósł ponad sufit

- **WHEN** zmiana dokłada narzędzie, pole albo akapit opisu, po którym zserializowany
  zestaw przekracza sufit
- **THEN** test powierzchni narzędzi MUST wywrócić się, nazywając zmierzoną wielkość i sufit
- **AND** moduł MUST NOT zostać wdrożony, dopóki jedno z dwóch nie zostanie zmienione świadomie

#### Scenario: Schemat bez rusztowania

- **WHEN** model czyta ogłoszony schemat narzędzia
- **THEN** schemat MUST NOT nieść nazw pól powtórzonych jako ich własne etykiety ani
  wartości domyślnych dla odpowiedzi, której model nie konstruuje
- **AND** MUST nadal nieść każde pole, jego typ i to, czy jest wymagane
