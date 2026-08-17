# terminal-teams-schedules Specification

## Purpose
Panel operatora dla pracy zespołu bez operatora: układanie harmonogramu i wyzwalacza, podgląd
tego, co ma się wydarzyć, i odczyt tego, co wydarzyło się, gdy nikt nie patrzył.
## Requirements
### Requirement: Harmonogramy zespołu są widoczne razem z jego przebiegami

Terminal MUST pokazywać harmonogramy i wyzwalacze zespołu w tej samej zakładce co jego
definicję i przebiegi. Dla każdego MUST być widoczne, czy jest włączony, oraz kiedy wyzwoli
się najbliżej. Harmonogram wyłączony MUST pozostać widoczny i MUST NOT zniknąć z listy.

Wyłączony harmonogram jest stanem, który operator ma zobaczyć — zwłaszcza wtedy, gdy wyłączył
go moduł po serii niepowodzeń, a nie człowiek.

#### Scenario: Harmonogram wyłączony przez moduł

- **WHEN** moduł wyłączył harmonogram po serii nieudanych przebiegów
- **THEN** harmonogram jest na liście, oznaczony jako wyłączony
- **AND** widać powód wyłączenia

### Requirement: Terminal nie liczy czasu wyzwolenia sam

Momenty najbliższych wyzwoleń MUST pochodzić z modułu. Terminal MUST NOT nosić własnego
parsera wyrażeń czasowych, własnej implementacji ich rozwijania ani własnej zamiany rytmu
na wyrażenie czasowe.

To ta sama zasada, co przy katalogu modeli i katalogu narzędzi: druga implementacja tej samej
reguły po stronie terminala rozjeżdża się z pierwszą, a operator widzi wtedy inną godzinę niż
ta, o której moduł naprawdę ruszy.

#### Scenario: Podgląd najbliższych wyzwoleń

- **WHEN** operator układa harmonogram i chce zobaczyć, kiedy ten wyzwoli
- **THEN** pokazane momenty pochodzą z odpowiedzi modułu

#### Scenario: Rytm zamieniany na wyrażenie czasowe

- **WHEN** operator zapisuje harmonogram ułożony rytmem
- **THEN** zamiany na wyrażenie czasowe dokonuje moduł

### Requirement: Czas jest pokazany tak, żeby nie trzeba było go przeliczać

Moment wyzwolenia MUST być pokazany w czasie polskim i MUST być oznaczony jako czas polski.
Gdy strefa przeglądarki jest inna niż polska, ten sam moment MUST być pokazany obok także
w czasie przeglądarki.

Harmonogramy są opisywane w czasie polskim, więc to on jest tu czasem, w którym operator
myśli. UTC był tu wcześniej dlatego, że w nim liczył moduł — a nie dlatego, że ktoś go
czytał.

#### Scenario: Operator w strefie polskiej

- **WHEN** terminal pokazuje moment najbliższego wyzwolenia operatorowi w strefie polskiej
- **THEN** widzi ten moment raz, oznaczony jako czas polski

#### Scenario: Operator w strefie innej niż UTC

- **WHEN** terminal pokazuje moment najbliższego wyzwolenia operatorowi poza strefą polską
- **THEN** widzi go w czasie polskim i w czasie swojej przeglądarki

### Requirement: Historia pokazuje także to, co się nie wydarzyło

Historia wyzwoleń MUST zawierać wyzwolenia, które nie uruchomiły przebiegu, wraz z powodem.
Wyzwolenie, które uruchomiło przebieg, MUST prowadzić do śladu tego przebiegu.

Bez tego panel odpowiada „nic tu nie ma" zarówno na harmonogram, który poprawnie milczał, jak
i na taki, który od trzech dni odbija się od granicy kosztu.

#### Scenario: Wyzwolenie pominięte

- **WHEN** wyzwolenie zostało pominięte, bo poprzedni przebieg wciąż trwał
- **THEN** jest widoczne w historii z tym powodem

#### Scenario: Wyzwolenie zakończone przebiegiem

- **WHEN** operator wybiera wyzwolenie, które uruchomiło przebieg
- **THEN** przechodzi do śladu tego przebiegu

### Requirement: Odmowa modułu jest pokazana słowami modułu

