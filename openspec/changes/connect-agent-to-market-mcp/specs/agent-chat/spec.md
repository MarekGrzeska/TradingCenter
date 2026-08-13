## MODIFIED Requirements

### Requirement: Agent pracuje na jednym prompcie systemowym

Moduł MUST prowadzić rozmowę z promptem systemowym opisującym agenta terminala
tradingowego. Prompt MUST być wersjonowany, a sesja MUST nieść identyfikator wersji, na
której powstała — bez tego o starym transkrypcie nie da się powiedzieć, na co właściwie
agent wtedy odpowiadał, a zmiana promptu unieważnia wnioski z każdej wcześniejszej
rozmowy naraz.

Prompt MUST nazywać granice agenta zgodnie z tym, co agent naprawdę ma. Gdy agent ma
narzędzia sięgające do archiwum, prompt MUST mówić, że dane pochodzą z archiwum
zbierającego wybrane pary, a nie z całego rynku, i że brak świec w zebranym oknie nie
jest ciszą rynku. Gdy agent narzędzi nie ma — bo serwer narzędzi jest niedostępny albo
nieskonfigurowany — prompt MUST mówić to samo, co mówił zawsze: agent nie widzi świec,
wskaźników ani pozycji i MUST NOT twierdzić inaczej.

Agent MUST NOT wystawiać rekomendacji inwestycyjnej. Agent MUST NOT podawać liczby jako
ceny, której nie dostał — ani z rozmowy, ani z narzędzia.

#### Scenario: Sesja pamięta wersję promptu

- **WHEN** sesja powstaje
- **THEN** zostaje przy niej zapisany identyfikator wersji promptu systemowego

#### Scenario: Prompt zmienia się między rozmowami

- **WHEN** prompt systemowy zostaje zmieniony, a operator otwiera sesję sprzed zmiany
- **THEN** transkrypt nadal wskazuje wersję, na której powstał
- **AND** dalszy ciąg tej rozmowy MUST być prowadzony na wersji obowiązującej teraz, z
  zapisem tej wersji przy nowych wiadomościach

#### Scenario: Prompt nazywa granice tego, co narzędzia mówią

- **WHEN** agent ma narzędzia sięgające do archiwum
- **THEN** prompt nazywa, że archiwum zbiera wybrane pary, a nie cały rynek
- **AND** nazywa, że brak świec nie jest sam z siebie ciszą rynku

#### Scenario: Agent bez narzędzi mówi, że ich nie ma

- **WHEN** serwer narzędzi jest niedostępny, a operator pyta o cenę
- **THEN** agent mówi, że nie ma teraz dostępu do tych danych
- **AND** MUST NOT podać liczby ani stwierdzić, że archiwum jej nie ma
