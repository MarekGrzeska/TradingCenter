## REMOVED Requirements

### Requirement: Przebieg kończy się zapisaną rekomendacją, a nie zleceniem

**Reason**: To było ograniczenie fazy 1, postawione świadomie i na czas: zanim zespół dostanie
skutki nieodwracalne, trzeba sprawdzić, czy w ogóle produkuje powtarzalne przebiegi. Ta zmiana
daje zestaw narzędzi zmieniających stan rachunku, więc zdanie „zestaw nie zawiera narzędzia
składającego zlecenie" przestaje być prawdziwe i nie da się go utrzymać jako wymogu.

**Migration**: Zespół nadal kończy rekomendacją, jeżeli żaden jego agent nie ma przypisanego
narzędzia zapisującego — i tak wygląda każda rewizja zapisana wcześniej. Co wolno zespołowi
zrobić z rachunkiem i w jakich granicach, opisuje `teams-trading`; komu wolno wołać serwer
zapisu — `trading-mcp-transport`.

## ADDED Requirements

### Requirement: Przebieg, który ruszył rachunek, niesie to w śladzie obok wypracowanej pracy

Ślad przebiegu, w którym padło wywołanie zmieniające stan rachunku, MUST nieść zarówno to, co
agenci wypracowali, jak i wywołania, które wykonali, wraz z ich skutkiem. Jedno bez drugiego
MUST NOT być podane jako komplet.

Rekomendacja bez zleceń nie mówi, co się naprawdę stało; zlecenia bez rekomendacji nie mówią,
dlaczego. Eksperyment porównuje jedno z drugim, więc ślad musi je trzymać razem.

#### Scenario: Przebieg zakończony złożonym zleceniem

- **WHEN** przebieg kończy się po tym, jak agent złożył zlecenie
- **THEN** ślad niesie wypracowaną pracę agentów oraz złożone zlecenie z jego skutkiem

#### Scenario: Przebieg przerwany po złożeniu zlecenia

- **WHEN** operator przerywa przebieg już po tym, jak agent złożył zlecenie
- **THEN** ślad zlecenia pozostaje zapisany
- **AND** zlecenie MUST NOT zostać cofnięte przez samo przerwanie przebiegu

### Requirement: Powód zatrzymania odróżnia granicę zleceń od granicy kosztu

Status zatrzymanego przebiegu MUST nazywać, która granica go zatrzymała. Zatrzymanie z powodu
wyczerpanej liczby zleceń MUST być odróżnialne od zatrzymania z powodu kosztu.

Operator reaguje na jedno i drugie inaczej: wyczerpany koszt to droższy eksperyment, wyczerpane
zlecenia to zespół, który chciał handlować więcej, niż mu wolno — i to drugie jest wynikiem
eksperymentu, a nie jego awarią.

#### Scenario: Przebieg zatrzymany granicą zleceń

- **WHEN** przebieg zostaje zatrzymany po wyczerpaniu dopuszczalnej liczby zleceń
- **THEN** jego status nazywa granicę zleceń jako przyczynę
- **AND** jest to inny powód niż zatrzymanie z powodu kosztu
