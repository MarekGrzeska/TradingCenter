## REMOVED Requirements

### Requirement: Usunięcie zatrzymuje zbieranie, ale nie kasuje danych

**Reason**: Operator nie miał żadnej drogi, którą mógłby usunąć zebrane dane, a zostawione zakresy
pokrycia sprawiały, że ponowne dodanie pary z innym zakresem nie ściągało nic — zakres uchodził za
już pobrany. Obietnica „archiwum nie kasuje danych" zostaje zawężona do tego, co w niej istotne:
archiwum nie kasuje danych **samo z siebie**.

**Migration**: Zastąpione przez „Skasowanie pary zatrzymuje zbieranie i usuwa jej dane". Konsument,
który dotąd używał usunięcia pary jako sposobu na zwolnienie połączenia do providera z zachowaniem
świec, nie ma po tej zmianie takiej operacji — musi liczyć się z utratą danych albo nie usuwać pary.

## ADDED Requirements

### Requirement: Skasowanie pary zatrzymuje zbieranie i usuwa jej dane

Operator MUST móc skasować parę. Skasowanie MUST zatrzymać zbieranie, zwolnić połączenie do
providera oraz usunąć świece i zakresy pokrycia tej pary. Usunięcie świec i usunięcie pokrycia MUST
być jedną operacją niepodzielną — para bez świec, ale z zachowanym pokryciem, wygląda dla planowania
zleceń jak para już pobrana i nie zostałaby pobrana ponownie.

Archiwum MUST NOT kasować danych z żadnego innego powodu niż jawne żądanie skasowania: ani samo z
siebie, ani przy zmianie konfiguracji, ani przy zatrzymaniu i uruchomieniu modułu.

#### Scenario: Operator kasuje parę

- **WHEN** operator kasuje parę
- **THEN** moduł zatrzymuje jej ingest i zamyka związane z nią połączenie
- **AND** świece tej pary przestają być odczytywalne
- **AND** zakresy pokrycia tej pary przestają istnieć

#### Scenario: Ponowne dodanie pary skasowanej

- **WHEN** operator dodaje parę skasowaną wcześniej, wskazując moment, od którego chce mieć historię
- **THEN** żaden zakres nie uchodzi za już pokryty
- **AND** cała wskazana historia zostaje dociągnięta od nowa

#### Scenario: Skasowanie jednej pary nie rusza pozostałych

- **WHEN** operator kasuje jeden interwał instrumentu archiwizowanego w kilku
- **THEN** świece i pokrycie pozostałych interwałów tego instrumentu zostają nietknięte

#### Scenario: Restart modułu

- **WHEN** moduł zostaje zatrzymany i uruchomiony ponownie
- **THEN** żadna para nie traci ani jednej świecy z tego powodu

### Requirement: Skasowanie zostaje odnotowane

Skasowanie MUST zostawić trwały ślad: która para, kiedy, ile świec zostało usuniętych i jaki zakres
czasu obejmowały. Ślad MUST przeżyć restart modułu i MUST NOT zniknąć wraz z danymi, których dotyczy
— bez niego cofnięcie się zasięgu danych jest zdarzeniem bez wytłumaczenia.

Zlecenia dociągania tej pary MUST pozostać w historii po skasowaniu jej danych. Zlecenie jest
zapisem tego, co się wydarzyło, a skasowanie danych tego nie odwraca.

#### Scenario: Skasowanie pary z zebranymi danymi

- **WHEN** zostaje skasowana para, dla której zebrano świece
- **THEN** odnotowane zostaje, która para, kiedy, ile świec usunięto i jaki zakres czasu obejmowały

#### Scenario: Skasowanie pary bez ani jednej świecy

- **WHEN** zostaje skasowana para, która nie zebrała jeszcze nic
- **THEN** skasowanie i tak zostaje odnotowane, z liczbą usuniętych świec równą zeru

#### Scenario: Historia zleceń po skasowaniu

- **WHEN** operator odczytuje historię dla pary, której dane zostały skasowane
- **THEN** widzi wcześniejsze zlecenia dociągania tej pary
- **AND** widzi odnotowane skasowanie

#### Scenario: Restart po skasowaniu

- **WHEN** moduł zostaje uruchomiony ponownie po skasowaniu pary
- **THEN** odnotowane skasowanie jest nadal odczytywalne
