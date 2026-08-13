## MODIFIED Requirements

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
