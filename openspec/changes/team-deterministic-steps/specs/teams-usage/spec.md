## MODIFIED Requirements

### Requirement: Przekroczenie granicy kosztu zatrzymuje przebieg

Definicja zespołu MUST móc nieść granicę kosztu jednego przebiegu oraz granicę kosztu dobowego
dla zespołu. Moduł MUST sprawdzić granicę przed wywołaniem modelu i MUST zatrzymać przebieg ze
statusem nazywającym koszt jako przyczynę, zamiast wykonać wywołanie przekraczające granicę.

Sprawdzenie MUST zapadać w module, a MUST NOT być powierzone treści promptu. Prompt jest
proszeniem modelu, żeby się ograniczył; granica kosztu ma trzymać także wtedy, gdy model
poprosi o to, o co nie powinien — a przy zespole wołanym harmonogramem w nocy jest to jedyna
rzecz stojąca między eksperymentem a rachunkiem, którego nikt nie zatwierdził.

Granica kosztu dotyczy wywołań modelu, a krok deterministyczny (`teams-steps`) żadnego nie robi.
Wyczerpana granica dobowa MUST więc odmówić uruchomienia tylko rewizji bez kroków. Rewizja z
krokami MUST ruszyć: jej kroki pracują, jej agenci MUST NOT wywołać modelu, a przebieg kończy się
statusem nazywającym granicę dobową. Inaczej wydatek na rozmowy z modelem w ciągu dnia mógłby
zablokować zamknięcie pozycji, które nie kosztuje nic.

#### Scenario: Przebieg dobija do granicy w połowie pracy

- **WHEN** koszt trwającego przebiegu osiąga granicę przed wywołaniem kolejnego agenta
- **THEN** przebieg zostaje zatrzymany ze statusem nazywającym koszt jako przyczynę
- **AND** ślad tego, co zdążyło się wydarzyć, pozostaje zapisany

#### Scenario: Zespół wyczerpał granicę dobową

- **WHEN** operator uruchamia przebieg zespołu bez kroków, którego koszt dobowy jest już wyczerpany
- **THEN** moduł odmawia uruchomienia, nazywając granicę dobową jako przyczynę

#### Scenario: Zespół z krokiem wyczerpał granicę dobową

- **WHEN** harmonogram uruchamia zespół z krokiem i agentem, którego koszt dobowy jest już wyczerpany
- **THEN** przebieg rusza i krok wykonuje swój przepis
- **AND** agent nie wywołuje modelu
- **AND** przebieg kończy się statusem nazywającym granicę dobową

#### Scenario: Zespół bez ustawionych granic

- **WHEN** definicja nie niesie żadnej granicy kosztu
- **THEN** przebieg rusza i nie jest zatrzymywany z powodu kosztu
