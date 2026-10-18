## ADDED Requirements

### Requirement: Pakiet alertów jest obecny z konfiguracji albo nieobecny

Proces MUST montować pakiet alertów wtedy i tylko wtedy, gdy jego baza jest skonfigurowana. Brak
konfiguracji bazy MUST być działającą konfiguracją: proces MUST wystartować bez tego pakietu, jego
ścieżki MUST NOT odpowiadać, jego narzędzia MUST NOT być widoczne dla rozmowy ani zespołów, pakiety
publikujące zdarzenia MUST działać dalej bez publikacji, a log startu MUST to nazwać.

Gdy baza jest skonfigurowana, pakiet podlega regule „wszystko albo nic”: jego baza nieosiągalna albo
migracja nieudana MUST zatrzymać start całego procesu.

#### Scenario: Baza alertów nieskonfigurowana

- **WHEN** proces startuje bez ustawienia bazy alertów
- **THEN** proces MUST wystartować i serwować pozostałe pakiety
- **AND** archiwa MUST zbierać i odczytywać normalnie, bez publikowania zdarzeń i bez stawiania znaczników publikacji

#### Scenario: Baza skonfigurowana, ale nieosiągalna

- **WHEN** baza alertów jest ustawiona, a nie odpowiada albo jej migracja się nie udaje
- **THEN** proces MUST NOT zacząć serwować czegokolwiek
- **AND** komunikat MUST nazywać bazę alertów
