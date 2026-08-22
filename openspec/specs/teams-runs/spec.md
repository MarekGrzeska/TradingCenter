# teams-runs Specification

## Purpose
Co dzieje się, gdy zespół zostaje uruchomiony: w jakiej kolejności pracują agenci, co widzi
każdy z nich, kiedy przebieg się kończy, co po nim zostaje i co widać, zanim się skończy.
## Requirements
### Requirement: Przebieg odbywa się na rewizji, nie na zespole

Przebieg MUST wskazywać rewizję, na której się odbył, i MUST NOT być opisany samą nazwą
zespołu. Zmiana definicji po uruchomieniu MUST NOT zmienić tego, na czym przebieg się odbył.

Dwa przebiegi tej samej rewizji różnią się wtedy tylko tym, czym miały się różnić — odpowiedzią
modelu i stanem rynku. To jedyny układ, w którym porównanie dwóch wyników mówi cokolwiek
o zespołach, a nie o tym, co operator zmienił po drodze.

#### Scenario: Definicja zmieniona w trakcie przebiegu

- **WHEN** operator zapisuje kolejną rewizję zespołu, gdy jego przebieg jeszcze trwa
- **THEN** trwający przebieg pracuje dalej na rewizji, z którą ruszył
- **AND** ślad tego przebiegu wskazuje tamtą rewizję

### Requirement: Kolejność pracy agentów wynika z zależności

Agent MUST zacząć pracę dopiero wtedy, gdy skończyli wszyscy, od których prowadzi do niego
zależność. Agenci, których zależności są już spełnione, MAY pracować równocześnie.

#### Scenario: Dwie role bez zależności między sobą

- **WHEN** przebieg dochodzi do dwóch agentów, między którymi nie ma zależności, a ich
  poprzednicy skończyli
- **THEN** obaj mogą pracować równocześnie

#### Scenario: Rola zbierająca wyniki dwóch innych

- **WHEN** do agenta prowadzą zależności od dwóch innych, z których jeden już skończył
- **THEN** agent nie zaczyna, dopóki nie skończy również drugi

### Requirement: Agent widzi wypowiedzi poprzedników, a nie całą historię przebiegu

Agentowi MUST zostać podane to, co wypracowali agenci, od których prowadzi do niego zależność.
MUST NOT być mu podawana praca agentów, z którymi nie łączy go żadna zależność.

Zależność jest w tej definicji nośnikiem informacji i to jest informacja, którą niesie. Zespół,
w którym każdy widzi wszystko, jest jednym agentem z kilkoma promptami — rozdzielenie ról
przestaje wtedy cokolwiek znaczyć, a koszt rośnie z każdą kolejną rolą.

#### Scenario: Rola nie sąsiadująca z inną

- **WHEN** dwaj agenci pracują w tym samym przebiegu, a między nimi nie ma zależności
- **THEN** żaden z nich nie dostaje pracy drugiego

### Requirement: Praca pojedynczego agenta ma skończoną liczbę rund

Wymiana między modelem a narzędziami w obrębie jednego agenta MUST mieć górną granicę liczby
rund. Po jej osiągnięciu agent MUST dokończyć pracę bez dalszego sięgania po narzędzia, zamiast
sięgać po nie dalej.

#### Scenario: Agent osiąga granicę rund

- **WHEN** agent wyczerpał dozwoloną liczbę rund z narzędziami, a nie zakończył wypowiedzi
- **THEN** kolejne wywołanie modelu odbywa się bez narzędzi
- **AND** ślad przebiegu pokazuje, że granica została osiągnięta

### Requirement: Przebieg ma skończony czas i daje się przerwać

Przebieg MUST mieć górną granicę czasu trwania i po jej przekroczeniu MUST zostać zatrzymany
ze statusem nazywającym czas jako przyczynę. Operator MUST móc przerwać trwający przebieg,
a przerwany przebieg MUST zachować to, co zdążył wypracować.

#### Scenario: Operator przerywa przebieg w trakcie

- **WHEN** operator przerywa trwający przebieg
- **THEN** przebieg kończy się ze statusem mówiącym o przerwaniu
- **AND** praca agentów, którzy zdążyli skończyć, pozostaje w śladzie

#### Scenario: Przebieg przekracza dozwolony czas

- **WHEN** przebieg trwa dłużej, niż wolno
- **THEN** zostaje zatrzymany, a jego status nazywa czas jako przyczynę

### Requirement: Ślad przebiegu zostaje niezależnie od tego, jak przebieg się skończył

Moduł MUST zapisać dla każdego przebiegu jego status, pracę każdego agenta, który ruszył, oraz
każde wywołanie narzędzia wraz z jego wynikiem. Ślad MUST zostać także wtedy, gdy przebieg
skończył się błędem, przerwaniem albo przekroczeniem limitu.

