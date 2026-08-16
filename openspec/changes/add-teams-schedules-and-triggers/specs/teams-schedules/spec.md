## Purpose

Kiedy zespół rusza bez operatora: co opisuje harmonogram, którą rewizję uruchamia, kto jest
właścicielem przebiegu, którego nikt nie zamówił ręcznie, oraz co dzieje się z wyzwoleniem,
które nie mogło uruchomić przebiegu.

## ADDED Requirements

### Requirement: Harmonogram należy do operatora, który go zapisał

Harmonogram MUST nieść tożsamość operatora zapisaną w momencie jego utworzenia. Przebieg
uruchomiony z harmonogramu MUST należeć do tej samej tożsamości co harmonogram. Odczyt
i zmiana harmonogramu należącego do kogo innego MUST być nieodróżnialne od odczytu
harmonogramu, który nie istnieje.

Harmonogram ma działać wtedy, gdy przeglądarki nie ma — więc tożsamość jest kopiowana na
wiersz, a nie brana z żądania w chwili wyzwolenia. Moduł niczego tą tożsamością nie woła:
klucz modelu i tożsamość do serwera narzędzi są jego własne. To etykieta na wierszach, nie
podszywanie się.

#### Scenario: Harmonogram cudzego operatora

- **WHEN** operator prosi o harmonogram zapisany przez kogo innego
- **THEN** odpowiedź jest taka sama jak dla harmonogramu, którego nie ma

#### Scenario: Przebieg z harmonogramu na liście przebiegów

- **WHEN** harmonogram uruchamia przebieg, a operatora nie ma przy terminalu
- **THEN** przebieg jest widoczny na liście przebiegów zespołu tego samego operatora
- **AND** ślad przebiegu wskazuje harmonogram, który go uruchomił

### Requirement: Harmonogram uruchamia rewizję przypiętą, a tryb „najnowsza" jest jawnym wyborem

Harmonogram MUST nazywać rewizję, którą uruchamia. Domyślnie MUST to być rewizja przypięta —
ta, która obowiązywała w chwili zapisania harmonogramu. Śledzenie najnowszej rewizji zespołu
MAY zostać wybrane, ale MUST być zapisane w harmonogramie jawnie i MUST być widoczne dla
operatora.

Definicja zespołu jest append-only po to, żeby dwa przebiegi dało się porównać. Harmonogram
milcząco biorący „to, co akurat jest" zamieniałby edycję wieczorem w zmianę tego, co robi
robot o dziewiątej rano — bez żadnego przebiegu, który by to odnotował.

#### Scenario: Zespół zmieniony po zapisaniu harmonogramu

- **WHEN** operator zapisuje nową rewizję zespołu, którego harmonogram jest przypięty
- **THEN** kolejne wyzwolenie uruchamia rewizję przypiętą, a nie nową

#### Scenario: Harmonogram śledzący najnowszą rewizję

- **WHEN** harmonogram ma jawnie wybrany tryb „najnowsza" i zespół ma nową rewizję
- **THEN** kolejne wyzwolenie uruchamia nową rewizję
- **AND** ślad przebiegu wskazuje, która rewizja to była

### Requirement: Wyzwolenie jest przejmowane dokładnie raz

Wyzwolenie harmonogramu MUST zostać przejęte przez dokładnie jeden proces. Dwa procesy modułu
pracujące na tej samej bazie MUST NOT uruchomić dwóch przebiegów z jednego wyzwolenia.

Wdrożenie jest momentem, w którym stary kontener jeszcze odpowiada, a nowy już wstaje. Bez
przejęcia w bazie oznaczałoby to podwójny przebieg i podwójny rachunek — raz na wdrożenie.

#### Scenario: Dwa procesy przy jednym wyzwoleniu

- **WHEN** dwa procesy modułu widzą to samo należne wyzwolenie
- **THEN** przebieg rusza dokładnie jeden raz
- **AND** drugi proces nie zapisuje drugiego wyzwolenia

### Requirement: Pominięte wyzwolenia zwijają się do jednego

Jeśli moduł nie pracował przez czas obejmujący kilka należnych wyzwoleń, po powrocie MUST
uruchomić co najwyżej jeden przebieg dla danego harmonogramu i MUST NOT nadrabiać każdego
pominiętego wyzwolenia osobno. Liczba pominiętych wyzwoleń MUST zostać zapisana.

Zespół czyta rynek taki, jaki jest teraz. Pięć przebiegów nadrabiających noc odpowiada na
pytania, których nikt już nie zadaje, i kosztuje pięć razy tyle.

#### Scenario: Moduł nie pracował przez sześć godzin

- **WHEN** moduł wstaje po przerwie obejmującej sześć należnych wyzwoleń harmonogramu godzinowego
- **THEN** rusza jeden przebieg
- **AND** historia wyzwoleń mówi, ile wyzwoleń zostało pominiętych

### Requirement: Wyzwolenie bez przebiegu zostawia zapisany powód

