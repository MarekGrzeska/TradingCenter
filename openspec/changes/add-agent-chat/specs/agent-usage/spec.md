## Purpose

Opisuje pomiar tego, co rozmowa z agentem zużywa i kosztuje: co zostaje zapisane przy
każdym wywołaniu modelu, dlaczego stawka jest przepisywana na wiersz zamiast doliczana
przy odczycie, i co operator może z tego odczytać.

## ADDED Requirements

### Requirement: Każde wywołanie modelu zostawia ślad zużycia

Każde wywołanie modelu MUST zapisać osobny wiersz zużycia niosący: sesję i wiadomość,
której dotyczy, użyty model, liczbę tokenów wejścia i wyjścia oraz moment wywołania. Jeśli
dostawca raportuje tokeny rozbite dokładniej — czytane z pamięci podręcznej promptu,
zużyte na rozumowanie — te liczby MUST być zapisane osobno, bo różnią się stawką i bez
nich rachunek się nie zgadza.

Wywołanie zakończone błędem po tym, jak model zaczął odpowiadać, MUST zapisać zużycie,
które zdążyło powstać. Dostawca liczy tokeny, których operator nie zobaczył; rachunek to
uwzględni, więc pomiar też MUST.

Zużycia, którego dostawca nie podał, MUST NOT być zgadywane. Wiersz MUST wtedy oznaczać
zużycie jako nieznane, odróżnialne od zerowego.

#### Scenario: Zwykła wymiana zdań

- **WHEN** operator wysyła wiadomość i dostaje odpowiedź
- **THEN** powstaje wiersz zużycia wskazujący sesję, wiadomość, model, tokeny wejścia i
  wyjścia oraz moment

#### Scenario: Odpowiedź przerwana błędem

- **WHEN** wywołanie modelu kończy się błędem po wygenerowaniu części odpowiedzi
- **THEN** zużycie, które dostawca zaraportował, zostaje zapisane

#### Scenario: Dostawca nie podał liczb

- **WHEN** odpowiedź kończy się bez raportu zużycia
- **THEN** wiersz oznacza zużycie jako nieznane
- **AND** nie jest liczony jako zero w sumach pokazywanych operatorowi

### Requirement: Koszt jest przypisany do wiersza w chwili zapisu

Stawka za tokeny MUST być konfiguracją, nie stałą w kodzie — zmienia się częściej niż
wychodzą wersje modułu. Koszt wiersza zużycia MUST być policzony i zapisany w chwili
powstania wiersza, wraz ze stawkami, których użyto.

Koszt zapisany MUST NOT być przeliczany przy odczycie. Cennik zmieniany po fakcie
przesunąłby koszt każdej wcześniejszej rozmowy i rozjechał sumy z fakturą — a to właśnie
zgodność z fakturą jest jedynym powodem, dla którego ten pomiar w ogóle istnieje.

#### Scenario: Cennik zmienia się po rozmowie

- **WHEN** stawka modelu zostaje zmieniona w konfiguracji, a operator otwiera zużycie
  sprzed zmiany
- **THEN** koszt tamtych wierszy jest taki jak w chwili ich zapisu
- **AND** wiersze powstałe po zmianie niosą stawkę nową

#### Scenario: Model bez skonfigurowanej stawki

- **WHEN** model jest dostępny, ale nie ma skonfigurowanej stawki
- **THEN** moduł odmawia startu, wskazując model bez stawki jako przyczynę

### Requirement: Zużycie da się odczytać zbiorczo

Moduł MUST publikować zużycie i koszt w postaci zagregowanej: w podziale na model, w
podziale na sesję i w podziale na czas, w zadanym zakresie dat. Agregat MUST nieść tokeny
i koszt osobno — jedno pytanie brzmi „ile mnie to kosztowało", drugie „jak długie są te
rozmowy", i jedno nie zastępuje drugiego.

Sumy MUST być liczone z zapisanych kosztów wierszy, bez sięgania po bieżący cennik.

#### Scenario: Koszt w podziale na model

- **WHEN** konsument pyta o zużycie w zadanym zakresie dat w podziale na model
- **THEN** dostaje dla każdego modelu liczbę tokenów i sumę kosztów z tego zakresu

#### Scenario: Koszt jednej rozmowy

- **WHEN** konsument pyta o zużycie wskazanej sesji
- **THEN** dostaje sumę tokenów i kosztów jej wywołań

#### Scenario: Zakres bez ani jednej rozmowy

- **WHEN** zadany zakres dat nie obejmuje żadnego wywołania
- **THEN** odpowiedź jest pustym zestawieniem, a nie błędem
