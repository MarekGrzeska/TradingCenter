## Purpose

Kontrakt REST modułu: na jakie pytania o zebrane posty odpowiada terminalowi i pocketowi, w jakim
kształcie, i dlaczego nie ma w nim ani jednej trasy zmieniającej stan.

## ADDED Requirements

### Requirement: Kontrakt wyłącznie czyta

Kontrakt MUST NOT publikować trasy, która zbiera, wzbogaca, zmienia albo kasuje cokolwiek. Zbiór
jest czynnością pętli modułu, a nie zdolnością klienta.

Odróżnia to ten moduł od `polymarket-data`, gdzie trasy zmieniające stan są, bo tam istnieje lista
obserwacji, którą operator układa. Tutaj nie ma czego układać: źródło jest zbierane w całości.

#### Scenario: Klient szuka drogi do wymuszenia zbioru

- **WHEN** klient przegląda dokument kontraktu
- **THEN** MUST NOT znaleźć trasy zapisującej, kasującej ani wymuszającej pobranie ze źródła

### Requirement: Okno i zawężenia są jawne w zapytaniu

Kontrakt MUST pozwalać pytać o posty oknem czasu — zarówno skrótem „ostatnie N godzin", jak
i parą znaczników czasu — oraz zawężać wynik po źródle, po najniższej ocenie wpływu i po temacie.
Porządek odpowiedzi MUST być określony w kontrakcie, a nie zależny od tego, jak zapytano bazę.

Kontrakt MUST pozwalać odczytać pojedynczy post po parze źródło–identyfikator, wraz z pełną
treścią i tłumaczeniem.

#### Scenario: Pytanie o okno z zawężeniem

- **WHEN** klient prosi o posty z ostatnich 24 godzin z oceną nie niższą niż 6
- **THEN** odpowiedź MUST zawierać wyłącznie posty spełniające oba warunki

#### Scenario: Okno bez sensu

- **WHEN** klient podaje okno, którego koniec jest wcześniejszy niż początek
- **THEN** kontrakt MUST odmówić z powodem nazywającym błąd, a nie zwrócić pustą listę

### Requirement: Brak odczytu jest wartością pustą, nie brakiem pola

Pola niosące odczyt modelu — tłumaczenie, tematy, ocena, nazwa modelu, moment odczytu — MUST być
w odpowiedzi zawsze, a ich brak MUST być wartością pustą. Klient MUST NOT musieć zgadywać, czy
pola nie ma, bo model milczał, czy dlatego, że kontrakt się zmienił.

#### Scenario: Post niewzbogacony w odpowiedzi

- **WHEN** klient odczytuje post, którego model nie widział
- **THEN** pola odczytu MUST być obecne i puste

### Requirement: Moduł mówi, w jakim jest stanie

Kontrakt MUST publikować trasę stanu, która niesie: moment ostatniego udanego zbioru, moment
początku zbioru, liczbę zebranych postów w bieżącym oknie, listę czynnych źródeł oraz to, czy
dostęp do modelu jest skonfigurowany.

Bez tego cisza archiwum jest nieodróżnialna od cichego dnia, a brak tłumaczeń — od modelu, który
nie miał czego tłumaczyć.

#### Scenario: Archiwum stoi

- **WHEN** ostatni udany zbiór był dawniej niż wielokrotność odstępu zbioru
- **THEN** odpowiedź o stan MUST pozwolić klientowi nazwać archiwum nieświeżym

#### Scenario: Wdrożenie bez modelu

- **WHEN** moduł działa bez skonfigurowanego dostępu do modelu
- **THEN** odpowiedź o stan MUST to mówić wprost

### Requirement: Kontrakt jest źródłem typów dla obu konsumentów

Kształt odpowiedzi MUST być opisany dokumentem OpenAPI drukowanym z modeli samego modułu, bez
uruchamiania serwera i bez bazy. Terminal i pocket MUST wyprowadzać z niego swoje typy, a rozjazd
między wygenerowanym plikiem a modułem MUST wywracać CI.

#### Scenario: Zmiana kształtu odpowiedzi

- **WHEN** moduł zmienia kształt odpowiedzi, a wygenerowany kontrakt w terminalu albo w pocket
  nie został odświeżony
- **THEN** CI MUST odmówić przejścia
