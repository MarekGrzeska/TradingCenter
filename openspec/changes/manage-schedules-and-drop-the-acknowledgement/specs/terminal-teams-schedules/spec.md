## ADDED Requirements

### Requirement: Harmonogram da się usunąć z listy, nie tylko zatrzymać

Terminal MUST pozwalać usunąć harmonogram i wyzwalacz z listy, obok wyłączenia i osobno od
niego. Usunięcie MUST wymagać potwierdzenia i MUST nazwać w nim to, co zniknie bezpowrotnie
— historię wyzwoleń tego wpisu — oraz to, co zostaje: przebiegi, które z niego wystartowały,
wraz z ich kosztem.

Wyłączenie i usunięcie MUST być rozróżnialne wzrokiem, zanim operator kliknie. Lista, na
której jedyną drogą do pozbycia się wpisu jest jego wyłączenie, rośnie w jedną stronę: wpisy
wyłączone i zapomniane wyglądają jak wpisy czekające na wznowienie.

#### Scenario: Operator usuwa harmonogram z listy

- **WHEN** operator wybiera usunięcie harmonogramu i potwierdza
- **THEN** harmonogram znika z listy
- **AND** lista jest odczytana z modułu na nowo, a nie poprawiona lokalnie

#### Scenario: Potwierdzenie mówi, co zniknie

- **WHEN** operator wybiera usunięcie harmonogramu, który wyzwalał się wcześniej
- **THEN** potwierdzenie nazywa historię wyzwoleń jako to, co znika bezpowrotnie
- **AND** mówi, że przebiegi i ich koszt zostają

#### Scenario: Operator rezygnuje z usunięcia

- **WHEN** operator zamyka potwierdzenie bez zgody
- **THEN** harmonogram zostaje nietknięty i dalej się wyzwala

#### Scenario: Zatrzymanie zostaje osobną czynnością

- **WHEN** operator chce, żeby harmonogram przestał chodzić, ale został
- **THEN** ma na to wyłączenie, bez przechodzenia przez usunięcie
