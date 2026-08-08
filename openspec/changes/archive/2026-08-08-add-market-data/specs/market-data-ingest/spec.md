## Purpose

Opisuje, jak świece trafiają do archiwum: co przychodzi na żywo, co jest dociągane wstecz, jak
domykana jest luka po przerwie i ile ruchu do providera moduł ma prawo zająć.

## ADDED Requirements

### Requirement: Nasłuch na żywo dla każdej śledzonej pary

Moduł MUST utrzymywać subskrypcję strumienia `capital-gateway` dla każdej śledzonej pary i zapisywać
świece w chwili ich zamknięcia. Subskrypcja MUST być wznawiana po zerwaniu, dopóki para pozostaje
śledzona.

#### Scenario: Świeca się zamyka

- **WHEN** strumień przynosi zamkniętą świecę śledzonej pary
- **THEN** moduł zapisuje ją w archiwum

#### Scenario: Połączenie ze strumieniem pada

- **WHEN** subskrypcja zostaje zerwana, a para nadal jest śledzona
- **THEN** moduł ponawia połączenie z rosnącym odstępem między próbami
- **AND** po wznowieniu domyka lukę powstałą w czasie przerwy

### Requirement: Uzupełnianie wstecz sięga po historię

Moduł MUST umieć dociągnąć świece starsze niż moment rozpoczęcia śledzenia, korzystając z odczytu
historii `capital-gateway`. MUST NOT stronicować sam — gateway robi to za limitem tysiąca świec na
żądanie i ta logika MUST NOT być powielana.

#### Scenario: Nowo dodana para

- **WHEN** operator zaczyna śledzić parę, dla której archiwum nie ma nic
- **THEN** moduł dociąga historię wstecz do skonfigurowanej głębokości
- **AND** zapisuje zakres, który udało się pokryć

#### Scenario: Provider nie ma starszych danych

- **WHEN** uzupełnianie dochodzi do końca historii dostępnej u providera
- **THEN** moduł zatrzymuje się, co nie jest błędem
- **AND** zapisuje ten punkt jako najstarszą granicę pokrycia

### Requirement: Restart domyka lukę

Każde zatrzymanie modułu zostawia okres bez danych. Moduł MUST przy starcie, dla każdej śledzonej
pary, dociągnąć okres między najnowszą posiadaną świecą a chwilą bieżącą.

#### Scenario: Start po przerwie

- **WHEN** moduł startuje, a najnowsza świeca pary jest starsza niż jeden jej okres
- **THEN** moduł dociąga brakujący przedział, zanim uzna parę za bieżącą

#### Scenario: Start bez przerwy

- **WHEN** moduł startuje, a najnowsza świeca pary jest bieżąca
- **THEN** moduł nie wysyła żadnego żądania uzupełniającego

### Requirement: Ruch do gatewaya ma budżet

`capital-gateway` przepuszcza dziesięć żądań na sekundę na całe konto, dzieląc ten limit z ruchem
interaktywnym z terminala. Głębokie uzupełnianie to dziesiątki żądań pod rząd, więc moduł MUST
ograniczyć liczbę równoczesnych uzupełnień i MUST NOT dopuścić, by zagłodziły odczyt wywołany przez
operatora.

#### Scenario: Kilka par wymaga uzupełnienia naraz

- **WHEN** uzupełnienia wymaga więcej par, niż wynosi skonfigurowana równoległość
- **THEN** moduł wykonuje je kolejno, zamiast wysyłać wszystkie naraz

#### Scenario: Uzupełnianie w toku, a operator prosi o dane

- **WHEN** operator odczytuje świece w trakcie trwającego uzupełniania
- **THEN** odczyt jest obsłużony z archiwum i nie czeka na zakończenie uzupełniania

### Requirement: Ingest raportuje swój postęp i porażki

Uzupełnianie może trwać dziesiątki minut i zawodzić na pojedynczych parach. Moduł MUST udostępniać
stan tej pracy — co jest w toku, co się powiodło, co zawiodło i dlaczego — zamiast pozostawiać to
w logach.

#### Scenario: Uzupełnianie się kończy

- **WHEN** uzupełnianie pary dobiega końca
- **THEN** moduł odnotowuje liczbę zebranych świec oraz pokryty przedział czasu

#### Scenario: Uzupełnianie zawodzi

- **WHEN** uzupełnianie pary kończy się błędem
- **THEN** moduł odnotowuje przyczynę w postaci czytelnej dla operatora
- **AND** pozostałe pary są uzupełniane dalej
