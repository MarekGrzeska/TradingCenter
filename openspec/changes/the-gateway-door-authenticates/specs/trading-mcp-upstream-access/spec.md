## MODIFIED Requirements

### Requirement: Bez poświadczenia do gatewaya moduł nie wstaje

Moduł MUST odmówić startu, gdy nie może przedstawić się gatewayowi, i MUST NOT wstawać w trybie, w
którym gateway jest wołany bez poświadczenia. Odmowa MUST nazywać, czego zabrakło.

Zabraknąć może dwóch rzeczy, zależnie od tego, gdzie moduł stoi: konfiguracji klucza
współdzielonego tam, gdzie moduł nie ma własnej tożsamości, albo tokenu tej tożsamości tam, gdzie ją
ma. Obie MUST być odmową startu, nie ostrzeżeniem — moduł bez poświadczenia nie jest modułem
ograniczonym do odczytu, jest modułem, którego każde narzędzie odpowiada tym samym błędem, i
którego awarię widać dopiero w środku przebiegu.

#### Scenario: Start bez skonfigurowanego poświadczenia

- **WHEN** moduł startuje bez poświadczenia do gatewaya
- **THEN** odmawia startu z komunikatem nazywającym brakujące ustawienie
- **AND** nie zaczyna nasłuchiwać

#### Scenario: Start bez możliwości uzyskania tokenu

- **WHEN** moduł stoi tam, gdzie ma własną tożsamość, i nie może uzyskać tokenu dla gatewaya
- **THEN** odmawia startu z komunikatem nazywającym, czego nie udało się uzyskać
- **AND** nie zaczyna nasłuchiwać

### Requirement: Poświadczenie do gatewaya jest wymagane niezależnie od adresu

`capital-gateway` przyjmuje wywołania wyłącznie z poświadczeniem dołączonym do każdego żądania —
jego wymóg nie zależy od tego, czy gateway stoi na tej samej maszynie, czy zdalnie. Konfiguracja
tego modułu MUST nieść poświadczenie przy każdym adresie gatewaya, loopback nie wyłącza go.

Postać poświadczenia zależy od miejsca, jego wymóg nie: token tożsamości modułu tam, gdzie moduł ją
ma, klucz współdzielony tam, gdzie nie ma. To wciąż inny kształt niż tryb dostępu do serwera
narzędzi (`teams-tool-access`), gdzie pętla zwrotna bez tożsamości jest poprawnym trybem, bo
uwierzytelnianie stoi tylko przed zdalną instancją. Gateway żąda poświadczenia od każdego
wołającego, więc nie ma tu trybu do wybierania — jest tylko postać do rozpoznania.

#### Scenario: Poświadczenie nieskonfigurowane przy adresie loopback

- **WHEN** moduł startuje z adresem gatewaya w pętli zwrotnej i bez skonfigurowanego
  poświadczenia
- **THEN** MUST odmówić startu z komunikatem nazywającym brakujące ustawienie

#### Scenario: Gateway zdalny, tożsamość własna

- **WHEN** moduł stoi tam, gdzie ma własną tożsamość, i woła gateway pod adresem zdalnym
- **THEN** każde żądanie niesie token tej tożsamości wystawiony dla gatewaya
