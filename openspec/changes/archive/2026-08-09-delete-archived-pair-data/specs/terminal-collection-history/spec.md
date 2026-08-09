## ADDED Requirements

### Requirement: Skasowanie danych widać w historii

Zakładka MUST pokazywać skasowania danych obok dociągnięć, w jednym porządku czasu — dociągnięcie i
skasowanie tej samej pary to dwa zdarzenia z tej samej historii, a rozdzielone na dwie listy nie
dałyby się przeczytać jako ciąg przyczyn. Wpis o skasowaniu MUST podawać, kiedy nastąpiło, jakiej
pary dotyczyło, ile świec zostało usuniętych i jaki zakres czasu obejmowały.

Wpis o skasowaniu MUST być odróżnialny od dociągnięcia na pierwszy rzut oka i MUST NOT być pokazany
kolorem zarezerwowanym dla powodzenia — skasowanie nie jest ani sukcesem, ani porażką, tylko
odjęciem danych.

#### Scenario: Historia pary po skasowaniu

- **WHEN** operator patrzy na historię pary, której dane skasowano po wcześniejszym dociągnięciu
- **THEN** widzi oba zdarzenia, od najnowszego
- **AND** wpis o skasowaniu podaje moment, liczbę usuniętych świec i zakres czasu, który obejmowały

#### Scenario: Skasowanie odróżnia się od dociągnięcia

- **WHEN** w historii sąsiadują wpis o dociągnięciu i wpis o skasowaniu
- **THEN** operator rozróżnia je bez czytania szczegółów
- **AND** wpis o skasowaniu MUST NOT wyglądać jak zakończone powodzeniem dociąganie

#### Scenario: Instrument skasowany w całości

- **WHEN** operator skasował wszystkie interwały instrumentu
- **THEN** historia tego instrumentu jest nadal odczytywalna wraz z wpisami o skasowaniu
- **AND** MUST NOT znikać wraz z instrumentem z listy archiwizowanych
