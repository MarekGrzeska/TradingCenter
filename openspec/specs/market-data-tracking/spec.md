## Purpose

Rozstrzyga, co archiwum w ogóle zbiera: która para symbolu i rozdzielczości jest śledzona, kto o tym
decyduje i co się dzieje z danymi, gdy decyzja zostanie cofnięta.
## Requirements
### Requirement: Śledzona para jest decyzją operatora

Moduł MUST archiwizować wyłącznie pary (symbol, rozdzielczość) jawnie wskazane przez operatora.
MUST NOT dopisywać pary samoczynnie — ani przy wyświetleniu wykresu, ani przy zapytaniu o historię.
Zbieranie danych kosztuje połączenie do providera utrzymywane bez przerwy, więc MUST być skutkiem
świadomej decyzji, a nie ubocznym efektem oglądania. Jedna decyzja operatora MAY obejmować wiele par
naraz — ten sam instrument w kilku rozdzielczościach albo kilka instrumentów — i moduł MUST przyjąć
ją jako całość, zapisując każdą parę osobno.

#### Scenario: Zapytanie o nieśledzoną parę

- **WHEN** konsument prosi o świece pary, która nie jest śledzona
- **THEN** moduł nie zaczyna jej archiwizować
- **AND** odpowiedź stwierdza, że ta para nie jest śledzona

#### Scenario: Operator dodaje parę

- **WHEN** operator wskazuje symbol i rozdzielczość do archiwizowania
- **THEN** para zostaje zapisana jako śledzona
- **AND** ingest zaczyna ją obsługiwać bez restartu modułu

#### Scenario: Operator dodaje instrument w kilku rozdzielczościach

- **WHEN** operator wskazuje jeden symbol i cztery rozdzielczości jako jedną decyzję
- **THEN** zapisane zostają cztery pary
- **AND** ingest zaczyna obsługiwać każdą z nich bez restartu modułu

#### Scenario: Część decyzji zostaje odrzucona

- **WHEN** jedna z par w decyzji zostaje odrzucona, a pozostałe nie
- **THEN** pary przyjęte są śledzone
- **AND** moduł nazywa powód odmowy dla tej odrzuconej

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
działa. Sama obecność na liście nie dowodzi, że dane przychodzą. Para MUST nieść też moment, od
którego historia ma być pokryta, żeby dało się odróżnić parę zbieraną od tygodnia od pary, dla
której zamówiono dziesięć lat wstecz, oraz znacznik czasu najstarszej zebranej świecy — dokąd dane
faktycznie sięgają, co dla pary z niedokończonym zleceniem jest czymś innym niż zamówiona głębokość.

#### Scenario: Odczyt listy śledzonych par

- **WHEN** operator odczytuje śledzone pary
- **THEN** dla każdej dostaje symbol, rozdzielczość, stan połączenia oraz znacznik czasu najnowszej
  zebranej świecy
- **AND** moment, od którego historia tej pary ma być pokryta
- **AND** znacznik czasu najstarszej zebranej świecy, pusty dla pary, która nie zebrała jeszcze nic

#### Scenario: Zamówiona głębokość jeszcze nieosiągnięta

- **WHEN** dla pary zamówiono historię głębszą, niż zdążyła zostać zebrana
- **THEN** lista podaje osobno moment zamówiony i moment, od którego dane faktycznie są

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

### Requirement: Para niesie moment, od którego ma być pokryta

Śledzona para MUST przechowywać moment, od którego historia ma zostać pokryta, wskazany przez
operatora i przycięty do tego, co provider faktycznie ma. Moment ten MUST być trwały i MUST przeżyć
restart, bo to on mówi, dokąd sięga zobowiązanie archiwum wobec tej pary. Para dodana bez wskazanego
momentu MUST dostać go z domyślnej głębokości z konfiguracji.

#### Scenario: Para dodana z datą początku

- **WHEN** operator dodaje parę, wskazując moment, od którego chce mieć historię
- **THEN** para zapamiętuje ten moment, przycięty do najstarszego osiągalnego u providera

#### Scenario: Para dodana bez daty początku

- **WHEN** para zostaje dodana bez wskazania momentu początku
- **THEN** moduł wylicza go z domyślnej głębokości z konfiguracji i zapamiętuje

#### Scenario: Restart modułu

- **WHEN** moduł zostaje uruchomiony ponownie
- **THEN** każda śledzona para ma ten sam moment początku co przed zatrzymaniem

#### Scenario: Ponowne dodanie pary z wcześniejszą datą

- **WHEN** operator dodaje parę już śledzoną, wskazując moment wcześniejszy niż zapamiętany
- **THEN** para zapamiętuje ten wcześniejszy moment
- **AND** powstaje zlecenie dociągnięcia brakującego, starszego zakresu

