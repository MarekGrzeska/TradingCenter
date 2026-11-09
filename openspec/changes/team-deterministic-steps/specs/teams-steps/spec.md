## Purpose

Krok deterministyczny w zespole: węzeł grafu, który zamiast modelu wykonuje przepis z katalogu modułu. Ta specyfikacja
opisuje, jak krok trafia do rewizji, jak pracuje, co zostawia następnikom i w śladzie, oraz jak przepis
`strategy_execute` prowadzi pozycję zespołu za silnikiem strategii.

## ADDED Requirements

### Requirement: Rewizja może nieść kroki obok agentów

Definicja rewizji MUST móc nieść listę kroków obok listy agentów. Każdy krok MUST mieć klucz, nazwę przepisu i
parametry tego przepisu. Klucze MUST być unikalne łącznie wśród kroków i agentów. Zależności MUST móc łączyć krok z
agentem, agenta z krokiem i krok z krokiem, z tymi samymi regułami grafu co dziś: bez cyklu i bez węzła odciętego od
pozostałych. Rewizja MUST mieć co najmniej jeden węzeł, krok albo agenta.

Rewizja bez kroków MUST czytać się, zapisywać i biec dokładnie tak jak przed tą zmianą. Zmiana MUST NOT przepisywać
ani migrować żadnej zapisanej rewizji.

#### Scenario: Rewizja zapisana przed zmianą

- **WHEN** operator uruchamia zespół, którego rewizja powstała przed wprowadzeniem kroków
- **THEN** przebieg biegnie tak samo jak przed zmianą
- **AND** odczyt tej rewizji pokazuje pustą listę kroków

#### Scenario: Zespół mieszany

- **WHEN** operator zapisuje rewizję z jednym krokiem i jednym agentem oraz zależnością od kroku do agenta
- **THEN** zapis zostaje przyjęty
- **AND** w przebiegu agent zaczyna dopiero po zakończeniu kroku

#### Scenario: Krok i agent o tym samym kluczu

- **WHEN** rewizja niesie krok i agenta o tym samym kluczu
- **THEN** zapis zostaje odrzucony z nazwą tego klucza

### Requirement: Krok wykonuje przepis z katalogu modułu

Krok MUST wykonywać wyłącznie przepis, który moduł ogłasza w swoim katalogu przepisów. Katalog MUST być czytelny dla
terminala i dla zestawu narzędzi zespołów i MUST podawać dla każdego przepisu nazwę, opis, parametry z ich typami i
narzędzia, których przepis potrzebuje. Rewizja MUST NOT nieść kodu ani wyrażeń wykonywanych przez krok.

Przy zapisie moduł MUST odrzucić krok, gdy:
- przepis jest nieznany;
- parametry nie pasują do przepisu;
- serwer narzędzi nie ogłasza któregoś z narzędzi przepisu.

Odmowa MUST nazywać krok. Przepis, który zmienia stan rachunku, MUST podlegać tym samym zakazom co agent zespołu z
kontem: nie przełącza konta aktywnego i nie koryguje salda.

#### Scenario: Nieznany przepis

- **WHEN** operator zapisuje krok z nazwą przepisu, której katalog nie zna
- **THEN** zapis zostaje odrzucony z nazwą kroku i listą znanych przepisów

#### Scenario: Parametr spoza przepisu

- **WHEN** krok niesie parametr, którego przepis nie przyjmuje, albo nie niesie parametru wymaganego
- **THEN** zapis zostaje odrzucony z nazwą kroku i parametru

### Requirement: Krok nie woła modelu i pracuje tą samą drogą co agent

Krok MUST NOT wywoływać modelu i MUST NOT zostawiać wierszy zużycia. Narzędzia MUST wołać przez te same narzędzia
przebiegu co agent, więc na takich samych warunkach:
- konto rewizji jest wpisywane w każde wywołanie narzędzia rachunku;
- granice handlowe rewizji są sprawdzane przed każdym wywołaniem zapisującym;
- każde wywołanie zapisujące zostawia wiersz zlecenia przed wysłaniem;
- każde wywołanie narzędzia trafia do śladu przebiegu przy tym kroku.

Postęp kroku MUST być widoczny w trakcie przebiegu tak jak postęp agenta: czeka, pracuje, skończył.

Odmowa granicy wielkości zlecenia MUST zakończyć krok wynikiem odmowy. Krok MUST NOT zmniejszać ani dzielić zlecenia,
żeby zmieścić się w granicy. Ta sama zasada obowiązuje przy odmowie bramy konta realnego.

#### Scenario: Krok składa zlecenie na koncie zespołu

- **WHEN** krok zespołu z przypisanym kontem składa zlecenie
- **THEN** zlecenie trafia na konto zespołu
- **AND** ślad przebiegu niesie wiersz zlecenia wskazujący ten krok
- **AND** przebieg nie ma żadnego wiersza zużycia modelu przypisanego do kroku

#### Scenario: Zlecenie większe niż granica rewizji

