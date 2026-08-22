## Purpose

Powierzchnia narzędzi, którą platforma publikuje klientowi MCP: wyłącznie odczyt stanu
strategii i decyzji, z jednym narzędziem zaprojektowanym wprost pod wyzwalacze zespołów.

## ADDED Requirements

### Requirement: Zestaw narzędzi wyłącznie czyta

Platforma MUST publikować wyłącznie narzędzia, których wykonanie nie zmienia stanu platformy
ani żadnego innego modułu. Żadne narzędzie MUST NOT aktywować ani dezaktywować strategii,
zmieniać zestawów parametrów, kasować decyzji ani uruchamiać backtestu. Nie SHALL istnieć
konfiguracja dokładająca do zestawu narzędzie zapisujące, a wymóg MUST być sprawdzany testem.

Zmiany stanu platformy są sprawą operatora i przechodzą przez REST; model dostaje odpowiedzi
na pytania. To ta sama granica, którą trzyma powierzchnia archiwum — i z tego samego powodu:
narzędzie zapisujące jest o jeden import od procesu, który pisze.

#### Scenario: Lista narzędzi nie zawiera zapisu

- **WHEN** klient MCP prosi o listę narzędzi
- **THEN** każde narzędzie na liście odpowiada na pytanie o stan strategii lub decyzji
- **AND** na liście MUST NOT być narzędzia zmieniającego konfigurację ani dane

### Requirement: Liczba oczekujących setupów jest warunkiem do zawieszenia wyzwalacza

Zestaw MUST zawierać narzędzie zwracające dla wskazanej strategii liczbę oczekujących
setupów jako pole liczbowe, nadające się wprost na warunek progowy wyzwalacza zespołów.
Wartość zwrócona wyzwalaczowi MUST być tą samą wartością, którą przeczyta uruchomiony
zespół — z tego samego zapisu decyzji.

To jest zamierzony szew między deterministycznym rdzeniem a zespołami agentów: rdzeń
znajduje kandydata, wyzwalacz budzi zespół, zespół czyta tę samą decyzję. Wyzwalacz
reagujący na inną wartość niż ta, którą zobaczy zespół, byłby gorszy niż brak wyzwalacza.

#### Scenario: Wyzwalacz zespołu budzi się na kandydacie

- **WHEN** ocena kończy się decyzją o wejściu, a wyzwalacz zespołu porównuje liczbę
  oczekujących setupów z progiem
- **THEN** kolejne sprawdzenie warunku widzi wartość powiększoną o tę decyzję
- **AND** zespół uruchomiony wyzwalaczem odczytuje narzędziami tę samą decyzję

#### Scenario: Strategia bez oczekujących setupów

- **WHEN** wskazana strategia nie ma oczekujących setupów
- **THEN** narzędzie odpowiada wartością zero, nie błędem

### Requirement: Powierzchnia zna tożsamość wołającego

Powierzchnia narzędzi MUST być dostępna wyłącznie transportem sieciowym i MUST podlegać
tej samej regule tożsamości wołającego, co powierzchnie pozostałych modułów: w środowisku
produkcyjnym wołający spoza listy dopuszczonych aplikacji MUST być odrzucony, zanim
zobaczy odpowiedź.

#### Scenario: Wołający spoza listy dopuszczonych aplikacji

- **WHEN** w środowisku produkcyjnym narzędzie woła aplikacja spoza listy dopuszczonych
- **THEN** wywołanie zostaje odrzucone
- **AND** odpowiedź nie niesie żadnych danych platformy
