## MODIFIED Requirements

### Requirement: Śledzone pary są wyliczalne wraz ze swoim stanem

Operator MUST móc odczytać, co jest śledzone, i dla każdej pary zobaczyć, czy zbieranie faktycznie
działa. Sama obecność na liście nie dowodzi, że dane przychodzą. Para MUST nieść też moment, od
którego historia ma być pokryta, żeby dało się odróżnić parę zbieraną od tygodnia od pary, dla
której zamówiono dziesięć lat wstecz, oraz znacznik czasu najstarszej zebranej świecy — dokąd dane
faktycznie sięgają, co dla pary z niedokończonym zleceniem jest czymś innym niż zamówiona głębokość.

Para MUST nieść także liczbę zebranych świec oraz szacowaną objętość, jaką te świece zajmują.
Zakres dat mówi, dokąd dane sięgają, ale nie mówi, ile ich jest: para z rocznym zakresem i jedną
świecą w środku wygląda tak samo jak para pokryta gęsto. Objętość MUST być podana jako szacunek
wyprowadzony z liczby świec — ta sama liczba na świecę, którą moduł podaje przy wycenie zlecenia,
żeby zamówione i zebrane dało się porównać.

#### Scenario: Odczyt listy śledzonych par

- **WHEN** operator odczytuje śledzone pary
- **THEN** dla każdej dostaje symbol, rozdzielczość, stan połączenia oraz znacznik czasu najnowszej
  zebranej świecy
- **AND** moment, od którego historia tej pary ma być pokryta
- **AND** znacznik czasu najstarszej zebranej świecy, pusty dla pary, która nie zebrała jeszcze nic
- **AND** liczbę zebranych świec oraz szacowaną objętość, jaką zajmują

#### Scenario: Para, która nie zebrała jeszcze nic

- **WHEN** dla pary nie zebrano ani jednej świecy
- **THEN** liczba świec wynosi zero, a szacowana objętość zero
- **AND** MUST NOT być podana jako brak danej — zero jest tu odpowiedzią, nie niewiedzą

#### Scenario: Zamówiona głębokość jeszcze nieosiągnięta

- **WHEN** dla pary zamówiono historię głębszą, niż zdążyła zostać zebrana
- **THEN** lista podaje osobno moment zamówiony i moment, od którego dane faktycznie są

#### Scenario: Zbieranie ustało po cichu

- **WHEN** dla śledzonej pary najnowsza świeca jest starsza niż dwa jej okresy, a rynek jest otwarty
- **THEN** stan tej pary stwierdza, że zbieranie nie nadąża albo ustało
