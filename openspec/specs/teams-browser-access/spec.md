# teams-browser-access Specification

## Purpose
Kto może wołać moduł z przeglądarki, na jakich warunkach moduł uznaje tożsamość ustaloną przed
nim i czego o cudzych zespołach nie ujawnia temu, kto nie jest ich właścicielem.
## Requirements
### Requirement: Zespół i jego przebiegi należą do operatora, który je zapisał

Zespół MUST być przypisany do tożsamości, która go utworzyła. Odczyt zespołu, jego rewizji
i przebiegów MUST być ograniczony do tej tożsamości, a wywołanie od kogo innego MUST być
odrzucone, także wtedy, gdy niesie poprawny identyfikator zespołu lub przebiegu.

Odmowa dostępu do cudzego zespołu MUST być nieodróżnialna od odpowiedzi o zespole
nieistniejącym — różnica między nimi mówi obcemu, że zespół istnieje, i pozwala wyliczyć, ile
ich jest.

#### Scenario: Wywołanie z cudzym identyfikatorem zespołu

- **WHEN** przychodzi wywołanie o zespół należący do innej tożsamości
- **THEN** moduł odmawia
- **AND** odpowiedź jest nieodróżnialna od odpowiedzi o zespole nieistniejącym

#### Scenario: Uruchomienie cudzego zespołu

- **WHEN** przychodzi żądanie uruchomienia przebiegu zespołu należącego do innej tożsamości
- **THEN** moduł odmawia i żaden przebieg nie powstaje

### Requirement: Moduł nie bierze na wiarę warstwy przed sobą

Moduł MUST dać się skonfigurować tak, że wymaga tożsamości ustalonej przez warstwę
uwierzytelniającą stojącą przed nim, i w tej konfiguracji MUST odmówić każdego wywołania,
któremu tożsamości brakuje. Moduł MUST NOT zakładać, że warstwa przed nim działa — jedna
pomyłka w konfiguracji platformy otworzyłaby inaczej płatne wywołania modelu każdemu, kto zna
adres, a tu jedno wywołanie uruchamia cały zespół, nie jedną odpowiedź.

Konfiguracja bez tego wymagania MUST być możliwa i MUST być trybem pracy lokalnej, gdzie przed
modułem nie stoi nic i nie ma tożsamości do ustalenia.

#### Scenario: Wywołanie bez tożsamości przy wymaganej tożsamości

- **WHEN** moduł wymaga tożsamości, a wywołanie jej nie niesie
- **THEN** moduł odmawia, nie wykonując żadnej pracy

#### Scenario: Praca lokalna

- **WHEN** moduł pracuje bez wymagania tożsamości
- **THEN** obsługuje wywołania i nie szuka tożsamości

### Requirement: Wywołanie z przeglądarki przychodzi z uznanego adresu

Terminal i moduł stoją pod różnymi adresami, więc przeglądarka pyta o zgodę, zanim wyśle
wywołanie niosące poświadczenie. Moduł MUST uznawać wywołania pochodzące z adresów
skonfigurowanych jako dozwolone i MUST NOT uznawać wywołań z pozostałych. Lista dozwolonych
adresów MUST być konfiguracją, nie wartością wpisaną w kod, i MUST NOT być otwarta na dowolny
adres.

Zapytanie wstępne przeglądarki poprzedza wysłanie poświadczenia i samo go nie niesie. MUST
zostać obsłużone, bo inaczej żadne wywołanie z przeglądarki nie dojdzie do skutku —
niezależnie od tego, jak poprawną tożsamość ma operator.

#### Scenario: Zapytanie wstępne przeglądarki

- **WHEN** przeglądarka pyta wstępnie o zgodę przed wywołaniem niosącym poświadczenie
- **THEN** moduł odpowiada na nie, nie wymagając tożsamości

#### Scenario: Wywołanie z adresu spoza listy

- **WHEN** wywołanie przychodzi z adresu, którego konfiguracja nie wymienia
- **THEN** moduł go nie uznaje

### Requirement: Poświadczenie nie wędruje w adresie

Poświadczenie MUST być przekazywane poza adresem wywołania. Adres wywołania odbierającego
postęp przebiegu MUST NOT nieść poświadczenia operatora, bo adres trafia do dzienników po
drodze, a poświadczenie w dzienniku przestaje być poświadczeniem.

#### Scenario: Odbieranie postępu przebiegu

- **WHEN** terminal otwiera odbiór postępu trwającego przebiegu
- **THEN** poświadczenie jedzie poza adresem
- **AND** adres zapisany po stronie serwera nie niesie poświadczenia

### Requirement: Poświadczenia nie trafiają do logów ani do odpowiedzi

Moduł MUST NOT zapisywać w dzienniku ani zwracać w odpowiedzi poświadczenia operatora, klucza
do dostawcy modeli ani ich fragmentów. Komunikat o błędzie MUST nazywać przyczynę bez cytowania
poświadczenia.

#### Scenario: Odmowa dostawcy modeli trafia do dziennika

- **WHEN** dostawca modeli odmawia z powodu klucza, a moduł zapisuje to zdarzenie
- **THEN** wpis nazywa przyczynę
- **AND** nie niesie klucza ani jego fragmentu

