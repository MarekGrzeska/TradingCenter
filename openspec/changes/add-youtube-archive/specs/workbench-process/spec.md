## ADDED Requirements

### Requirement: Archiwum YouTube jest obecne z konfiguracji albo nieobecne

Proces MUST montować archiwum YouTube wtedy i tylko wtedy, gdy jego baza jest skonfigurowana. Brak
konfiguracji bazy MUST być działającą konfiguracją: proces MUST wystartować bez tego archiwum, jego
ścieżki MUST NOT odpowiadać, jego narzędzia MUST NOT być widoczne dla rozmowy ani zespołów, a log
startu MUST to nazwać.

Gdy baza jest skonfigurowana, archiwum podlega regule „wszystko albo nic": jego baza nieosiągalna
albo migracja nieudana MUST zatrzymać start całego procesu. Nieobecność z konfiguracji to decyzja
operatora; „zamontowane, ale bez bazy" byłoby półstanem, którego ta specyfikacja zabrania.

#### Scenario: Baza archiwum nieskonfigurowana

- **WHEN** proces startuje bez ustawienia bazy archiwum YouTube
- **THEN** proces MUST wystartować i serwować pozostałe pakiety
- **AND** ścieżki archiwum MUST NOT odpowiadać, a jego narzędzi MUST NOT być na listach

#### Scenario: Baza skonfigurowana, ale nieosiągalna

- **WHEN** baza archiwum jest ustawiona, a nie odpowiada albo jej migracja się nie udaje
- **THEN** proces MUST NOT zacząć serwować czegokolwiek
- **AND** komunikat MUST nazywać bazę archiwum YouTube
