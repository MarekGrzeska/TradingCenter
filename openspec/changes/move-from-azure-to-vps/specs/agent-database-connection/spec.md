## MODIFIED Requirements

### Requirement: Moduł przedstawia się tożsamością, nie hasłem

Moduł MUST uwierzytelniać się wobec bazy hasłem **własnej** roli, która jest właścicielem bazy modułu
od jej utworzenia. Hasło MUST pochodzić z pliku sekretów serwera albo ze środowiska procesu i MUST NOT
występować w repozytorium. Dopóki system działa także w Azure, tryb tożsamości (poświadczenie
pobierane dla tożsamości przy nawiązywaniu połączenia) MUST działać jak dotąd; konfiguracja trybu
tożsamości, której adres bazy niesie własne poświadczenie, MUST być odrzucona przy starcie.

#### Scenario: Moduł na serwerze

- **WHEN** moduł startuje w trybie serwera z hasłem swojej roli w adresie bazy
- **THEN** łączy się jako ta rola

#### Scenario: Poświadczenie w adresie obok tożsamości

- **WHEN** moduł startuje w trybie tożsamości, a adres bazy niesie nazwę użytkownika lub hasło
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje, że poświadczenie z adresu nie byłoby użyte

### Requirement: Praca bez tożsamości nie wychodzi poza maszynę

Bez skonfigurowanej tożsamości moduł MAY łączyć się hasłem niesionym w adresie tylko z hostem na pętli
zwrotnej albo z hostem wymienionym w ustawieniu prywatnych hostów sieci kontenerów tej samej maszyny.
Z każdym innym hostem moduł MUST NOT nawiązać połączenia i MUST odmówić startu. Chroni to przed
lokalnym modułem piszącym do produkcji i przed poświadczeniem ambientowym maszyny.

#### Scenario: Baza w sieci kontenerów serwera

- **WHEN** moduł startuje bez tożsamości, a adres wskazuje host wymieniony jako prywatny
- **THEN** moduł startuje i łączy się z bazą

#### Scenario: Host zdalny bez tożsamości

- **WHEN** moduł startuje bez tożsamości, a adres wskazuje host spoza pętli zwrotnej i spoza listy prywatnych
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje, że praca bez tożsamości jest ograniczona do bazy lokalnej albo prywatnej

#### Scenario: Narzędzie deweloperskie odmawia wcześniej

- **WHEN** skrypt uruchamiający środowisko lokalne czyta konfigurację wskazującą hosta spoza pętli zwrotnej
- **THEN** skrypt odmawia startu przed uruchomieniem czegokolwiek
