## Purpose

Zestaw narzędzi, które moduł publikuje klientowi MCP: na jakie pytanie o archiwum
odpowiada każde z nich, co obiecuje ich opis, i czego w zestawie nie ma — nigdy.

## ADDED Requirements

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

#### Scenario: Model zaczyna bez wiedzy o symbolach

- **WHEN** operator pyta o „Nasdaqa", a model nie zna symbolu używanego przez archiwum
- **THEN** zestaw pozwala mu znaleźć symbol i sprawdzić, czy jest zbierany, przed
  zapytaniem o cenę

#### Scenario: Ostatnia cena niesie swój wiek

- **WHEN** narzędzie odpowiada ostatnią ceną
- **THEN** odpowiedź MUST nieść moment świecy i to, ile czasu od niego minęło

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
