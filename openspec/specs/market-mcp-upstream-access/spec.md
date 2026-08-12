# market-mcp-upstream-access Specification

## Purpose
Warunki, na jakich moduł łączy się z archiwum: czym się przed nim przedstawia, jakich
żądań nie wykonuje nigdy i skąd wie, że kontrakt, który czyta, jest wciąż tym samym.
## Requirements
### Requirement: Tryb połączenia jest wybrany jednoznacznie, nie zgadnięty

Konfiguracja MUST wskazywać dokładnie jeden tryb dostępu do archiwum: tożsamość wobec
adresu zdalnego albo pętla zwrotna bez niej. Konfiguracja nazywająca oba tryby naraz albo
żaden MUST być odrzucona przy starcie, zanim moduł zacznie odpowiadać na cokolwiek.

Adres inny niż pętla zwrotna bez skonfigurowanej tożsamości MUST być odmową. Moduł nie
przechowuje hasła do archiwum i nie ma czego rotować.

#### Scenario: Adres zdalny bez tożsamości

- **WHEN** moduł startuje ze wskazanym adresem archiwum spoza pętli zwrotnej i bez
  skonfigurowanej tożsamości
- **THEN** MUST odmówić startu z komunikatem nazywającym brakujące ustawienie

#### Scenario: Pętla zwrotna bez tożsamości

- **WHEN** moduł startuje ze wskazanym adresem w pętli zwrotnej i bez tożsamości
- **THEN** startuje i łączy się z lokalnym archiwum

#### Scenario: Oba tryby naraz

- **WHEN** konfiguracja niesie i tożsamość, i ustawienie wybierające tryb lokalny
- **THEN** moduł MUST odmówić startu, zamiast wybrać jeden z nich

### Requirement: Do archiwum idą wyłącznie żądania czytające

Moduł MUST NOT wykonywać wobec archiwum żądania, które tworzy, zmienia albo kasuje
cokolwiek. Jedynym dozwolonym żądaniem metodą inną niż czytająca jest obliczenie
wskaźników, które nie zmienia stanu archiwum, a metody tej używa wyłącznie dlatego, że
specyfikacja obliczenia nie mieści się w adresie.

Ograniczenie to MUST być sprawdzane testem na kliencie, a nie wyłącznie pilnowane przy
review. Klient, przez który przechodzi każde żądanie, jest jedynym miejscem, w którym da
się to sprawdzić raz dla całego modułu.

#### Scenario: Klient odmawia żądania zmieniającego

- **WHEN** kod modułu próbuje wykonać wobec archiwum żądanie tworzące, zmieniające albo
  kasujące
- **THEN** klient MUST je odrzucić
- **AND** MUST to wywrócić testy modułu

#### Scenario: Obliczenie wskaźników jest dozwolone

- **WHEN** narzędzie prosi archiwum o obliczenie wskaźników
- **THEN** żądanie przechodzi, mimo że jego metoda nie jest metodą czytającą

### Requirement: Kontrakt archiwum jest sprawdzany, nie zakładany

Moduł MUST NOT importować kodu archiwum. Kształty, których używa, MUST być opisane u
siebie, a zgodność z opublikowanym kontraktem MUST być sprawdzana automatycznie: dla
każdego pola, po które moduł sięga, testy MUST potwierdzać, że kontrakt je publikuje.

Sprawdzenie MUST działać bez uruchomionego archiwum. Sprawdzenie wymagające działającej
usługi jest sprawdzeniem, którego nikt nie uruchamia, a to jest dokładnie ten sposób, w
jaki dwie kopie kontraktu się rozjeżdżają.

#### Scenario: Pole znika z kontraktu

- **WHEN** archiwum przestaje publikować pole, po które moduł sięga
- **THEN** MUST to wywrócić testy modułu, zanim zmiana zostanie wdrożona

#### Scenario: Sprawdzenie bez działającego archiwum

- **WHEN** testy modułu są uruchamiane bez działającego archiwum
- **THEN** zgodność z kontraktem MUST być mimo to sprawdzona

### Requirement: Wołanie archiwum ma skończony czas i jedno ponowienie

Każde wywołanie archiwum MUST mieć górną granicę czasu oczekiwania. Po jej przekroczeniu
moduł MUST odpowiedzieć odmową nazywającą awarię, a nie czekać dłużej, niż klient MCP jest
gotów czekać.

Wywołanie zakończone błędem serwera MAY zostać ponowione jeden raz. Każde żądanie modułu
jest czytające, więc ponowienie nie może niczego zdublować.

#### Scenario: Archiwum nie odpowiada w czasie

- **WHEN** archiwum nie odpowiada w wyznaczonym czasie
- **THEN** narzędzie MUST odpowiedzieć odmową nazywającą awarię archiwum

#### Scenario: Jednorazowa awaria serwera

- **WHEN** archiwum odpowiada błędem serwera, a ponowione żądanie kończy się powodzeniem
- **THEN** narzędzie MUST oddać odpowiedź, nie odmowę
