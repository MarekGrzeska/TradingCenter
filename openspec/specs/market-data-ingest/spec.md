## Purpose

Opisuje, jak świece trafiają do archiwum: co przychodzi na żywo, co jest dociągane wstecz, jak
domykana jest luka po przerwie i ile ruchu do providera moduł ma prawo zająć.
## Requirements
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
historii `capital-gateway`. Uzupełnianie MUST być wykonywaniem kawałka zlecenia — jednej pary w
jednym oknie czasu — a nie pojedynczym sięgnięciem o głębokości branej z konfiguracji. Wewnątrz
kawałka moduł MUST NOT stronicować sam: gateway robi to za limitem tysiąca świec na żądanie i ta
logika MUST NOT być powielana. Podział zakresu na kawałki MUST NOT być mylony ze stronicowaniem —
kawałek jest jednostką, która osobno się udaje, osobno zawodzi i osobno się ponawia, a każdy z nich
to jedno żądanie do gatewaya.

Zostaje jedna droga bez zlecenia: para wzięta pod opiekę wprost, bez kreatora. Dla niej moduł
domyka lukę cicho, sam — i to domknięcie MUST NOT sięgać dalej wstecz niż `collect_from` tej pary,
czyli moment, od którego historia ma być pokryta, wskazany przez operatora albo wyliczony
z domyślnej głębokości, gdy operator nic nie wskazał (`market-data-tracking` spec, „Para niesie
moment, od którego ma być pokryta"). Dla pary bez jawnie wskazanego momentu `collect_from`
i skonfigurowana głębokość mówią to samo, więc dla niej nic się nie zmienia; dla pary z jawnym,
płytszym momentem cichy fill MUST zatrzymać się na nim, a nie sięgać dalej tylko dlatego, że
skonfigurowana głębokość jest większa.

Żadna z tych dróg MUST NOT zapisać świecy starszej niż własna starsza krawędź — okno kawałka albo
`collect_from` pary. Liczba świec tej krawędzi nie pilnuje i pilnować nie może: liczba liczy świece,
a krawędź jest momentem, i dla instrumentu notowanego przez część tygodnia te dwie rzeczy rozjeżdżają
się o połowę. Krawędź MUST zostać nazwana gatewayowi jako moment (`capital-market-data` spec,
„Historia jest stronicowana poza limit providera") i MUST zostać sprawdzona jeszcze raz przy
zapisie — to, co ląduje w archiwum, jest obietnicą tego modułu, nie obietnicą do oddelegowania.

#### Scenario: Nowo dodana para

- **WHEN** operator zaczyna śledzić parę, dla której archiwum nie ma nic
- **THEN** moduł dociąga historię wstecz do momentu wskazanego w zleceniu
- **AND** zapisuje zakres, który udało się pokryć

#### Scenario: Kawałek to jedno żądanie

- **WHEN** moduł wykonuje kawałek zlecenia
- **THEN** wysyła do gatewaya jedno żądanie o historię dla okna tego kawałka
- **AND** nie dzieli tego okna na kolejne żądania po stronie modułu

#### Scenario: Para wzięta pod opiekę z jawną, płytszą datą OD

- **WHEN** para jest śledzona z momentem, od którego ma być pokryta, płytszym niż skonfigurowana
  domyślna głębokość, a cichy fill domyka dla niej lukę
- **THEN** fill dociąga historię wstecz najwyżej do tego momentu
- **AND** MUST NOT zapisać ani jednej świecy starszej niż on, także wtedy, gdy gateway odda
  w odpowiedzi coś starszego

#### Scenario: Provider nie ma starszych danych

- **WHEN** uzupełnianie dochodzi do końca historii dostępnej u providera
- **THEN** moduł zatrzymuje się, co nie jest błędem
- **AND** zapisuje ten punkt jako najstarszą granicę pokrycia
- **AND** kawałki zlecenia sięgające dalej wstecz są pomijane, a nie oznaczane jako nieudane

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

