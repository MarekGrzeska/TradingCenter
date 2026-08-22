# terminal-teams Specification

## Purpose
Zakładka, w której operator składa zespół i patrzy, jak pracuje: co widać na obrazie zespołu,
jak edytuje się role i zależności, skąd bierze się lista katalogu i co pokazuje przebieg
w trakcie.
## Requirements
### Requirement: Zespół jest widoczny jako obraz zależności, nie jako lista ról

Terminal MUST pokazywać zespół jako agentów i prowadzące między nimi zależności, rozmieszczone
tak, żeby kierunek pracy dało się odczytać bez klikania. Przy każdym agencie MUST być widoczna
jego rola i model, którym pracuje.

Zależności są tu treścią, a nie ozdobą: to one decydują, kto co widzi (`teams-runs`, „Agent
widzi wypowiedzi poprzedników, a nie całą historię przebiegu"). Lista ról pokazuje wszystko
oprócz tej jednej rzeczy, dla której zespół jest zespołem.

#### Scenario: Otwarcie zapisanego zespołu

- **WHEN** operator otwiera zespół z katalogu
- **THEN** widzi jego agentów, zależności między nimi oraz rolę i model przy każdym agencie

#### Scenario: Zespół o jednym agencie

- **WHEN** operator otwiera zespół złożony z jednego agenta
- **THEN** widzi go bez żadnej zależności i może dodać kolejnych

### Requirement: Operator składa zespół w tym samym widoku, w którym go ogląda

Terminal MUST pozwalać dodać agenta, usunąć go, poprowadzić i usunąć zależność oraz zmienić
rolę, prompt, wytyczne, model i przypisane narzędzia — bez opuszczania widoku zespołu. Wybór
modelu MUST pochodzić z katalogu modeli modułu, a wybór narzędzi z tego, co moduł ogłasza;
terminal MUST NOT nieść własnej listy jednych ani drugich.

#### Scenario: Operator dokłada rolę i wiąże ją z istniejącą

- **WHEN** operator dodaje agenta i prowadzi do niego zależność od agenta już obecnego
- **THEN** obraz zespołu pokazuje nowego agenta i nową zależność

#### Scenario: Wybór modelu dla agenta

- **WHEN** operator wybiera model dla agenta
- **THEN** wybiera spośród modeli z katalogu modułu
- **AND** terminal nie ma w swoim kodzie ani jednego identyfikatora modelu

#### Scenario: Usunięcie zależności przy niej samej

- **WHEN** operator usuwa zależność wskazaną na obrazie zespołu
- **THEN** znika ona z definicji bez otwierania panelu któregokolwiek z jej końców

### Requirement: Ostatnią zmianę w zespole da się cofnąć

Terminal MUST pozwalać cofnąć ostatnią zmianę wprowadzoną w składanym zespole — dodanie
i usunięcie agenta, poprowadzenie i usunięcie zależności, zmianę pól agenta oraz przesunięcie
agenta. Cofnięcie MUST przywrócić stan sprzed tej zmiany i MUST NOT sięgać poza to, co
operator zrobił od otwarcia zespołu.

Ciąg pisania w jednym polu MUST być cofany jako jedna zmiana, a nie znak po znaku. Cofnięcie
MUST NOT odbierać przeglądarce jej własnego cofania wewnątrz pola tekstowego.

Cofnięcie dotyczy szkicu, nie zapisu: MUST NOT usuwać zapisanej rewizji ani zatrzymywać
przebiegu. Zespół doprowadzony cofaniem z powrotem do stanu ostatniej rewizji MUST przestać
mieć niezapisane zmiany.

Canvas jest miejscem, w którym operator próbuje układów. Bez cofnięcia każda próba jest
zakładem: usunięta rola to prompt, wytyczne i narzędzia do napisania od nowa, a to zmienia
sposób pracy z „sprawdźmy" na „lepiej nie ruszać".

#### Scenario: Operator cofa usunięcie agenta

- **WHEN** operator usuwa agenta, a potem cofa ostatnią zmianę
- **THEN** agent wraca wraz ze swoim promptem, modelem i przypisanymi narzędziami

#### Scenario: Cofnięcie do stanu ostatniej rewizji

- **WHEN** operator cofa wszystkie zmiany wprowadzone od zapisu
- **THEN** zespół przestaje mieć niezapisane zmiany
- **AND** żadna zapisana rewizja nie zostaje usunięta

#### Scenario: Cofanie w polu tekstowym

- **WHEN** operator cofa zmianę, mając kursor w polu, w którym pisze
- **THEN** cofnięcie dotyczy tekstu w tym polu, a nie całego zespołu

### Requirement: Rozmieszczenie agentów jest wyborem operatora i przeżywa zamknięcie widoku

Operator MUST móc przesunąć agenta na obrazie zespołu, a moduł MUST zapamiętać to
rozmieszczenie i oddać je przy kolejnym otwarciu. Rozmieszczenie MUST NOT być częścią rewizji:
przesunięcie agenta MUST NOT tworzyć nowej rewizji ani zmieniać żadnej zapisanej.

Agent, którego rozmieszczenie nie obejmuje — dołożony po ostatnim przesunięciu albo obecny
w rewizji, na której biegnie oglądany przebieg — MUST dostać miejsce wyliczone z zależności,
zamiast wylądować w rogu.

Układ automatyczny odczytuje kierunek pracy i na tym kończy swoją wiedzę. Operator wie
o swoim zespole rzeczy, których w grafie nie ma — które role są tą samą myślą, co czym jest
tylko podparte — i to jest jedyna rzecz, którą obraz może po nim zapamiętać. Poza rewizją,
bo dwa przebiegi tej samej rewizji MUST różnić się odpowiedzią modelu, nigdy pikselami.

#### Scenario: Operator przesuwa agenta i wraca do zespołu

- **WHEN** operator przesuwa agenta na obrazie zespołu, zamyka zespół i otwiera go ponownie
- **THEN** agent jest tam, gdzie operator go zostawił

#### Scenario: Przesunięcie nie jest zmianą definicji

- **WHEN** operator przesuwa agenta i nie zmienia niczego więcej
- **THEN** wersja zespołu pozostaje ta sama
- **AND** żadna zapisana rewizja się nie zmienia

#### Scenario: Agent bez zapamiętanego miejsca

- **WHEN** operator otwiera zespół, do którego dołożył agenta po ostatnim przesuwaniu
- **THEN** ten agent dostaje miejsce wyliczone z zależności, a pozostali zostają tam, gdzie ich
  zostawiono

### Requirement: Zapis odrzucony przez moduł jest pokazany przy miejscu, którego dotyczy

Gdy moduł odrzuca zapis definicji, terminal MUST pokazać przyczynę i MUST wskazać agenta albo
zależność, której odmowa dotyczy. Terminal MUST NOT poprzestać na komunikacie ogólnym.

Odmowa mówiąca „definicja niepoprawna" przy zespole o ośmiu rolach zostawia operatora
z szukaniem po omacku tego, co moduł już wie.

#### Scenario: Zapis z cyklem zależności

- **WHEN** operator zapisuje zespół, w którym zależności tworzą cykl, a moduł odmawia
- **THEN** terminal pokazuje przyczynę
- **AND** wskazuje zależność, przez którą odmowa zapadła

### Requirement: Katalog pokazuje, co jest do uruchomienia

Terminal MUST pokazywać listę zapisanych zespołów z nazwą, opisem i momentem ostatniej zmiany,
a z tej listy MUST dać się otworzyć zespół do edycji i uruchomić jego przebieg.

#### Scenario: Wejście do zakładki

- **WHEN** operator wchodzi na zakładkę zespołów
- **THEN** widzi listę zapisanych zespołów
- **AND** z każdej pozycji może otworzyć zespół albo uruchomić przebieg

### Requirement: Przebieg widać na obrazie zespołu w trakcie, nie po fakcie

W trakcie przebiegu terminal MUST pokazywać na obrazie zespołu, który agent czeka, który
pracuje, a który skończył, i MUST udostępniać to, co agenci wypracowali, oraz wywołane przez
nich narzędzia. Zamknięcie widoku MUST NOT przerwać przebiegu, a ponowne otwarcie MUST pokazać
stan bieżący.

Przebieg zespołu trwa dłużej niż jedna odpowiedź modelu. Obraz, na którym nic się nie zmienia,
nie daje odróżnić pracy od zawieszenia — a to jest pierwsza rzecz, którą operator chce
wiedzieć.

#### Scenario: Przebieg w toku

- **WHEN** przebieg trwa, a pracuje drugi z trzech agentów
- **THEN** obraz zespołu pokazuje pierwszego jako zakończonego, drugiego jako pracującego,
  a trzeciego jako czekającego

#### Scenario: Operator wraca do trwającego przebiegu

- **WHEN** operator zamyka widok przebiegu i otwiera go ponownie
- **THEN** przebieg pracuje nieprzerwanie
- **AND** widok pokazuje stan bieżący, a nie stan sprzed zamknięcia

#### Scenario: Przebieg zatrzymany z powodu kosztu

- **WHEN** przebieg zostaje zatrzymany po przekroczeniu granicy kosztu
- **THEN** terminal pokazuje koszt jako przyczynę zatrzymania
- **AND** pokazuje to, co agenci zdążyli wypracować

### Requirement: Złożone zlecenia widać przy agencie, który je złożył

Terminal MUST pokazywać na obrazie przebiegu zlecenia złożone przez zespół — przy tym agencie,
który je złożył — wraz z symbolem, kierunkiem, wielkością i skutkiem. Zlecenie o skutku
nieznanym MUST być pokazane jako nieznane, a MUST NOT być pominięte ani pokazane jako nieudane.

Operator patrzący na przebieg, który rusza rachunek, ma najpierw jedno pytanie: co już poszło.
Odpowiedź schowana w liście wywołań narzędzi jest odpowiedzią, której się szuka.

#### Scenario: Przebieg, w którym padło zlecenie

- **WHEN** agent w trwającym przebiegu składa zlecenie
- **THEN** przy tym agencie pojawia się zlecenie z symbolem, kierunkiem, wielkością i skutkiem

#### Scenario: Zlecenie bez znanego skutku

- **WHEN** wywołanie zapisujące skończyło się awarią dostępu
- **THEN** terminal pokazuje je jako zlecenie o nieznanym skutku

### Requirement: Granice handlowe ustawia się w tym samym widoku co resztę zespołu

Terminal MUST pozwalać ustawić granice handlowe zespołu — maksymalną wielkość zlecenia, liczbę
zleceń na przebieg i dobową — w widoku, w którym operator składa zespół. Każda z nich MUST dać
się zostawić pustą, a pusta MUST znaczyć „bez ograniczenia": terminal MUST NOT wymagać żadnej z
nich do zapisu ani podstawiać za operatora wartości domyślnej.

**Reason**: wymóg zapisany tu pierwotnie brzmiał odwrotnie — odmowa zapisu rewizji z narzędziem
zapisującym i bez granic, pokazana przy agencie. Został odwrócony w grupie 6 tej zmiany, na
polecenie operatora i przed napisaniem kodu: granice są mechanizmem, którym operator dysponuje,
a nie zgodą, której moduł mu udziela (`teams-trading`, „Każda granica handlowa daje się wyłączyć,
a moduł żadnej nie narzuca"). Terminal, który dalej by tej odmowy pilnował, pilnowałby czegoś,
czego moduł już nie mówi.

#### Scenario: Operator przypisuje narzędzie zapisujące bez granic

- **WHEN** operator przypisuje agentowi narzędzie zmieniające stan rachunku i zapisuje zespół
  bez ustawionych granic handlowych
- **THEN** zespół zostaje zapisany
- **AND** terminal MUST NOT pokazać z tego powodu odmowy ani ostrzeżenia

#### Scenario: Narzędzia zapisujące są rozpoznawalne przy wyborze

- **WHEN** operator wybiera narzędzia dla agenta
- **THEN** narzędzia zmieniające stan rachunku są odróżnione od czytających

### Requirement: Zatrzymanie z powodu granicy zleceń jest pokazane jako takie

Terminal MUST pokazywać granicę zleceń jako przyczynę zatrzymania przebiegu, odróżniając ją od
granicy kosztu, i MUST pokazywać to, co zespół zdążył wypracować i złożyć.

#### Scenario: Przebieg zatrzymany granicą zleceń

- **WHEN** przebieg zostaje zatrzymany po wyczerpaniu dopuszczalnej liczby zleceń
- **THEN** terminal nazywa granicę zleceń jako przyczynę
- **AND** pokazuje złożone dotąd zlecenia

### Requirement: Zakończony przebieg pokazuje treść każdego wywołania, także obserwowanego na żywo

Kiedy przebieg się kończy, terminal MUST doczytać nagrane wywołania narzędzi i pokazywać ich
argumenty oraz odpowiedzi — również tych wywołań, które przyszły strumieniem w trakcie
obserwowania i przyszły bez treści.

Bez tego operator, który patrzył na przebieg od początku, widzi mniej niż ten, który otworzył
go po fakcie — a to pierwszy z nich siedzi przy nieudanym zleceniu i pyta, co dokładnie
zostało wysłane. Odczyt po zakończeniu jest też momentem, w którym nagrane wiersze są
kompletne: przebieg nie dopisze już żadnego.

Lista wywołań po tym odczycie MUST NOT nieść tego samego wywołania dwa razy.

#### Scenario: Wywołanie obserwowane na żywo, czytane po zakończeniu

- **WHEN** przebieg kończy się, a operator rozwija wywołanie, które przyszło strumieniem
- **THEN** widzi jego argumenty i wynik albo powód odmowy
- **AND** wpis nie mówi już, że treść nie została odczytana

#### Scenario: Wywołanie nagrane i to samo wywołanie ze strumienia

- **WHEN** to samo wywołanie dotarło strumieniem i zostało doczytane z nagranych wierszy
- **THEN** okno pokazuje je jeden raz

### Requirement: Wywołanie narzędzia w oknie outputów da się rozwinąć

Okno, w którym operator czyta, co agenci napisali, MUST pozwalać rozwinąć wpis wywołanego
narzędzia i zobaczyć argumenty, którymi je wywołano, oraz treść wyniku albo powód odmowy.
Wpisy MUST być zwinięte, dopóki operator ich nie rozwinie.

To ta sama potrzeba, którą transkrypt czatu zaspokaja od początku: wynik narzędzia jest tym,
z czego wzięła się odpowiedź modelu, a wpis mówiący samo „ok" każe brać ją na słowo. Odczyt
zespołu jest tu trudniejszy niż rozmowy — agentów jest kilku, a wynik jednego bywa całym
wejściem następnego.

Okno MUST powiedzieć wprost, kiedy treści wywołania jeszcze nie ma, i MUST NOT pokazywać jej
braku jako pustej odpowiedzi. Przebieg w trakcie zgłasza wywołania szybciej, niż okno je
doczytuje, a pusty wynik czyta się jak narzędzie, które nic nie zwróciło.

#### Scenario: Operator rozwija wywołanie

- **WHEN** operator rozwija wpis wywołania w oknie outputów
- **THEN** widzi argumenty, którymi narzędzie wywołano, i treść wyniku albo powód odmowy

#### Scenario: Wpisy są zwinięte na wejściu

- **WHEN** operator otwiera okno outputów przebiegu, w którym agenci wywoływali narzędzia
- **THEN** wywołania są wypisane zwinięte
- **AND** żadne z nich nie zajmuje ekranu, dopóki nie zostanie rozwinięte

#### Scenario: Treść wywołania jeszcze nie dotarła

- **WHEN** operator rozwija wywołanie, którego treści okno jeszcze nie odczytało
- **THEN** wpis mówi, że treść nie została jeszcze odczytana
- **AND** MUST NOT pokazywać pustego wyniku ani pustych argumentów

#### Scenario: Wywołanie zakończone odmową

- **WHEN** operator rozwija wpis wywołania oznaczonego jako odmowa
- **THEN** widzi powód odmowy

### Requirement: Przebieg da się uruchomić z widoku przebiegów zespołu

Terminal MUST pozwalać uruchomić przebieg zespołu z widoku jego przebiegów, nie tylko
z katalogu. Uruchomienie MUST być potwierdzone przez operatora, a potwierdzenie MUST nazywać
rewizję, która zostanie uruchomiona. Po uruchomieniu widok MUST pokazać nowy przebieg jako
oglądany. Odmowę modułu — wyczerpaną granicę dobową, rewizję nie do uruchomienia —
terminal MUST pokazać słowami modułu.

Widok przebiegów jest miejscem, w którym operator porównuje to, co zespół powiedział wczoraj,
z tym, co mówi dziś. „Uruchom jeszcze raz, teraz" jest tam najczęstszym następnym ruchem,
a droga do niego prowadzi dziś przez wyjście z tego widoku i powrót do niego.

#### Scenario: Uruchomienie z listy przebiegów

- **WHEN** operator potwierdza uruchomienie przebiegu w widoku przebiegów zespołu
- **THEN** rusza przebieg na rewizji nazwanej w potwierdzeniu
- **AND** widok pokazuje ten przebieg jako oglądany

#### Scenario: Uruchomienie odrzucone przez moduł

- **WHEN** moduł odmawia uruchomienia przebiegu
- **THEN** operator widzi powód podany przez moduł
- **AND** oglądany przebieg pozostaje ten, który oglądał

#### Scenario: Rezygnacja z uruchomienia

- **WHEN** operator zamyka potwierdzenie bez zgody
- **THEN** żaden przebieg nie rusza

### Requirement: Pamięć zespołu jest widoczna przy zespole i to operator ją prostuje

Terminal MUST pokazywać wpisy pamięci wybranego zespołu — treść, agenta, który je zapisał, moment
zapisu i przebieg, z którego pochodzą — od najnowszego. Operator MUST móc usunąć pojedynczy wpis, a
usunięcie MUST wymagać potwierdzenia i MUST nazwać, że wpis nie trafi już do kolejnych przebiegów.
Terminal MUST NOT pozwalać na edycję wpisu.

Pamięć jest jedyną rzeczą w tym module, która wpływa na kolejny przebieg, a nie jest widoczna
w rewizji ani w śladzie tego przebiegu. Zespół, który zapamiętał nieprawdę, powtarza ją odtąd przy
każdym uruchomieniu i płaci za to za każdym razem — operator, który nie ma gdzie tego zobaczyć,
szuka przyczyny w promptach.

Zespół bez ani jednego wpisu MUST być pokazany jako zespół, który jeszcze nic nie zapamiętał, a nie
jako pusty widok bez wyjaśnienia — brak pamięci jest stanem normalnym, w szczególności dla zespołu,
którego żaden agent nie ma przypisanego narzędzia zapisu.

#### Scenario: Operator ogląda pamięć zespołu

- **WHEN** operator otwiera pamięć zespołu, który ma zapisane wpisy
- **THEN** widzi je od najnowszego, z treścią, agentem, momentem zapisu i wskazaniem przebiegu

#### Scenario: Operator usuwa nietrafiony wpis

- **WHEN** operator usuwa wybrany wpis i potwierdza
- **THEN** wpis znika z listy
- **AND** pozostałe wpisy zostają nietknięte

#### Scenario: Zespół, który jeszcze nic nie zapamiętał

- **WHEN** operator otwiera pamięć zespołu bez ani jednego wpisu
- **THEN** widzi, że zespół niczego jeszcze nie zapamiętał
