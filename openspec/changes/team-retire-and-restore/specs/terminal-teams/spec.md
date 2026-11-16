## ADDED Requirements

### Requirement: Wycofane zespoły są widoczne i dają się przywrócić

Zakładka zespołów MUST pozwalać przełączyć się na listę wycofanych zespołów, pokazującą nazwę, opis, ostatnią
rewizję i moment wycofania, i MUST pozwalać przywrócić każdy z nich. Terminal MUST powiedzieć przy
przywróceniu, że harmonogramy zostają wyłączone.

#### Scenario: Przywrócenie z listy wycofanych

- **WHEN** operator otwiera listę wycofanych i przywraca zespół
- **THEN** zespół znika z listy wycofanych i pojawia się w katalogu aktywnych
- **AND** operator przed potwierdzeniem widzi, że harmonogramy trzeba włączyć samemu
