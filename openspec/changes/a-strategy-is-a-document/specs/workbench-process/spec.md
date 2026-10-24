## ADDED Requirements

### Requirement: Pakiet strategii jest obecny z konfiguracji albo nieobecny

Proces MUST montować pakiet strategii wtedy i tylko wtedy, gdy jego baza jest skonfigurowana. Brak konfiguracji
bazy MUST być działającą konfiguracją: proces MUST wystartować bez tego pakietu, jego ścieżki MUST NOT
odpowiadać, a log startu MUST to nazwać.

Gdy baza jest skonfigurowana, pakiet podlega regule „wszystko albo nic”: jego baza nieosiągalna albo migracja
nieudana MUST zatrzymać start całego procesu. Uruchomienie backtestu MUST NOT wstrzymywać obsługi tras
pozostałych pakietów.

#### Scenario: Baza strategii nieskonfigurowana

- **WHEN** proces startuje bez ustawienia bazy strategii
- **THEN** proces MUST wystartować i serwować pozostałe pakiety
- **AND** ścieżki pod `/strategies` MUST NOT odpowiadać jak trasy pakietu

#### Scenario: Baza skonfigurowana, ale nieosiągalna

- **WHEN** baza strategii jest ustawiona, a nie odpowiada albo jej migracja się nie udaje
- **THEN** proces MUST NOT zacząć serwować czegokolwiek
- **AND** komunikat MUST nazywać bazę strategii

#### Scenario: Backtest w toku

- **WHEN** uruchomienie backtestu liczy wieloletni zakres
- **THEN** trasy `/market` i rozmowy MUST odpowiadać w czasie, w którym odpowiadają bez uruchomienia
