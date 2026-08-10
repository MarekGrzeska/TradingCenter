## ADDED Requirements

### Requirement: Wpis historii zlecenia da się usunąć

Operator MUST móc usunąć zlecenie z historii — samo zlecenie razem ze wszystkimi jego
kawałkami. Usunięcie MUST być całością albo niczym: zlecenie bez kawałków i kawałki bez
zlecenia to obie postacie historii, której nie da się już przeczytać.

Usunięcie MUST NOT dotykać świec ani pokrycia zebranego przez to zlecenie. Historia mówi,
co było robione, a nie trzyma danych; skasowanie zapisu o pracy MUST NOT cofać jej wyniku.
Do usuwania świec służy skasowanie danych pary i to ono, a nie ta operacja, zostawia po
sobie ślad w historii.

Moduł MUST odmówić usunięcia zlecenia, w którym jakikolwiek kawałek jest w toku albo
czeka na wykonanie, i MUST nazwać powód — nie da się usunąć zapisu pracy, którą coś
właśnie wykonuje, bo ta praca dopisałaby się do usuniętego zlecenia. Odmowa MUST
zostawiać zlecenie nietknięte.

Prośba o usunięcie zlecenia, którego nikt nie utworzył, MUST zostać odmówiona w sposób
odróżnialny od odmowy z powodu pracy w toku — pierwsza mówi „nie ma czego usuwać", druga
„nie teraz", a operator podejmuje po nich różne decyzje.

Usunięcie MUST być trwałe: usunięte zlecenie MUST NOT wrócić do historii po restarcie
modułu.

#### Scenario: Usunięcie zlecenia zakończonego

- **WHEN** operator usuwa zlecenie, którego wszystkie kawałki się rozstrzygnęły
- **THEN** zlecenie i jego kawałki znikają z historii
- **AND** świece zebrane przez to zlecenie pozostają w archiwum, a pokrycie par się nie zmienia

#### Scenario: Usunięcie zlecenia, w którym coś trwa

- **WHEN** operator prosi o usunięcie zlecenia mającego kawałek w toku albo oczekujący
- **THEN** moduł odmawia i nazywa powód
- **AND** zlecenie wraz z kawałkami zostaje nietknięte

#### Scenario: Usunięcie zlecenia, którego nie ma

- **WHEN** operator prosi o usunięcie zlecenia o identyfikatorze, którego nikt nie utworzył
- **THEN** moduł odmawia w sposób odróżnialny od odmowy z powodu pracy w toku
- **AND** MUST NOT usunąć żadnego innego zlecenia

#### Scenario: Pozostałe zlecenia po usunięciu

- **WHEN** operator usuwa jedno z kilku zleceń dotyczących tej samej pary
- **THEN** pozostałe zlecenia tej pary są nadal odczytywalne, z tym samym wynikiem co przedtem
- **AND** ich kawałki pozostają nienaruszone

#### Scenario: Usunięcie przeżywa restart

- **WHEN** moduł zostaje zatrzymany i uruchomiony ponownie po usunięciu zlecenia
- **THEN** usunięte zlecenie nadal nie występuje w historii
