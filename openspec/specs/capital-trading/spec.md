## Purpose

Wszystko, co rusza pieniądze: otwieranie i zamykanie pozycji, zlecenia oczekujące, dołączone
stopy oraz zamiana asynchronicznego potwierdzenia providera w wynik, na którym wywołujący może
polegać.

## Requirements

### Requirement: Otwarte pozycje są czytelne

Moduł MUST publikować otwarte pozycje aktywnego konta, każdą z identyfikatorem, symbolem,
kierunkiem, wielkością, poziomem otwarcia i wynikiem.

#### Scenario: Odczyt pozycji

- **WHEN** konsument odczytuje pozycje
- **THEN** każdy wpis niesie identyfikator, symbol, kierunek, wielkość, poziom otwarcia i wynik

#### Scenario: Brak otwartych pozycji

- **WHEN** aktywne konto nie trzyma żadnej pozycji
- **THEN** moduł zwraca pustą listę, a nie błąd

### Requirement: Zlecenia są składane według typu

Moduł MUST przyjmować zlecenia `MARKET`, `LIMIT` i `STOP`. `LIMIT` i `STOP` MUST wymagać poziomu
docelowego; żądanie bez niego MUST zostać odrzucone, zanim dotrze do providera. Zlecenie MAY nieść
dołączony stop-loss i take-profit.

#### Scenario: Zlecenie rynkowe

- **WHEN** konsument składa zlecenie MARKET na handlowalnym symbolu
- **THEN** moduł zwraca rozliczony wynik raportujący zlecenie jako wykonane, z jego
  identyfikatorem i poziomem wykonania

#### Scenario: Zlecenie oczekujące

- **WHEN** konsument składa zlecenie LIMIT albo STOP z poziomem docelowym
- **THEN** moduł zwraca rozliczony wynik raportujący zlecenie jako oczekujące
- **AND** zlecenie pojawia się wśród zleceń oczekujących

#### Scenario: Zlecenie oczekujące bez poziomu

- **WHEN** konsument składa zlecenie LIMIT albo STOP bez poziomu docelowego
- **THEN** moduł odrzuca żądanie bez kontaktu z providerem i nazywa brakujące pole

#### Scenario: Provider odmawia przyjęcia zlecenia

- **WHEN** provider odrzuca zlecenie
- **THEN** moduł zwraca wynik oznaczony jako odrzucony, niosący podany przez providera powód

### Requirement: Asynchroniczna transakcja jest rozliczana przed zaraportowaniem

Provider potwierdza zlecenie referencją, a rozlicza je osobno. Moduł MUST rozwiązać tę referencję
w wynik, zanim odpowie, i MUST NOT raportować nierozwiązanej referencji jako sukcesu.

#### Scenario: Rozliczenie przychodzi

- **WHEN** provider rozlicza transakcję krótko po jej potwierdzeniu
- **THEN** moduł zwraca rozliczony wynik — wykonane, oczekujące, zamknięte, anulowane albo
  zmienione, zależnie od operacji

#### Scenario: Rozliczenie nie przychodzi na czas

- **WHEN** transakcja pozostaje nierozliczona po wyczerpaniu ograniczonej liczby prób
- **THEN** moduł zwraca wynik oznaczony jako oczekujący na rozliczenie, niosący referencję, żeby
  wywołujący mógł rozwiązać ją później
- **AND** wynik nie jest raportowany jako wykonany

### Requirement: Pozycje są zamykane i zmieniane

Moduł MUST zamykać otwartą pozycję po identyfikatorze oraz ustawiać i usuwać jej stop-loss
i take-profit. Każdy stop MUST być niezależnie ustawialny, usuwalny albo pozostawiany bez zmian —
pominięte pole MUST NOT skasować istniejącego poziomu.

#### Scenario: Zamknięcie pozycji

- **WHEN** konsument zamyka pozycję po identyfikatorze
- **THEN** moduł zwraca rozliczony wynik raportujący pozycję jako zamkniętą

#### Scenario: Ustawienie jednego stopu i pozostawienie drugiego

- **WHEN** konsument ustawia stop-loss i pomija take-profit
- **THEN** stop-loss zostaje ustawiony, a istniejący take-profit pozostaje bez zmian

#### Scenario: Usunięcie stopu

- **WHEN** konsument jawnie kasuje take-profit
- **THEN** take-profit zostaje usunięty z pozycji

#### Scenario: Zmiana niewskazująca żadnego stopu

- **WHEN** konsument wysyła zmianę niewskazującą żadnego ze stopów
- **THEN** moduł odrzuca ją, zamiast wysyłać pustą zmianę

### Requirement: Zlecenia oczekujące są wyliczane i anulowane

Moduł MUST publikować zlecenia oczekujące aktywnego konta i anulować wskazane po identyfikatorze.

#### Scenario: Wylistowanie zleceń oczekujących

- **WHEN** konsument wylistowuje zlecenia oczekujące
- **THEN** każde niesie identyfikator, symbol, kierunek, wielkość, typ zlecenia, poziom docelowy
  i ewentualny termin ważności

#### Scenario: Anulowanie zlecenia oczekującego

- **WHEN** konsument anuluje zlecenie oczekujące po identyfikatorze
- **THEN** moduł zwraca rozliczony wynik raportujący je jako anulowane
- **AND** nie pojawia się ono już wśród zleceń oczekujących

### Requirement: Handel dotyka wyłącznie konta demo

Składanie zleceń, zamykanie pozycji, zmiana i anulowanie MUST być osiągalne tylko wtedy, gdy moduł
jest związany ze środowiskiem demo.

#### Scenario: Próba handlu poza demo

- **WHEN** moduł jest skonfigurowany na środowisko inne niż demo
- **THEN** nie startuje, więc żadna operacja handlowa nie jest osiągalna
