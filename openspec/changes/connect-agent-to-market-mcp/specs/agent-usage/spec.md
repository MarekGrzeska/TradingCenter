## MODIFIED Requirements

### Requirement: Każde wywołanie modelu zostawia ślad zużycia

Każde wywołanie modelu MUST zapisać osobny wiersz zużycia niosący: sesję i wiadomość,
której dotyczy, użyty model, liczbę tokenów wejścia i wyjścia oraz moment wywołania.
Jeśli dostawca raportuje tokeny rozbite dokładniej — czytane z pamięci podręcznej
promptu, zużyte na rozumowanie — te liczby MUST być zapisane osobno, bo różnią się
stawką i bez nich rachunek się nie zgadza.

Tura, w której model był wołany kilka razy — bo poprosił o narzędzie i mówił dalej z
jego wynikiem — MUST zostawić po jednym wierszu na każde wywołanie, wszystkie wskazujące
tę samą wypowiedź agenta. Jeden wiersz na wypowiedź pokazałby ułamek tego, co dostawca
policzy: wynik narzędzia wchodzi do promptu następnego wywołania i jest liczony jeszcze
raz jako wejście.

Wywołanie zakończone błędem po tym, jak model zaczął odpowiadać, MUST zapisać zużycie,
które zdążyło powstać. Dostawca liczy tokeny, których operator nie zobaczył; rachunek to
uwzględni, więc pomiar też MUST.

Zużycia, którego dostawca nie podał, MUST NOT być zgadywane. Wiersz MUST wtedy oznaczać
zużycie jako nieznane, odróżnialne od zerowego.

#### Scenario: Zwykła wymiana zdań

- **WHEN** operator wysyła wiadomość i dostaje odpowiedź
- **THEN** powstaje wiersz zużycia wskazujący sesję, wiadomość, model, tokeny wejścia i
  wyjścia oraz moment

#### Scenario: Tura z wywołaniem narzędzia

- **WHEN** model prosi o narzędzie, dostaje wynik i dopiero potem odpowiada operatorowi
- **THEN** powstają dwa wiersze zużycia wskazujące tę samą wypowiedź agenta
- **AND** koszt tury jest ich sumą

#### Scenario: Odpowiedź przerwana błędem

- **WHEN** wywołanie modelu kończy się błędem po wygenerowaniu części odpowiedzi
- **THEN** zużycie, które dostawca zaraportował, zostaje zapisane

#### Scenario: Dostawca nie podał liczb

- **WHEN** odpowiedź kończy się bez raportu zużycia
- **THEN** wiersz oznacza zużycie jako nieznane
- **AND** nie jest liczony jako zero w sumach pokazywanych operatorowi
