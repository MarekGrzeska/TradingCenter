## Purpose

Panel operatora dla pracy zespołu bez operatora: układanie harmonogramu i wyzwalacza, podgląd
tego, co ma się wydarzyć, i odczyt tego, co wydarzyło się, gdy nikt nie patrzył.

## ADDED Requirements

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
parsera wyrażeń czasowych ani własnej implementacji ich rozwijania.

To ta sama zasada, co przy katalogu modeli i katalogu narzędzi: druga implementacja tej samej
reguły po stronie terminala rozjeżdża się z pierwszą, a operator widzi wtedy inną godzinę niż
ta, o której moduł naprawdę ruszy.

#### Scenario: Podgląd najbliższych wyzwoleń

- **WHEN** operator układa harmonogram i chce zobaczyć, kiedy ten wyzwoli
- **THEN** pokazane momenty pochodzą z odpowiedzi modułu

### Requirement: Czas jest pokazany tak, żeby nie trzeba było go przeliczać

Moment wyzwolenia MUST być pokazany w UTC — czyli w tym, w czym jest zapisany — oraz w czasie
lokalnym przeglądarki obok niego.

#### Scenario: Operator w strefie innej niż UTC

- **WHEN** terminal pokazuje moment najbliższego wyzwolenia
- **THEN** widać go w UTC i w czasie lokalnym

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