- **WHEN** wyliczony przez krok rozmiar przekracza maksymalną wielkość zlecenia z rewizji
- **THEN** zlecenie nie zostaje wysłane
- **AND** krok kończy się wynikiem odmowy nazywającym granicę i rozmiar

### Requirement: Wynik kroku jest daną przekazaną następnikom

Krok MUST kończyć się wynikiem w ustalonym kształcie. Wynik niesie:
- decyzję, jedną z: wejście, wyjście, brak działania, pominięcie, odmowa, wynik nieznany, strategia nieobsługiwana;
- powód, gdy decyzja nie jest wejściem ani wyjściem;
- jednozdaniowe streszczenie;
- pozostałe dane, które przepis zwraca.

Następnik MUST dostać ten wynik jako pracę poprzednika, tak jak dziś dostaje wypowiedź agenta.

Przewidziane przez przepis wyniki MUST kończyć krok jako zakończony i MUST NOT zatrzymywać przebiegu, bo następnik ma
je opowiedzieć. Dotyczy to odmowy, braku świecy i wyniku nieznanego. Krok MUST zakończyć się błędem i zatrzymać
przebieg tylko przy awarii, której przepis nie przewiduje.

#### Scenario: Następnik czyta wynik kroku

- **WHEN** krok kończy się wejściem, a zależność prowadzi od niego do agenta
- **THEN** agent dostaje wynik kroku jako pracę poprzednika

#### Scenario: Odmowa nie zatrzymuje przebiegu

- **WHEN** brama odmawia zlecenia złożonego przez krok
- **THEN** krok kończy się jako zakończony z decyzją odmowy i jej treścią
- **AND** następnik kroku pracuje

### Requirement: Przepis strategy_execute prowadzi własną pozycję zespołu za silnikiem strategii

Przepis `strategy_execute` MUST przyjmować:
- strategię i jej rewizję (wymagane);
- symbol (wymagany);
- rozmiar (opcjonalny);
- czas czekania na świecę w archiwum (opcjonalny);
- największy dopuszczalny wiek świecy sygnałowej (opcjonalny).

Decyzję MUST brać wyłącznie z sygnału silnika strategii i MUST NOT liczyć wskaźników ani warunków samodzielnie.

Wejście MUST nastąpić wtedy i tylko wtedy, gdy spełnione są wszystkie cztery warunki:
- sygnał mówi „wejście” na świecy, której wiek nie przekracza ustawionego największego wieku (brak tego parametru
  znaczy brak granicy wieku);
- na koncie zespołu nie ma pozycji ani zlecenia oczekującego na tym symbolu;
- zespół nie ma żadnej własnej pozycji;
- dla tej świecy sygnałowej nie było jeszcze próby.

Wejście MUST być zleceniem rynkowym w kierunku sygnału. Rozmiar MUST być wyliczony z depozytu i ceny przez narzędzie
rachunku. Przepis MUST NOT nadrabiać wejścia, którego świeca jest za stara.

Gdy archiwum jeszcze nie ma świecy sygnałowej, przepis MUST ponawiać pytanie o sygnał najwyżej przez ustawiony czas
czekania. Po jego upływie MUST zakończyć się pominięciem z powodem nazywającym brak świecy.

Własną pozycję zespołu przepis MUST zamknąć, gdy zachodzi jedno z trzech:
- sygnał mówi „wyjście”;
- silnik nie ma pozycji;
- pozycja silnika ma przeciwny kierunek.

Przepis MUST NOT otwierać pozycji w tym samym przebiegu, w którym zamknął własną. Pozycji, której zespół nie złożył,
MUST NOT dotykać.

Silnik nie widzi pozycji otwartej przed początkiem swojego okna. Dla własnej pozycji starszej niż to okno przepis
MUST NOT decydować na podstawie stanu silnika. MUST zakończyć się wynikiem nieznanym, bez zlecenia, i zostawić decyzję
operatorowi.

Własna pozycja to pozycja założona zleceniem tego zespołu, odnaleziona w jego wierszach zleceń i obecna na koncie.
Gdy tego nie da się jednoznacznie ustalić, przepis MUST zakończyć się wynikiem nieznanym, bez zlecenia.

#### Scenario: Świeży sygnał wejścia na pustym koncie

- **WHEN** sygnał mówi „wejście long” na świecy w granicy wieku, a konto zespołu nie ma pozycji ani zleceń na symbolu
- **THEN** przepis składa jedno zlecenie rynkowe kupna o rozmiarze wyliczonym z depozytu

#### Scenario: Świeca za stara

- **WHEN** sygnał mówi „wejście”, a wiek świecy przekracza ustawiony największy wiek
- **THEN** przepis nie składa zlecenia i kończy się pominięciem z wiekiem świecy jako powodem

#### Scenario: Archiwum spóźnione

- **WHEN** przy starcie kroku archiwum nie ma jeszcze świecy sygnałowej, a pojawia się ona przed upływem czasu
  czekania
- **THEN** przepis działa na tej świecy, jakby była obecna od początku

