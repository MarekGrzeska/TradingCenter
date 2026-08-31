## Purpose

Skąd moduł bierze posty, jak często, co robi z milczącym źródłem i od kiedy w ogóle zaczyna
zbierać — czyli wszystko, co decyduje o tym, czy archiwum jest prawdziwe.

## ADDED Requirements

### Requirement: Zbiór jest czynnością własną modułu, nie skutkiem odczytu

Moduł MUST zbierać posty własną pętlą, uruchamianą przy starcie procesu i pracującą w odstępie
z konfiguracji. Żadna trasa kontraktu ani żadne narzędzie MUST NOT wywoływać pobrania ze źródła
jako skutku ubocznego odczytu.

Powód jest zmierzony na aplikacji, z której ta funkcja pochodzi: tam pobranie listy dla daty
pobierało feed i zapisywało do bazy, więc zawartość archiwum zależała od tego, kto i kiedy patrzył.

#### Scenario: Odczyt nie dokłada danych

- **WHEN** klient pyta kontrakt o posty z dowolnego okna
- **THEN** odpowiedź MUST pochodzić wyłącznie z tego, co zebrano wcześniej
- **AND** liczba postów w archiwum po odczycie MUST być ta sama co przed nim

#### Scenario: Pętla pracuje bez pytania

- **WHEN** proces działa, a nikt nie zadaje żadnego pytania
- **THEN** nowe posty MUST pojawiać się w archiwum w odstępie z konfiguracji

### Requirement: Okno zbioru obejmuje każdą datę kalendarzową, której dotyka

Moduł MUST pytać źródło o każdą datę kalendarzową UTC, której dotyka okno zbioru, i dopiero wynik
MUST filtrować do samego okna. Post opublikowany tuż przed północą MUST NOT wypaść z powodu
sposobu, w jaki źródło adresuje historię datą.

#### Scenario: Okno przecina północ

- **WHEN** okno zbioru zaczyna się przed północą UTC i kończy po niej
- **THEN** moduł MUST odpytać obie daty kalendarzowe
- **AND** post opublikowany o 23:50 MUST trafić do archiwum

### Requirement: Zbiór zaczyna się w dniu wdrożenia

Moduł MUST NOT dociągać historii sprzed pierwszego uruchomienia, choć źródło pozwala pytać o datę
wstecz. Archiwum, które zaczyna się w znanym dniu, MUST być odróżnialne od takiego, które zaczyna
się tam, dokąd akurat sięgnął pierwszy przebieg — moduł MUST podawać moment początku zbioru.

#### Scenario: Pierwsze uruchomienie

- **WHEN** moduł startuje po raz pierwszy na pustej bazie
- **THEN** zbiera wyłącznie bieżące okno
- **AND** MUST NOT sięgać po dni wcześniejsze

#### Scenario: Pytanie o okres sprzed zbioru

- **WHEN** klient pyta o okno wcześniejsze niż początek zbioru
- **THEN** odpowiedź MUST nieść moment, od którego moduł zbiera, a nie samą pustą listę

### Requirement: Milczące źródło jest odróżnione od cichego dnia

Moduł MUST rozróżniać trzy stany źródła: odpowiedź z postami, odpowiedź pusta i brak odpowiedzi.
Brak odpowiedzi ani odpowiedź nieparsowalna MUST NOT kasować, zmieniać ani unieważniać niczego,
co już zebrano, i MUST być widoczne dla klienta jako moment ostatniego udanego zbioru.

#### Scenario: Źródło nie odpowiada

- **WHEN** źródło zwraca błąd albo dokument, którego nie da się sparsować
- **THEN** moduł MUST zostawić archiwum nienaruszone
- **AND** MUST dalej odpowiadać na pytania o to, co zebrał wcześniej
- **AND** moment ostatniego udanego zbioru MUST NOT drgnąć

#### Scenario: Dzień bez postów

- **WHEN** źródło odpowiada poprawnie i nie ma w oknie żadnego posta
- **THEN** moment ostatniego udanego zbioru MUST zostać zaktualizowany

### Requirement: Źródło jest wymienne, a post niesie swoje pochodzenie

Moduł MUST traktować pobieranie jako zdolność źródła, a nie własność modułu: każdy zebrany post
MUST nieść nazwę źródła i autora, a dołożenie drugiego źródła MUST NOT wymagać zmiany w sposobie
przechowywania, w kontrakcie ani w istniejącym źródle.

Nazwa modułu jest szersza niż jego pierwsze źródło celowo — to jest cena zapłacona z góry za to,
żeby drugie źródło było dopisaniem, a nie przebudową.

#### Scenario: Dołożenie źródła

- **WHEN** do modułu dokłada się drugie źródło postów
- **THEN** istniejące źródło, schemat przechowywania i kontrakt MUST zostać bez zmian

#### Scenario: Ten sam identyfikator w dwóch źródłach

- **WHEN** dwa źródła wydają post o tym samym identyfikatorze zewnętrznym
- **THEN** oba MUST trafić do archiwum jako osobne posty
