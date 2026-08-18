# teams-schedules Specification

## Purpose
Kiedy zespół rusza bez operatora: co opisuje harmonogram, którą rewizję uruchamia, kto jest
właścicielem przebiegu, którego nikt nie zamówił ręcznie, oraz co dzieje się z wyzwoleniem,
które nie mogło uruchomić przebiegu.
## Requirements
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

### Requirement: Moduł ma jeden zegar i sam publikuje najbliższe wyzwolenia

Czas wyzwolenia MUST być liczony w strefie `Europe/Warsaw` i MUST być publikowany w UTC.
Godzina harmonogramu MUST NOT przesuwać się przy zmianie czasu: harmonogram opisany na 9:00
wyzwala się o 9:00 czasu polskiego zarówno w czasie letnim, jak i zimowym. Moduł MUST
publikować moment najbliższego wyzwolenia harmonogramu, a jego wyliczenie MUST NOT być
zadaniem odbiorcy kontraktu. Budzenie się modułu MUST dać się wyłączyć ustawieniem aplikacji,
bez wdrażania nowego obrazu; wyłączenie MUST NOT zabrać możliwości uruchomienia przebiegu
ręcznie.

Operator pracuje w jednej strefie — swojej. Harmonogram liczony w UTC znaczył, że operator
sam wpisywał 7:00, żeby zespół ruszył o dziewiątej, i poprawiał to dwa razy w roku. Cena jest
w drugą stronę: granica dobowa kosztu nadal liczy się od północy UTC, więc odstęp między
resetem budżetu a porannym wyzwoleniem zmienia się o godzinę przy zmianie czasu. To jest
odstęp, którego nikt nie ogląda; przesuwająca się godzina wyzwolenia była widoczna codziennie.

#### Scenario: Operator pyta o najbliższe wyzwolenia

- **WHEN** operator otwiera harmonogram
- **THEN** dostaje z modułu moment najbliższego wyzwolenia i kolejnych

#### Scenario: Zmiana czasu

- **WHEN** harmonogram codzienny na 9:00 przechodzi przez zmianę czasu letniego na zimowy
- **THEN** wyzwala się dalej o 9:00 czasu polskiego
- **AND** publikowany moment wyzwolenia w UTC przesuwa się o godzinę

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

### Requirement: Harmonogram da się opisać rytmem, a moduł zna oba zapisy

Moduł MUST przyjmować opis harmonogramu podany jako rytm — odstęp w minutach, godzina doby,
dni tygodnia albo dzień miesiąca — i MUST sam zamienić go na wyrażenie czasowe, które
wykonuje. Moduł MUST publikować ten rytm przy harmonogramie, obok wyrażenia czasowego.
Harmonogram, którego wyrażenia nie da się wyrazić żadnym z rytmów, MUST zostać opublikowany
z rytmem pustym i MUST nadal dać się odczytać oraz wyzwalać.

Rytm powtarzający się częściej niż raz na dobę MUST móc nieść dni tygodnia. Rynek stoi dwa
dni w tygodniu, a rytm bez tych dni każe pytać o niego także wtedy — kosztem przebiegu,
który nie ma o co zapytać. Dni tygodnia przy takim rytmie MUST być opcjonalne, a ich brak
MUST znaczyć każdy dzień.

Komplet siedmiu dni MUST być zapisany tak samo jak brak dni. Jedno wyzwolenie opisane na
dwa sposoby zabiera odczytowi jednoznaczność: moduł, który zapisze oba, przy odczycie
odpowie jednym z nich i operator zobaczy rytm, którego nie ułożył.

Rytm dobowy MUST NOT nieść dni tygodnia. Dobowy z dniami tygodnia znaczy dokładnie to, co
rytm tygodniowy, i te same dwa zapisy jednego wyzwolenia MUST NOT powstać.

Zamiana rytmu na wyrażenie czasowe istnieje raz — w module. Odbiorca kontraktu, który
musiałby ją powtórzyć u siebie, żeby pokazać operatorowi jego własny harmonogram, prędzej
czy później pokaże co innego, niż moduł wykona.

#### Scenario: Harmonogram zapisany rytmem

- **WHEN** operator zapisuje harmonogram jako „codziennie o 9:00"
- **THEN** moduł zapisuje harmonogram wyzwalający się o 9:00 czasu polskiego
- **AND** odczyt tego harmonogramu zwraca ten sam rytm

#### Scenario: Rytm godzinowy ograniczony do dni handlowych