Przebieg nieudany jest wynikiem eksperymentu tak samo jak udany, a częściej bywa tym
interesującym. Ślad zapisywany dopiero na końcu przepadałby dokładnie wtedy, gdy jest
potrzebny.

#### Scenario: Przebieg kończy się błędem w połowie

- **WHEN** przebieg przerywa błąd przy pracy jednego z agentów
- **THEN** status przebiegu nazywa błąd
- **AND** praca agentów, którzy skończyli wcześniej, oraz ich wywołania narzędzi pozostają
  w śladzie

### Requirement: Postęp przebiegu widać w trakcie, a nie dopiero po nim

Moduł MUST udostępniać postęp trwającego przebiegu na bieżąco: który agent pracuje, który
skończył i co wywołał. Zerwanie połączenia odbierającego postęp MUST NOT przerwać przebiegu.

Przebieg zespołu trwa dłużej niż jedna odpowiedź modelu i operator, który do końca widzi tylko
klepsydrę, nie ma jak odróżnić pracy od zawieszenia.

#### Scenario: Operator zamyka podgląd w trakcie

- **WHEN** operator zamyka podgląd trwającego przebiegu
- **THEN** przebieg pracuje dalej
- **AND** po ponownym otwarciu widać jego bieżący stan

#### Scenario: Przebieg wystartowany, agent jeszcze nie skończył

- **WHEN** pierwszy agent pracuje, a pozostali czekają na zależności
- **THEN** odbierający postęp widzi, który agent pracuje, a który czeka

### Requirement: Przebieg, który ruszył rachunek, niesie to w śladzie obok wypracowanej pracy

Ślad przebiegu, w którym padło wywołanie zmieniające stan rachunku, MUST nieść zarówno to, co
agenci wypracowali, jak i wywołania, które wykonali, wraz z ich skutkiem. Jedno bez drugiego
MUST NOT być podane jako komplet.

Rekomendacja bez zleceń nie mówi, co się naprawdę stało; zlecenia bez rekomendacji nie mówią,
dlaczego. Eksperyment porównuje jedno z drugim, więc ślad musi je trzymać razem.

#### Scenario: Przebieg zakończony złożonym zleceniem

- **WHEN** przebieg kończy się po tym, jak agent złożył zlecenie
- **THEN** ślad niesie wypracowaną pracę agentów oraz złożone zlecenie z jego skutkiem

#### Scenario: Przebieg przerwany po złożeniu zlecenia

- **WHEN** operator przerywa przebieg już po tym, jak agent złożył zlecenie
- **THEN** ślad zlecenia pozostaje zapisany
- **AND** zlecenie MUST NOT zostać cofnięte przez samo przerwanie przebiegu

### Requirement: Powód zatrzymania odróżnia granicę zleceń od granicy kosztu

Status zatrzymanego przebiegu MUST nazywać, która granica go zatrzymała. Zatrzymanie z powodu
wyczerpanej liczby zleceń MUST być odróżnialne od zatrzymania z powodu kosztu.

Operator reaguje na jedno i drugie inaczej: wyczerpany koszt to droższy eksperyment, wyczerpane
zlecenia to zespół, który chciał handlować więcej, niż mu wolno — i to drugie jest wynikiem
eksperymentu, a nie jego awarią.

#### Scenario: Przebieg zatrzymany granicą zleceń

- **WHEN** przebieg zostaje zatrzymany po wyczerpaniu dopuszczalnej liczby zleceń
- **THEN** jego status nazywa granicę zleceń jako przyczynę
- **AND** jest to inny powód niż zatrzymanie z powodu kosztu

### Requirement: Przebieg niesie zespół i właściciela, a nie samą rewizję

Wykonanie przebiegu MUST znać zespół, którego przebieg dotyczy, i tożsamość operatora, w którego
imieniu się odbywa. Jedno i drugie MUST pochodzić z uruchomienia przebiegu, a MUST NOT być
odtwarzane z treści rewizji ani z argumentu wypełnionego przez model.

Rewizja mówi, jak zespół pracuje, ale nie mówi, którym jest zespołem — ta sama definicja może stać
pod dwiema nazwami u dwóch operatorów. Wszystko, co przeżywa jeden przebieg i ma być czytelne
w kolejnym, jest zakotwiczone w zespole, więc bez tych dwóch rzeczy narzędzie sięgające po taki
zapis nie ma czym rozstrzygnąć, czyj zapis ma czytać — a zgadnięcie oznaczałoby tu oddanie cudzej
pamięci.

#### Scenario: Uruchomienie z terminala

- **WHEN** operator uruchamia przebieg zespołu
- **THEN** wykonanie przebiegu zna ten zespół i tego operatora

#### Scenario: Uruchomienie z harmonogramu

- **WHEN** przebieg rusza z harmonogramu, bez żądania operatora w tej chwili
- **THEN** wykonanie zna zespół i tożsamość operatora, do którego ten harmonogram należy
- **AND** MUST NOT posłużyć się tożsamością samego procesu