Wyzwolenie, które nie uruchomiło przebiegu, MUST zostać zapisane razem z powodem. Powodem
MUST być co najmniej: trwający wciąż poprzedni przebieg tego harmonogramu, wyczerpana granica
dobowa zespołu, rewizja, której nie da się uruchomić, oraz niedostępność serwera narzędzi
wymaganych przez rewizję. Nakładający się przebieg MUST zostać pominięty, a MUST NOT zostać
zakolejkowany.

Praca bez nadzoru jest wiarygodna tylko wtedy, gdy da się po fakcie odczytać, dlaczego czegoś
nie było. Cisza wygląda identycznie przy harmonogramie działającym poprawnie i przy zepsutym.

#### Scenario: Poprzedni przebieg wciąż trwa

- **WHEN** nadchodzi wyzwolenie, a poprzedni przebieg tego harmonogramu jeszcze pracuje
- **THEN** nowy przebieg nie rusza
- **AND** w historii wyzwoleń jest wpis nazywający trwający przebieg jako powód

#### Scenario: Zespół wyczerpał granicę dobową

- **WHEN** nadchodzi wyzwolenie, a zespół wydał już dobową granicę kosztu
- **THEN** przebieg nie rusza i nie powstaje żaden wiersz zużycia
- **AND** w historii wyzwoleń jest wpis nazywający granicę jako powód

### Requirement: Harmonogram po serii nieudanych przebiegów wyłącza się sam

Po serii kolejnych przebiegów zakończonych niepowodzeniem harmonogram MUST zostać wyłączony,
a powód wyłączenia MUST zostać zapisany. Wyłączony harmonogram MUST pozostać widoczny
i MUST dać się włączyć z powrotem przez operatora.

#### Scenario: Kolejne przebiegi kończą się niepowodzeniem

- **WHEN** przebiegi harmonogramu kończą się niepowodzeniem tyle razy z rzędu, ile wynosi
  granica
- **THEN** harmonogram przestaje wyzwalać
- **AND** operator widzi, że został wyłączony, i widzi dlaczego

### Requirement: Harmonogram nad rewizją z narzędziami zapisującymi wymaga jawnego potwierdzenia

Jeśli rewizja przypisuje któremukolwiek agentowi narzędzie zmieniające stan poza modułem,
utworzenie harmonogramu lub wyzwalacza dla tej rewizji MUST zostać odmówione, chyba że
harmonogram niesie jawne potwierdzenie operatora dla pracy bez nadzoru. Odmowa MUST nazywać
narzędzie, którego dotyczy.

Wymaganie jest dziś spełnione w próżni — narzędzia modułu są wyłącznie odczytem. Zapisane
teraz, obowiązuje w chwili, w której pojawi się pierwsze narzędzie zapisujące, zamiast być
odkrywane wtedy, gdy zespół bez nadzoru zrobi coś nieodwracalnego.

#### Scenario: Rewizja z samym odczytem rynku

- **WHEN** operator zapisuje harmonogram dla rewizji, której agenci mają wyłącznie narzędzia
  odczytu
- **THEN** harmonogram zostaje zapisany bez dodatkowego potwierdzenia

#### Scenario: Rewizja z narzędziem zmieniającym stan

- **WHEN** operator zapisuje harmonogram dla rewizji, której agent ma narzędzie zmieniające
  stan poza modułem, i nie niesie potwierdzenia
- **THEN** zapis zostaje odrzucony z powodem nazywającym to narzędzie

### Requirement: Moduł ma jeden zegar i sam publikuje najbliższe wyzwolenia

Czas wyzwolenia MUST być wyrażony i liczony w UTC. Moduł MUST publikować moment najbliższego
wyzwolenia harmonogramu, a jego wyliczenie MUST NOT być zadaniem odbiorcy kontraktu.
Budzenie się modułu MUST dać się wyłączyć ustawieniem aplikacji, bez wdrażania nowego obrazu;
wyłączenie MUST NOT zabrać możliwości uruchomienia przebiegu ręcznie.

Granica dobowa kosztu jest liczona od północy UTC. Harmonogram w innej strefie znaczyłby, że
budżet i wyzwolenia resetują się w innych momentach, a zmiana czasu przesuwałaby jedno wobec
drugiego dwa razy w roku.

#### Scenario: Operator pyta o najbliższe wyzwolenia

- **WHEN** operator otwiera harmonogram
- **THEN** dostaje z modułu moment najbliższego wyzwolenia i kolejnych

#### Scenario: Budzenie wyłączone ustawieniem

- **WHEN** budzenie się modułu jest wyłączone ustawieniem aplikacji
- **THEN** żaden harmonogram nie wyzwala
- **AND** ręczne uruchomienie przebiegu działa dalej

### Requirement: Przebieg z harmonogramu jest zwykłym przebiegiem

Przebieg uruchomiony przez harmonogram MUST podlegać tym samym granicom czasu, rund i kosztu
co przebieg uruchomiony ręcznie, MUST zostawiać ten sam ślad i MUST dać się przerwać tak samo.

#### Scenario: Operator przerywa przebieg, którego nie zaczął

- **WHEN** operator przerywa trwający przebieg uruchomiony przez harmonogram
- **THEN** przebieg zatrzymuje się i zachowuje to, co zdążył wypracować
