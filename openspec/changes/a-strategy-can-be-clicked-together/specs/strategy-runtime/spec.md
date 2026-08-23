## MODIFIED Requirements

### Requirement: Każda ocena zostaje zapisana i daje się odtworzyć

Każda ocena MUST zostać zapisana wraz z faktami, na których stanęła, wersją zestawu
parametrów oraz — gdy liczył ją wpis pochodzący z bazy — rewizją definicji. Odtworzenie
oceny z zapisu MUST dawać decyzję identyczną z zapisaną, i MUST być wykonalne wyłącznie
z rzeczy zapisanych: bez pytania archiwum i bez czytania bieżącego brzmienia definicji.

To jest dziennik systemowy strategii: bez snapshotu wejścia decyzja jest anegdotą, a spór
„czemu system wszedł" nie ma rozstrzygnięcia. Odkąd reguła jest danymi, snapshot wejścia
przestał być całością pochodzenia — odtworzenie sięgające po dzisiejsze brzmienie definicji
odpowiadałoby na inne pytanie niż zadane, i odpowiadałoby na nie przekonująco.

#### Scenario: Odtworzenie zapisanej oceny

- **WHEN** zapisana ocena zostaje odtworzona z jej faktów i wersji parametrów
- **THEN** wynik odtworzenia jest identyczny z decyzją zapisaną

#### Scenario: Odtworzenie oceny po zmianie definicji

- **WHEN** definicja doczekała się nowszej rewizji, a operator odtwarza decyzję sprzed niej
- **THEN** odtworzenie korzysta z rewizji zapisanej przy tej decyzji, nie z najnowszej
- **AND** wynik odtworzenia jest identyczny z decyzją zapisaną
