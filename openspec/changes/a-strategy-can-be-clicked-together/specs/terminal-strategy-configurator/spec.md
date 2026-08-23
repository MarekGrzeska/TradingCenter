## ADDED Requirements

### Requirement: Wybieraki konfiguratora pochodzą z katalogu archiwum

Ekran składania reguły MUST budować listy wskaźników, ich linii i zakresów parametrów
z katalogu ogłaszanego przez archiwum, a nie z listy wpisanej w terminalu. Zakres parametru
MUST być pokazany przy polu, a wartość spoza zakresu MUST zostać odrzucona przez moduł —
terminal MUST NOT powielać tej reguły własnym sprawdzeniem.

Kopia katalogu po stronie ekranu rozjeżdża się przy pierwszym nowym wskaźniku, a druga
opinia o zakresach jest drugą prawdą o liczbach, których ten ekran nie posiada. To jest ta
sama zasada, którą kieruje się okno zakładania obserwacji.

#### Scenario: Nowy wskaźnik w archiwum

- **WHEN** archiwum ogłosi wskaźnik, którego wcześniej nie było
- **THEN** pojawia się on w wybieraku konfiguratora bez zmiany w terminalu

#### Scenario: Wartość poza zakresem wskaźnika

- **WHEN** operator wpisuje wartość parametru poza zakresem ogłoszonym przez archiwum
- **THEN** zapis kończy się odmową modułu, pokazaną przy tym, co ją wywołało

### Requirement: Ekran pokazuje rewizję jako pochodzenie, nie jako szczegół

Lista definicji MUST pokazywać przy każdej numer jej najnowszej rewizji, a decyzja policzona
wyklikaną strategią MUST pokazywać rewizję, którą powstała. Zapisanie nowej rewizji MUST NOT
sugerować, że działające obserwacje zaczęły ją liczyć; przejście obserwacji na nowszą
rewizję MUST być osobnym działaniem operatora.

Ekran, który pokazuje najnowszą regułę obok decyzji policzonych starą, odpowiada na pytanie
„czemu to weszło" przekonująco i błędnie — a to jest gorsze niż nieodpowiadanie.

#### Scenario: Decyzja sprzed zmiany reguły

- **WHEN** operator ogląda decyzję sprzed zapisania nowszej rewizji
- **THEN** przy decyzji widnieje rewizja, którą została policzona, a nie najnowsza

#### Scenario: Zapis nowej rewizji przy działającej obserwacji

- **WHEN** operator zapisuje nową rewizję definicji, którą obserwuje działający watch
- **THEN** ekran mówi, że obserwacja liczy dalej poprzednią rewizję
- **AND** przejście na nowszą wymaga osobnego działania

### Requirement: Konfigurator nie obiecuje wykonania ani nie udaje edycji kodu

Konfigurator MUST NOT oferować żadnego działania na rachunku. Wpis pochodzący z obrazu MUST
być na ekranie rozpoznawalny i MUST NOT mieć kontrolek edycji — MUST być czytelne, że jest
kodem, a nie wierszem, którego nie da się edytować z powodu usterki.

Przycisk obiecujący zlecenie byłby w tym terminalu jedynym miejscem obiecującym wykonanie
tam, gdzie go nie ma. Wyszarzona edycja bez wyjaśnienia jest odwrotną wersją tego samego
błędu: wygląda na awarię, a jest decyzją.

#### Scenario: Wpis kodowy na liście definicji

- **WHEN** operator ogląda listę, na której są wpisy z obrazu i wyklikane definicje
- **THEN** wpis z obrazu jest oznaczony jako pochodzący z kodu
- **AND** nie ma przy nim kontrolki edycji reguły

#### Scenario: Ekran konfiguratora a rachunek

- **WHEN** operator przegląda konfigurator
- **THEN** nie ma na nim żadnej kontrolki składającej, zmieniającej ani zamykającej pozycję
