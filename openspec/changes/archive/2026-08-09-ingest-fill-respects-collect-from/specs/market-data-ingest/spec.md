## MODIFIED Requirements

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
