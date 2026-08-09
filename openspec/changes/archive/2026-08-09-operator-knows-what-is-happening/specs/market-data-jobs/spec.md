## ADDED Requirements

### Requirement: Mechanizm wykonujący kawałki przeżywa własną awarię

Awaria w mechanizmie wykonującym kawałki MUST kosztować jedno podejście, a nie cały mechanizm.
Moduł MUST wykonywać kolejne kawałki po niepowodzeniu w dowolnym miejscu swojej pętli roboczej —
także poza samym sięgnięciem do providera, w przejmowaniu pracy do wykonania i w czekaniu na nią.
Przyczyna MUST zostać odnotowana w logu, a kolejne podejście MUST być poprzedzone odczekaniem, żeby
awaria trwała nie zamieniła się w pętlę bez przerwy.

Odróżnienie jest tu całą rzeczą: kawałek, który zawiódł, to jeden zapis w historii zlecenia i
pozycja do ponowienia, natomiast mechanizm, który się zatrzymał, to koniec pobierania czegokolwiek
przez cały moduł — bez żadnego wpisu w żadnym zleceniu, bo nie ma już czego zapisać. Tylko
zatrzymanie modułu MUST kończyć pętlę roboczą.

#### Scenario: Awaria przy przejmowaniu pracy

- **WHEN** próba przejęcia kolejnego kawałka do wykonania kończy się błędem
- **THEN** moduł odnotowuje przyczynę i po odczekaniu próbuje ponownie
- **AND** kawałki oczekujące zostają wykonane, gdy przyczyna ustąpi
- **AND** przywrócenie pobierania MUST NOT wymagać restartu modułu

#### Scenario: Awaria trwała

- **WHEN** przejęcie pracy zawodzi raz za razem
- **THEN** moduł nie próbuje bez przerwy, tylko z przerwą między podejściami

#### Scenario: Mechanizm jednak się zatrzymuje

- **WHEN** pętla robocza kończy się z powodu innego niż zatrzymanie modułu
- **THEN** fakt ten zostaje odnotowany w logu wraz z przyczyną
- **AND** MUST NOT być milczący, bo z zewnątrz wygląda identycznie jak brak pracy do wykonania

### Requirement: Zlecenie podaje moment swojej ostatniej aktywności

Zlecenie MUST podawać moment, w którym ostatnio cokolwiek się w nim wydarzyło — kawałek ruszył albo
się rozstrzygnął. Moment ten MUST być podawany również przy zleceniu zawężonym do jednej pary,
liczony z kawałków tej pary. Zlecenie, w którym żaden kawałek jeszcze nie ruszył, MUST podawać
moment swojego utworzenia, żeby odpowiedź na pytanie „od kiedy nic" istniała zawsze.

Sam postęp na to pytanie nie odpowiada. Kawałek pracujący od czterdziestu minut i kawałek stojący
od czterdziestu minut dają ten sam udział ukończonej pracy i tę samą liczbę świec — różni je
wyłącznie to, kiedy ostatni raz coś się ruszyło.

#### Scenario: Odczyt zlecenia w toku

- **WHEN** konsument odczytuje zlecenie, którego kawałki są w trakcie wykonywania
- **THEN** dostaje moment ostatniej aktywności obok postępu i liczby świec

#### Scenario: Zlecenie stoi

- **WHEN** żaden kawałek nie ruszył ani nie rozstrzygnął się od dłuższej chwili
- **THEN** moment ostatniej aktywności pozostaje ten sam przy kolejnych odczytach
- **AND** MUST NOT przesuwać się z upływem czasu, bo zlecenie jest nadal odczytywane

#### Scenario: Zlecenie dopiero utworzone

- **WHEN** zlecenie zostało utworzone, a żaden jego kawałek jeszcze nie ruszył
- **THEN** moment ostatniej aktywności jest momentem utworzenia zlecenia

#### Scenario: Odczyt zawężony do pary

- **WHEN** konsument odczytuje zlecenie zawężone do jednej pary
- **THEN** dostaje moment ostatniej aktywności wyliczony z kawałków tej pary
- **AND** aktywność innej pary tego samego zlecenia MUST NOT go przesuwać
