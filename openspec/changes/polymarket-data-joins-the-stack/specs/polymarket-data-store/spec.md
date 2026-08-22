## Purpose

Trzyma próbki ceny obserwowanych wyników i wie o sobie tyle, żeby odróżnić moment, w którym
rynkiem nikt nie handlował, od momentu, którego moduł po prostu nie zebrał.

## ADDED Requirements

### Requirement: Próbkę identyfikuje wynik i moment

Archiwum MUST identyfikować próbkę parą: wynik rynku oraz znacznik czasu, którego dotyczy. Dla
jednej pary MUST istnieć najwyżej jedna próbka; powtórny zapis tej samej pary MUST nadpisać wpis,
a nie dołożyć drugi. Bez tego uzupełnianie przeszłości i bieżące próbkowanie, które spotykają się
w tym samym punkcie, zostawiają w serii dwa punkty o jednym momencie i różnej cenie.

Cena MUST być przechowywana per wynik. Rynek o dwóch wynikach MUST być zapisany jako dwa wiersze,
a nie jako jedna wartość z dorozumianym dopełnieniem — dopełnienie nie zawsze jest prawdziwe, bo
rynki powiązane regułą wzajemnego wykluczania nie muszą sumować się do jedności.

Odczyt zakresu MUST zwracać próbki uporządkowane od najstarszej.

#### Scenario: Ta sama chwila przychodzi dwiema drogami

- **WHEN** uzupełnianie przeszłości przynosi próbkę wyniku dla momentu zapisanego już przez
  bieżące próbkowanie
- **THEN** archiwum trzyma nadal dokładnie jedną próbkę tego momentu
- **AND** odczyt zakresu nie zwraca powtórzonego znacznika czasu

#### Scenario: Rynek o więcej niż dwóch wynikach

- **WHEN** archiwum zapisuje próbkę rynku o pięciu wynikach
- **THEN** powstaje pięć wierszy, po jednym na wynik
- **AND** żaden z nich MUST NOT być wyliczony jako dopełnienie pozostałych

### Requirement: Próbka niesie rodzaj wyceny, z której pochodzi

Cena ostatniej transakcji i wycena wyprowadzona z księgi zleceń odpowiadają na dwa różne pytania:
pierwsza mówi, po ile ktoś ostatnio zawarł transakcję — i na płytkim rynku MAY być sprzed wielu
godzin — druga mówi, ile rynek żąda teraz. Archiwum MAY przechowywać obie, ale MUST zapisywać przy
każdej próbce, którą z nich jest, i MUST NOT mieszać ich w jednej serii bez rozróżnienia.

Wiek ceny MUST być odtwarzalny z zapisu: próbka MUST nieść moment, w którym została pobrana, oraz
— gdy dostawca go podaje — moment, którego wycena faktycznie dotyczy. Zapisanie wyłącznie chwili
odpytania czyni cenę sprzed doby nieodróżnialną od ceny sprzed minuty.

#### Scenario: Odczyt nazywa rodzaj wyceny

- **WHEN** konsument odczytuje historię ceny wyniku
- **THEN** odpowiedź stwierdza, z jakiego rodzaju wyceny pochodzą jej punkty

#### Scenario: Cena starsza niż moment jej pobrania

- **WHEN** dostawca oddaje cenę pochodzącą z transakcji sprzed wielu godzin
- **THEN** archiwum zapisuje oba momenty
- **AND** odczyt pozwala odróżnić cenę świeżą od stojącej

### Requirement: Archiwum wie, dokąd sięga zebrana historia

Brak próbki dlatego, że nikt wtedy nie handlował, i brak próbki dlatego, że moduł wtedy nie
działał, wyglądają w danych identycznie. Archiwum MUST przechowywać dla każdego obserwowanego
wyniku zakres czasu, dla którego dane zostały zebrane albo zweryfikowane, żeby te dwa przypadki
dało się rozróżnić.

Granica „dostawca nie ma nic starszego" MUST być zapisywana na najstarszym punkcie, który odczyt
faktycznie przyniósł, a nie na krawędzi okna, o które zapytano — te dwa punkty dzieli wszystko,
czego dostawca nie miał, a zapisanie drugiego ogłasza jako sprawdzone coś, czego nikt nie sprawdził.
Odczyt, który nie przyniósł ani jednego punktu, MUST NOT zapisywać takiej granicy.

#### Scenario: Pytanie o moment wewnątrz zebranego zakresu

- **WHEN** konsument pyta o cenę wyniku dla momentu wewnątrz zebranego zakresu, dla którego nie
  ma próbki
