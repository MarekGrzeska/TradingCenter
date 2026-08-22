## ADDED Requirements

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
