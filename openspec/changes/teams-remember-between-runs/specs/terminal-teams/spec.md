## ADDED Requirements

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