- **THEN** archiwum stwierdza, że w tym momencie nie było notowania

#### Scenario: Pytanie o moment poza zebranym zakresem

- **WHEN** konsument pyta o cenę wyniku dla momentu spoza jakiegokolwiek zebranego zakresu
- **THEN** archiwum stwierdza, że tego okresu nie zebrało
- **AND** MUST NOT przedstawić tego jako ciszy na rynku

#### Scenario: Odczyt wstecz nie przynosi nic

- **WHEN** uzupełnianie przeszłości kończy się bez ani jednego punktu
- **THEN** archiwum MUST NOT zapisać dla tego wyniku granicy najstarszego osiągalnego momentu
- **AND** zakres pozostaje możliwy do zebrania przy kolejnej próbie

### Requirement: Archiwum nie kasuje się samo

Archiwum MUST NOT usuwać próbek z żadnego powodu poza jawnym żądaniem skasowania: ani z upływu
czasu, ani przy zakończeniu obserwacji, ani przy rozstrzygnięciu rynku, ani przy starcie modułu.
Retencja MUST być decyzją zapisaną w specyfikacji, a nie skutkiem ubocznym zadania sprzątającego.

Archiwum MAY zagęszczać próbki starsze niż skonfigurowany próg, redukując ich takt. Zagęszczenie
MUST być odróżnialne w odczycie od danych o pełnym takcie i MUST NOT zmieniać zakresu, który
archiwum ogłasza jako zebrany.

#### Scenario: Restart modułu

- **WHEN** moduł zostaje zatrzymany i uruchomiony ponownie
- **THEN** żaden obserwowany wynik nie traci ani jednej próbki z tego powodu

#### Scenario: Rynek rozstrzygnięty przed miesiącem

- **WHEN** konsument odczytuje historię rynku rozstrzygniętego przed miesiącem
- **THEN** dostaje ją w całości
- **AND** MUST NOT dostać pustej odpowiedzi z powodu wieku danych

### Requirement: Moduł sam doprowadza bazę do rewizji, dla której powstał

Moduł MUST doprowadzić własną bazę do rewizji schematu, dla której został zbudowany, zanim zacznie
odpowiadać na cokolwiek i zanim zapisze pierwszą próbkę. Wdrożenie MUST NOT wymagać od operatora
osobnego kroku migracji.

Migracja MUST odbywać się pod blokadą wyłączną trzymaną w samej bazie, pod kluczem własnym tego
modułu — dwa jego procesy MUST NOT migrować jednocześnie, a blokada w procesie nie jest blokadą,
bo instancje nie widzą się nawzajem. Proces, który blokady nie dostał, MUST poczekać na jej
zwolnienie, a po upływie skończonego kresu czekania MUST odmówić pracy, mówiąc, że jej nie dostał.
Blokada MUST zostać zwolniona także wtedy, gdy migracja skończyła się błędem.

Migracje MUST być wykonywane tą samą tożsamością, którą moduł łączy się z bazą na co dzień, żeby
tabela utworzona przez migrację była dla niego użyteczna bez osobnego nadania uprawnień.

Moduł MUST odmówić pracy, gdy migracja się nie powiodła oraz gdy baza stoi na rewizji innej niż
oczekiwana przez obraz — nowszej tak samo jak starszej — i MUST nazwać obie rewizje.

#### Scenario: Wdrożenie niosące nową rewizję

- **WHEN** moduł startuje z obrazem nowszym niż rewizja, na której stoi jego baza
- **THEN** brakujące migracje zostają wykonane
- **AND** moduł zaczyna odpowiadać dopiero po nich

#### Scenario: Dwie instancje startują naraz

- **WHEN** dwie instancje modułu startują jednocześnie przeciwko jednej bazie wymagającej migracji
- **THEN** migracje wykonuje dokładnie jedna z nich
- **AND** druga zaczyna odpowiadać po tym, jak pierwsza skończyła

#### Scenario: Próbkowanie nie rusza przed migracją

- **WHEN** moduł startuje z migracją do wykonania
- **THEN** nie zapisuje żadnej próbki, zanim migracja się nie skończy

#### Scenario: Baza wyprzedza obraz

- **WHEN** moduł startuje przeciwko bazie na rewizji nowszej niż jego obraz
- **THEN** odmawia pracy, nazywając obie rewizje

#### Scenario: Migracja kończy się błędem

- **WHEN** migracja przerywa się na błędzie
- **THEN** moduł nie zaczyna odpowiadać
- **AND** blokada zostaje zwolniona, a log niesie rewizję, na której się przerwała
