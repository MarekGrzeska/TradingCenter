## MODIFIED Requirements

### Requirement: Wynik ma jeden z czterech kształtów

Wynik wskaźnika MUST mieć dokładnie jeden z czterech kształtów: wartości na świecę, zdarzenia
w punktach, strefy cenowe albo poziomy. Wpis katalogu MUST zapowiadać, którego z nich użyje.

Wynik, którego nie dało się policzyć, MUST wrócić bez żadnego z czterech kształtów, za to
z nazwaną przyczyną. MUST być odróżnialny od wyniku policzonego pusto: brak stref to stwierdzenie,
że w tym zakresie żadnej nie było, i MUST NOT być tym samym, co niemożność ich policzenia. Wynik
z przyczyną MUST NOT być pominięty w odpowiedzi — konsument, który zamówił wskaźnik, MUST dostać
w odpowiedzi wpis o nim, cokolwiek się z nim stało.

Strefa MUST nieść granice cenowe, moment powstania i — gdy jest już zamknięta — moment zakończenia,
a także fakty o tym, czy i kiedy cena do niej weszła. Fakty te MUST dotyczyć wyłącznie żądanego
zakresu: strefa nietknięta do końca zakresu MUST NOT być opisana jako nietknięta w ogóle.

#### Scenario: Strefa wciąż otwarta

- **WHEN** strefa nie została domknięta do końca żądanego zakresu
- **THEN** odpowiedź mówi, że jej koniec jest nieustalony, zamiast podawać koniec zakresu jako koniec strefy

#### Scenario: Kształt zapowiedziany w katalogu

- **WHEN** konsument czyta wpis katalogu przed wywołaniem obliczenia
- **THEN** wie, którego z czterech kształtów się spodziewać

#### Scenario: Wynik bez kształtu, za to z przyczyną

- **WHEN** zamówionego wskaźnika nie dało się policzyć
- **THEN** wraca on w odpowiedzi z nazwaną przyczyną i bez żadnego z czterech kształtów

#### Scenario: Pusto policzony a niepoliczalny

- **WHEN** konsument porównuje wskaźnik, który nie znalazł w zakresie ani jednej strefy, ze wskaźnikiem, którego nie dało się policzyć
- **THEN** odróżnia jedno od drugiego, zamiast widzieć w obu pustą listę

### Requirement: Poziomy z wyższego interwału pochodzą z zamkniętego okresu

Poziomy wyprowadzone z rozdzielczości wyższej niż rysowana — ekstrema i otwarcia poprzedniego
okresu — MUST pochodzić z okresu, który się już zamknął, i MUST obowiązywać od jego zamknięcia,
a nie od początku serii.

Gdy archiwum nie ma dla pary serii w wymaganej rozdzielczości, moduł MUST nazwać brak przy tym
wskaźniku, a MUST NOT zwracać poziomów wyliczonych z rozdzielczości zastępczej. Brak ten
MUST NOT unieważniać pozostałych wskaźników tego samego żądania.

#### Scenario: Poziomy poprzedniego dnia na wykresie minutowym

- **WHEN** konsument prosi o poziomy dnia poprzedniego dla serii piętnastominutowej
- **THEN** dostaje je jako poziomy obowiązujące od zamknięcia tamtego dnia

#### Scenario: Brak serii w wymaganej rozdzielczości

- **WHEN** para nie jest archiwizowana w rozdzielczości, z której poziomy miałyby pochodzić
- **THEN** wynik tego wskaźnika niesie nazwany brak zamiast poziomów

### Requirement: Profil czasowy liczy się z serii minutowej

Rozkład czasu spędzonego przy cenie MUST być liczony z serii minutowej pary, także wtedy, gdy
zamówiony jest dla rozdzielczości wyższej. Odpowiedź MUST podawać rozkład, poziom o największym
udziale oraz przedział obejmujący zadany udział całości.

Gdy para nie ma serii minutowej, moduł MUST nazwać brak przy tym wskaźniku, a MUST NOT zwracać
profilu policzonego z grubszej serii. Brak ten MUST NOT unieważniać pozostałych wskaźników tego
samego żądania.

#### Scenario: Profil pod wykresem czterogodzinnym

- **WHEN** konsument prosi o profil dla serii czterogodzinnej
- **THEN** profil jest policzony z minut, a nie z czterogodzinnych świec

#### Scenario: Para bez serii minutowej

- **WHEN** para jest archiwizowana wyłącznie w rozdzielczości godzinowej
- **THEN** wynik profilu niesie nazwany brak zamiast rozkładu

## ADDED Requirements

### Requirement: Brakująca seria nie unieważnia policzonych wskaźników

Gdy część zamówionych wskaźników nie da się policzyć z powodu tego, czego archiwum nie ma,
a pozostałe da się, moduł MUST odpowiedzieć: policzone wracają policzone, niepoliczone wracają
z przyczyną. Taka odpowiedź MUST być odpowiedzią udaną, a MUST NOT być odmową.

Granica jest tu świadoma i przebiega po tym, czyj to problem. Brak serii nie jest pomyłką
wołającego — jest właściwością tego, co ktoś zdecydował się zbierać, i różni się wskaźnik po
wskaźniku. Pomyłka wołającego jest inna: nieznany identyfikator wskaźnika, parametr poza
zakresem katalogu, zakres kończący się przed swoim początkiem i żądanie ponad sufit MUST nadal
być odmową całego żądania. Cicha, częściowa odpowiedź na literówkę w identyfikatorze
przeszłaby niezauważona, a odmowa nie przechodzi.

#### Scenario: Jeden wskaźnik bez serii, reszta policzona

- **WHEN** konsument zamawia jednym żądaniem wskaźnik wymagający serii, której archiwum nie ma, oraz wskaźniki liczone z serii rysowanej
- **THEN** dostaje odpowiedź, w której te drugie są policzone, a pierwszy niesie nazwany brak

#### Scenario: Wszystkie zamówione wskaźniki bez serii

- **WHEN** żadnego z zamówionych wskaźników nie da się policzyć z powodu brakujących serii
- **THEN** odpowiedź nadal jest odpowiedzią i niesie przyczynę przy każdym z nich, zamiast być odmową

#### Scenario: Nieznany identyfikator obok policzalnych wskaźników

- **WHEN** konsument zamawia jednym żądaniem wskaźnik o identyfikatorze, którego katalog nie zna, oraz wskaźniki policzalne
- **THEN** moduł odmawia całego żądania, zamiast odpowiadać częściowo

#### Scenario: Parametr poza zakresem obok policzalnych wskaźników

- **WHEN** konsument zamawia jednym żądaniem wskaźnik z parametrem poza zakresem podanym w katalogu oraz wskaźniki policzalne
- **THEN** moduł odmawia całego żądania i mówi, jaki zakres obowiązuje

#### Scenario: Powtórzenie tego samego żądania

- **WHEN** konsument powtarza żądanie, na które dostał odpowiedź częściową, przy niezmienionym archiwum
- **THEN** dostaje tę samą odpowiedź, z tymi samymi przyczynami przy tych samych wskaźnikach