#### Scenario: Wyjście o porze ze strategii

- **WHEN** zespół ma własną pozycję, a silnik nie ma już pozycji albo sygnał mówi „wyjście”
- **THEN** przepis zamyka własną pozycję zespołu
- **AND** nie otwiera nowej w tym samym przebiegu

#### Scenario: Pozycja ręczna na koncie

- **WHEN** na koncie zespołu stoi pozycja, której żadne zlecenie zespołu nie założyło
- **THEN** przepis jej nie zamyka
- **AND** nie wchodzi, bo konto ma pozycję na symbolu

### Requirement: Rozmiar pozycji jest zapisany w rewizji, nie w prozie

Bez parametru rozmiaru `strategy_execute` MUST stosować regułę rozmiaru z dokumentu strategii. Z parametrem MUST
stosować wartość z kroku. Wynik kroku MUST nazywać użytą wartość i jej źródło: dokument albo krok. Przepis MUST
odmówić rozmiaru, którego narzędzie rachunku nie umie przeliczyć na wielkość zlecenia, i MUST NOT podstawiać
najmniejszej wielkości ani zwiększać rozmiaru.

#### Scenario: Nadpisanie depozytu w kroku

- **WHEN** dokument strategii mówi o depozycie 20% kapitału, a krok niesie depozyt 35%
- **THEN** zlecenie ma rozmiar wyliczony z 35%
- **AND** wynik kroku nazywa 35% i źródło „krok”

#### Scenario: Depozyt za mały na najmniejsze zlecenie

- **WHEN** wyliczony depozyt nie wystarcza na najmniejszą wielkość instrumentu
- **THEN** przepis nie składa zlecenia i kończy się odmową z tym powodem

### Requirement: Jedna próba na świecę sygnałową

Moduł MUST zapewnić w bazie, a nie w pamięci zespołu ani w treści promptu, że na jedną świecę sygnałową jednej
strategii zespół wykona najwyżej jedną próbę wejścia i najwyżej jedną próbę wyjścia. Gwarancja MUST obowiązywać także
dla dwóch przebiegów biegnących równocześnie. Kolejna próba na tę samą świecę MUST zakończyć się pominięciem bez
wywołania zapisującego.

Wywołanie zapisujące, którego skutek pozostał nieznany, MUST NOT być ponawiane. Krok MUST zakończyć się wynikiem
nieznanym z tym, co odczytał po wywołaniu.

#### Scenario: Dwa przebiegi tej samej sesji

- **WHEN** dwa przebiegi zespołu startują po tej samej świecy sygnałowej z sygnałem wejścia
- **THEN** zlecenie składa najwyżej jeden z nich
- **AND** drugi kończy się pominięciem nazywającym wcześniejszą próbę

#### Scenario: Odpowiedź na zlecenie nie wraca

- **WHEN** wywołanie składające zlecenie kończy się bez znanego skutku
- **THEN** krok nie ponawia zlecenia
- **AND** kończy się wynikiem nieznanym

### Requirement: Strategia, której przepis nie wykona, jest odmową, a nie przybliżeniem

`strategy_execute` MUST zakończyć się wynikiem „strategia nieobsługiwana”, bez zlecenia, gdy:
- sygnał niesie zlecenie inne niż rynkowe;
- strategia niesie stop, cel albo stop kroczący.

Przepis MUST NOT przybliżać takiej strategii zleceniem rynkowym bez poziomów.

#### Scenario: Strategia ze stopem

- **WHEN** krok wykonuje strategię, której dokument ma stop
- **THEN** przepis nie składa zlecenia
- **AND** wynik nazywa stop jako to, czego przepis nie wykonuje

### Requirement: Agent może nieść powiadomienie zapasowe

Agent MUST móc nieść powiadomienie zapasowe: adresata, bota i stały prefiks tekstu. Zapis takiego agenta MUST zostać
odrzucony, gdy nie ma on przypisanego narzędzia wysyłającego wiadomość.

Gdy model takiego agenta zawiedzie albo agent nie może pracować z powodu granicy kosztu, przebieg MUST wysłać jedną
wiadomość: prefiks, streszczenia kroków, które ten agent dostał, i powód, dla którego agent nie odpowiedział.
Wysłanie MUST trafić do śladu przy tym agencie i MUST NOT zmieniać statusu przebiegu, który nadal nazywa pierwotną
przyczynę. Powiadomienie zapasowe MUST NOT być wysyłane, gdy agent skończył pracę.

#### Scenario: Model reportera nie odpowiada

- **WHEN** krok złożył zlecenie, a model agenta z powiadomieniem zapasowym zwraca błąd
- **THEN** operator dostaje wiadomość z prefiksem, streszczeniem kroku i powodem
- **AND** przebieg kończy się statusem nazywającym błąd modelu

#### Scenario: Agent kończy pracę normalnie

- **WHEN** agent z powiadomieniem zapasowym kończy pracę
- **THEN** powiadomienie zapasowe nie zostaje wysłane
