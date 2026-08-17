## Purpose

Jak moduł rozmawia z `teams` — czym się przedstawia, jak długo czeka, co robi z odmową, i
dlaczego kontrakt tamtego modułu jest sprawdzany zamiast zakładany.

## ADDED Requirements

### Requirement: Tryb połączenia jest wybrany jednoznacznie, nie zgadnięty

Konfiguracja MUST wskazywać dokładnie jeden tryb dostępu do modułu `teams`: tożsamość wobec
adresu zdalnego albo pętla zwrotna bez niej. Konfiguracja nazywająca oba tryby naraz MUST być
odrzucona przy starcie. Adres inny niż pętla zwrotna bez skonfigurowanej tożsamości MUST być
odmową startu.

#### Scenario: Adres zdalny bez tożsamości

- **WHEN** moduł startuje ze wskazanym adresem `teams` spoza pętli zwrotnej i bez tożsamości
- **THEN** MUST odmówić startu z komunikatem nazywającym brakujące ustawienie

#### Scenario: Pętla zwrotna bez tożsamości

- **WHEN** moduł startuje ze wskazanym adresem w pętli zwrotnej i bez tożsamości
- **THEN** startuje i łączy się z lokalnym `teams`

#### Scenario: Oba tryby naraz

- **WHEN** konfiguracja niesie i tożsamość, i adres w pętli zwrotnej
- **THEN** MUST odmówić startu, zamiast wybrać jeden z nich

### Requirement: Kontrakt modułu `teams` jest sprawdzany, nie zakładany

Moduł MUST trzymać u siebie migawkę kontraktu, którego używa, i MUST mieć sposób sprawdzenia
jej wobec kontraktu publikowanego przez `teams`. Rozjazd MUST być wykrywany narzędziem, a nie
awarią przy pierwszym wywołaniu.

Oba istniejące serwery MCP trzymają taką migawkę i to ona łapie zmianę po drugiej stronie,
zanim ta trafi na produkcję. Moduł czytający cudzy kontrakt z pamięci autora jest modułem,
który zepsuje się w dniu, w którym tamten doda pole.

#### Scenario: Kontrakt po stronie `teams` się zmienił

- **WHEN** sprawdzenie migawki jest uruchomione, a `teams` publikuje inny kontrakt
- **THEN** sprawdzenie MUST zakończyć się niepowodzeniem nazywającym różnicę

### Requirement: Wołanie modułu `teams` ma skończony czas

Każde wywołanie MUST mieć górną granicę czasu oczekiwania. Po jej przekroczeniu moduł MUST
oddać wołającemu wynik nazywający niedostępność, a nie czekać dalej.

Zapis MUST NOT być ponawiany po własnej awarii. Powtórzone założenie zespołu jest drugim
zespołem, a powtórzone uruchomienie przebiegu drugim rachunkiem.

#### Scenario: `teams` nie odpowiada w wyznaczonym czasie

- **WHEN** wywołanie przekracza granicę czasu
- **THEN** moduł oddaje wynik nazywający niedostępność
- **AND** MUST NOT ponowić wywołania zapisującego

#### Scenario: Odczyt po przekroczeniu czasu

- **WHEN** wywołanie czytające przekracza granicę czasu
- **THEN** wynik MUST nazywać niedostępność, a nie pustą odpowiedź

### Requirement: Odmowa modułu `teams` jest odróżnialna od jego niedostępności

Odmowa — odpowiedź modułu `teams`, że tak się nie da — MUST docierać do wołającego jako coś
innego niż brak odpowiedzi. Powód odmowy MUST być przeniesiony słowami, którymi `teams` go
napisał.

Model, który dostaje „nie udało się" na jedno i na drugie, spróbuje jeszcze raz tam, gdzie
powtórzenie nic nie zmieni, i podda się tam, gdzie wystarczyło poprawić jedno pole.

#### Scenario: `teams` odrzuca definicję zespołu

- **WHEN** `teams` odmawia zapisu rewizji, nazywając agenta i powód
- **THEN** wołający dostaje odmowę z tym samym powodem
- **AND** odmowa jest odróżnialna od niedostępności modułu
