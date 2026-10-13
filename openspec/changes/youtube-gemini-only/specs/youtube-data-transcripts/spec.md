## MODIFIED Requirements

### Requirement: Dostawca jest ustawieniem, nie kodem

Moduł MUST pobierać transkrypcje od jednego dostawcy wybranego ustawieniem: Gemini, który słucha filmu
z jego adresu, albo symulacji. Moduł MUST NOT czytać napisów YouTube. Każda transkrypcja MUST nieść
nazwę dostawcy, język, nazwę modelu i to, że tekst jest automatyczny. Wyjątek zgłoszony przez dostawcę
MUST być traktowany jak blokada.

#### Scenario: Film przepisany przez Gemini

- **WHEN** dostawcą jest Gemini, a film ma znaną długość
- **THEN** transkrypcja MUST zostać zapisana z dostawcą `gemini` i nazwą modelu

#### Scenario: Dostawca zgłasza wyjątek

- **WHEN** wywołanie dostawcy kończy się wyjątkiem
- **THEN** film MUST zostać oczekujący z nietkniętą liczbą prób, a przebieg MUST przestać pytać

### Requirement: Zablokowany dostawca odpoczywa

Dostawca, którego ostatnia odpowiedź była blokadą młodszą niż czas odpoczynku z ustawień, MUST NOT być
pytany. Po upływie tego czasu MUST zostać zapytany znowu. Dopóki odpoczywa, przebieg MUST NOT
transkrybować, a filmy MUST zostać oczekujące z nietkniętą liczbą prób.

Odmowa Gemini to przeciążony model albo limit zapytań — mija w minuty.

#### Scenario: Przeciążony model

- **WHEN** Gemini odmówił dziesięć minut temu, a odpoczynek trwa piętnaście
- **THEN** film MUST NOT zostać zapytany teraz i MUST zostać zapytany po upływie odpoczynku

## REMOVED Requirements

### Requirement: Napisy tylko w języku filmu

**Reason**: moduł nie czyta już napisów YouTube — z Azure YouTube odmawia każdemu zapytaniu, więc jedynym
dostawcą jest Gemini, który słucha filmu w jego języku.

**Migration**: brak; ustawienie `TRANSCRIPT_LANGUAGES` jest wycofane i nazywane przy starcie przez `scripts/dev.py`.
