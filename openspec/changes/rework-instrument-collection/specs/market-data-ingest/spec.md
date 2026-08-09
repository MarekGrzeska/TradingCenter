## MODIFIED Requirements

### Requirement: Uzupełnianie wstecz sięga po historię

Moduł MUST umieć dociągnąć świece starsze niż moment rozpoczęcia śledzenia, korzystając z odczytu
historii `capital-gateway`. Uzupełnianie MUST być wykonywaniem kawałka zlecenia — jednej pary w
jednym oknie czasu — a nie pojedynczym sięgnięciem o głębokości branej z konfiguracji. Wewnątrz
kawałka moduł MUST NOT stronicować sam: gateway robi to za limitem tysiąca świec na żądanie i ta
logika MUST NOT być powielana. Podział zakresu na kawałki MUST NOT być mylony ze stronicowaniem —
kawałek jest jednostką, która osobno się udaje, osobno zawodzi i osobno się ponawia, a każdy z nich
to jedno żądanie do gatewaya.

#### Scenario: Nowo dodana para

- **WHEN** operator zaczyna śledzić parę, dla której archiwum nie ma nic
- **THEN** moduł dociąga historię wstecz do momentu wskazanego w zleceniu
- **AND** zapisuje zakres, który udało się pokryć

#### Scenario: Kawałek to jedno żądanie

- **WHEN** moduł wykonuje kawałek zlecenia
- **THEN** wysyła do gatewaya jedno żądanie o historię dla okna tego kawałka
- **AND** nie dzieli tego okna na kolejne żądania po stronie modułu

#### Scenario: Provider nie ma starszych danych

- **WHEN** uzupełnianie dochodzi do końca historii dostępnej u providera
- **THEN** moduł zatrzymuje się, co nie jest błędem
- **AND** zapisuje ten punkt jako najstarszą granicę pokrycia
- **AND** kawałki zlecenia sięgające dalej wstecz są pomijane, a nie oznaczane jako nieudane

### Requirement: Ingest raportuje swój postęp i porażki

Uzupełnianie może trwać dziesiątki minut i zawodzić na pojedynczych kawałkach. Moduł MUST
udostępniać stan tej pracy — co jest w toku, co się powiodło, co zawiodło i dlaczego — zamiast
pozostawiać to w logach. Ten stan MUST być trwały: raport, który ginie przy restarcie, nie odpowiada
na pytanie „co się dociągnęło i kiedy", zadawane właśnie po restarcie.

#### Scenario: Uzupełnianie się kończy

- **WHEN** uzupełnianie kawałka dobiega końca
- **THEN** moduł odnotowuje liczbę zebranych świec oraz pokryty przedział czasu

#### Scenario: Uzupełnianie zawodzi

- **WHEN** uzupełnianie kawałka kończy się błędem
- **THEN** moduł odnotowuje przyczynę w postaci czytelnej dla operatora
- **AND** pozostałe kawałki są uzupełniane dalej

#### Scenario: Raport po restarcie

- **WHEN** moduł zostaje uruchomiony ponownie
- **THEN** wyniki uzupełnień sprzed zatrzymania są nadal odczytywalne
- **AND** uzupełnienie przerwane zatrzymaniem jest odnotowane jako przerwane, a nie trwające