Gdy moduł odmawia zapisania harmonogramu lub wyzwalacza, terminal MUST pokazać powód podany
przez moduł i MUST NOT zastąpić go własnym komunikatem ogólnym.

#### Scenario: Odmowa z powodu narzędzia zmieniającego stan

- **WHEN** moduł odmawia zapisu harmonogramu dla rewizji z narzędziem zmieniającym stan
- **THEN** operator widzi powód nazywający to narzędzie

### Requirement: Harmonogram układa się rytmem i godziną, nie wyrażeniem czasowym

Terminal MUST pozwalać ułożyć harmonogram przez wybór rytmu (co N minut, co godzinę,
codziennie, w wybrane dni tygodnia, w wybrany dzień miesiąca) i godziny, bez wpisywania
wyrażenia czasowego. Wyrażenie czasowe MUST pozostać dostępne jako droga dla rytmu, którego
kreator nie obejmuje, i MUST być schowane poza domyślnym widokiem formularza. Harmonogram,
którego wyrażenia nie da się opisać żadnym rytmem, MUST być pokazany tym wyrażeniem i MUST
dać się edytować bez utraty tego, co niesie.

Zespół układa operator rynku, nie administrator systemu. Pole z pięcioma gwiazdkami jest
dla niego zamkniętymi drzwiami, a wpisane w nie na wyczucie wyrażenie jest gorsze niż brak
harmonogramu, bo wygląda na działające.

#### Scenario: Harmonogram codzienny

- **WHEN** operator wybiera rytm „codziennie" i godzinę 9:00
- **THEN** zapisany harmonogram wyzwala się codziennie o 9:00 czasu polskiego
- **AND** operator nie wpisał żadnego wyrażenia czasowego

#### Scenario: Rytm spoza kreatora

- **WHEN** operator otwiera harmonogram, którego wyrażenia kreator nie obejmuje
- **THEN** widzi to wyrażenie i może je poprawić
- **AND** zapis nie zamienia go na inny rytm

### Requirement: Operator widzi skutek harmonogramu przed zapisaniem go

Terminal MUST pokazywać najbliższe wyzwolenia układanego harmonogramu, zanim zostanie
zapisany, i MUST je odświeżać po zmianie rytmu lub godziny. Te momenty MUST pochodzić
z modułu.

#### Scenario: Podgląd w trakcie układania

- **WHEN** operator zmienia godzinę w kreatorze harmonogramu
- **THEN** widzi najbliższe wyzwolenia dla tej godziny, przed zapisaniem harmonogramu

### Requirement: Harmonogram da się usunąć z listy, nie tylko zatrzymać

Terminal MUST pozwalać usunąć harmonogram i wyzwalacz z listy, obok wyłączenia i osobno od
niego. Usunięcie MUST wymagać potwierdzenia i MUST nazwać w nim to, co zniknie bezpowrotnie
— historię wyzwoleń tego wpisu — oraz to, co zostaje: przebiegi, które z niego wystartowały,
wraz z ich kosztem.

Wyłączenie i usunięcie MUST być rozróżnialne wzrokiem, zanim operator kliknie. Lista, na
której jedyną drogą do pozbycia się wpisu jest jego wyłączenie, rośnie w jedną stronę: wpisy
wyłączone i zapomniane wyglądają jak wpisy czekające na wznowienie.

#### Scenario: Operator usuwa harmonogram z listy

- **WHEN** operator wybiera usunięcie harmonogramu i potwierdza
- **THEN** harmonogram znika z listy
- **AND** lista jest odczytana z modułu na nowo, a nie poprawiona lokalnie

#### Scenario: Potwierdzenie mówi, co zniknie

- **WHEN** operator wybiera usunięcie harmonogramu, który wyzwalał się wcześniej
- **THEN** potwierdzenie nazywa historię wyzwoleń jako to, co znika bezpowrotnie
- **AND** mówi, że przebiegi i ich koszt zostają

#### Scenario: Operator rezygnuje z usunięcia

- **WHEN** operator zamyka potwierdzenie bez zgody
- **THEN** harmonogram zostaje nietknięty i dalej się wyzwala

#### Scenario: Zatrzymanie zostaje osobną czynnością

- **WHEN** operator chce, żeby harmonogram przestał chodzić, ale został
- **THEN** ma na to wyłączenie, bez przechodzenia przez usunięcie