- **WHEN** operator zapisuje harmonogram jako „co godzinę o :35, od poniedziałku do piątku"
- **THEN** moduł zapisuje harmonogram, który w sobotę i w niedzielę się nie wyzwala
- **AND** odczyt tego harmonogramu zwraca ten sam rytm wraz z tymi dniami

#### Scenario: Rytm krótszy niż godzina bez dni tygodnia

- **WHEN** operator zapisuje rytm „co 15 minut" bez wskazania dni
- **THEN** harmonogram wyzwala się każdego dnia tygodnia
- **AND** odczyt zwraca rytm bez dni tygodnia, a nie z kompletem siedmiu

#### Scenario: Wszystkie dni tygodnia wskazane

- **WHEN** operator zapisuje rytm godzinowy, wskazując wszystkie siedem dni
- **THEN** zapisany harmonogram jest tym samym, co harmonogram zapisany bez wskazania dni
- **AND** odczyt zwraca rytm bez dni tygodnia

#### Scenario: Dni tygodnia przy rytmie dobowym

- **WHEN** opis harmonogramu niesie rytm dobowy razem z dniami tygodnia
- **THEN** moduł odmawia zapisu, nazywając rytm tygodniowy jako miejsce na te dni

#### Scenario: Wyrażenie spoza rytmów kreatora

- **WHEN** harmonogram niesie wyrażenie czasowe, którego nie da się opisać żadnym z rytmów
- **THEN** odczyt zwraca ten harmonogram z pustym rytmem i z jego wyrażeniem
- **AND** harmonogram wyzwala się dalej

### Requirement: Moduł liczy najbliższe wyzwolenia także dla opisu, którego nie zapisano

Moduł MUST odpowiadać na pytanie „kiedy wyzwoli się harmonogram opisany tak a tak" dla opisu,
który nie został jeszcze zapisany. Odpowiedź MUST mieć tę samą postać co dla harmonogramu
zapisanego. Opis, którego moduł nie umie wykonać, MUST zostać odrzucony z powodem, a nie
policzony.

Operator układający harmonogram ma zobaczyć jego skutek przed zapisem. Bez tego jedyną drogą
do podglądu jest zapisanie harmonogramu, obejrzenie i poprawienie go — czyli trzy zapisy na
jedną decyzję.

#### Scenario: Podgląd przed zapisem

- **WHEN** operator pyta o najbliższe wyzwolenia dla opisu, którego jeszcze nie zapisał
- **THEN** moduł zwraca te momenty, nie zapisując żadnego harmonogramu

#### Scenario: Opis, którego nie da się wykonać

- **WHEN** operator pyta o najbliższe wyzwolenia dla opisu niepoprawnego
- **THEN** moduł odmawia z powodem nazywającym, co jest w tym opisie nie tak

### Requirement: Harmonogram i wyzwalacz dają się usunąć

Moduł MUST pozwalać właścicielowi usunąć harmonogram i wyzwalacz. Usunięcie MUST być
odróżnialne od wyłączenia: wyłączony wpis zostaje w katalogu ze swoim powodem i daje się
włączyć z powrotem, usunięty przestaje istnieć.

Usunięcie MUST zabrać ze sobą historię wyzwoleń tego wpisu i MUST NOT ruszyć przebiegów,
które z niej wystartowały. Historia wskazuje wpis, który ją wytworzył, i bez niego nie ma
jak istnieć; przebieg jest zapisem tego, co się wydarzyło — jego koszt i jego ślad handlowy
przeżywają usunięcie harmonogramu, który go zamówił.

Usunięcie cudzego wpisu MUST być nieodróżnialne od usunięcia nieistniejącego.

#### Scenario: Operator usuwa harmonogram

- **WHEN** właściciel usuwa swój harmonogram
- **THEN** harmonogram znika z katalogu i przestaje się wyzwalać
- **AND** przebiegi, które z niego wystartowały, zostają wraz ze swoim kosztem

#### Scenario: Usunięcie zabiera historię wyzwoleń

- **WHEN** właściciel usuwa harmonogram, który wyzwalał się wcześniej
- **THEN** zapisy jego wyzwoleń znikają razem z nim
- **AND** usunięcie nie zostaje odrzucone z powodu ich istnienia

#### Scenario: Wyłączenie to nie usunięcie

- **WHEN** operator wyłącza harmonogram, zamiast go usunąć
- **THEN** harmonogram zostaje w katalogu ze swoim powodem wyłączenia
- **AND** daje się włączyć z powrotem

#### Scenario: Cudzy harmonogram

- **WHEN** ktoś inny niż właściciel usuwa harmonogram
- **THEN** odpowiedź jest taka sama jak dla harmonogramu, którego nie ma
- **AND** harmonogram zostaje nietknięty

