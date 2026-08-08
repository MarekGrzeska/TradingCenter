## Purpose

Rozstrzyga, co archiwum w ogóle zbiera: która para symbolu i rozdzielczości jest śledzona, kto o tym
decyduje i co się dzieje z danymi, gdy decyzja zostanie cofnięta.

## ADDED Requirements

### Requirement: Śledzona para jest decyzją operatora

Moduł MUST archiwizować wyłącznie pary (symbol, rozdzielczość) jawnie wskazane przez operatora.
MUST NOT dopisywać pary samoczynnie — ani przy wyświetleniu wykresu, ani przy zapytaniu o historię.
Zbieranie danych kosztuje połączenie do providera utrzymywane bez przerwy, więc MUST być skutkiem
świadomej decyzji, a nie ubocznym efektem oglądania.

#### Scenario: Zapytanie o nieśledzoną parę

- **WHEN** konsument prosi o świece pary, która nie jest śledzona
- **THEN** moduł nie zaczyna jej archiwizować
- **AND** odpowiedź stwierdza, że ta para nie jest śledzona

#### Scenario: Operator dodaje parę

- **WHEN** operator wskazuje symbol i rozdzielczość do archiwizowania
- **THEN** para zostaje zapisana jako śledzona
- **AND** ingest zaczyna ją obsługiwać bez restartu modułu

### Requirement: Konfiguracja przeżywa restart

Lista śledzonych par MUST być trwała. Po restarcie moduł MUST podjąć archiwizowanie dokładnie tych
par, które były śledzone przed zatrzymaniem.

#### Scenario: Restart modułu

- **WHEN** moduł zostaje zatrzymany i uruchomiony ponownie
- **THEN** archiwizuje te same pary co przed zatrzymaniem
- **AND** nie wymaga ponownego wskazania ich przez operatora

### Requirement: Usunięcie zatrzymuje zbieranie, ale nie kasuje danych

Operator MUST móc przestać śledzić parę. Usunięcie MUST zatrzymać zbieranie i zwolnić połączenie do
providera, ale MUST NOT usuwać świec już zebranych — archiwum, które kasuje dane przy zmianie
konfiguracji, nie jest archiwum.

#### Scenario: Operator usuwa parę ze śledzonych

- **WHEN** operator przestaje śledzić parę
- **THEN** moduł zatrzymuje jej ingest i zamyka związane z nią połączenie
- **AND** świece zebrane wcześniej pozostają odczytywalne

#### Scenario: Ponowne dodanie wcześniej usuniętej pary

- **WHEN** operator ponownie zaczyna śledzić parę usuniętą wcześniej
- **THEN** moduł podejmuje zbieranie
- **AND** domyka lukę powstałą w czasie, gdy para nie była śledzona

### Requirement: Śledzone pary są wyliczalne wraz ze swoim stanem

Operator MUST móc odczytać, co jest śledzone, i dla każdej pary zobaczyć, czy zbieranie faktycznie
działa. Sama obecność na liście nie dowodzi, że dane przychodzą.

#### Scenario: Odczyt listy śledzonych par

- **WHEN** operator odczytuje śledzone pary
- **THEN** dla każdej dostaje symbol, rozdzielczość, stan połączenia oraz znacznik czasu najnowszej
  zebranej świecy

#### Scenario: Zbieranie ustało po cichu

- **WHEN** dla śledzonej pary najnowsza świeca jest starsza niż dwa jej okresy, a rynek jest otwarty
- **THEN** stan tej pary stwierdza, że zbieranie nie nadąża albo ustało

### Requirement: Liczba śledzonych par ma znany sufit

`capital-gateway` trzyma jedno połączenie do providera na parę (symbol, rozdzielczość), a provider
ogranicza liczbę sesji. Moduł MUST odmówić dodania pary ponad skonfigurowany limit i MUST nazwać
powód, zamiast po cichu przestać zbierać część danych.

#### Scenario: Próba przekroczenia limitu

- **WHEN** operator dodaje parę, gdy osiągnięto skonfigurowany limit śledzonych par
- **THEN** moduł odmawia i stwierdza, że limit został osiągnięty
- **AND** dotychczas śledzone pary działają dalej bez zmian
