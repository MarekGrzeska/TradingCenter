## Purpose

Trzyma połączenie modułu z capital.com: jak się uwierzytelnia, jak długo to uwierzytelnienie
żyje, do którego środowiska wolno mu sięgać i na którym koncie handlowym działają kolejne
wywołania.

## Requirements

### Requirement: Poświadczenia nie opuszczają modułu

Moduł MUST uwierzytelniać się w capital.com w imieniu każdego wywołującego. Poświadczenia
providera i tokeny sesji MUST NOT pojawić się w żadnej odpowiedzi, w żadnej wiadomości
WebSocketa ani w żadnej linii logu.

#### Scenario: Konsument czyta dane, nie mając poświadczenia

- **WHEN** konsument wywołuje dowolny endpoint modułu
- **THEN** nie podaje żadnego poświadczenia capital.com
- **AND** odpowiedź nie niesie klucza API, identyfikatora, hasła, `CST` ani `X-SECURITY-TOKEN`

#### Scenario: Brak poświadczeń przy starcie

- **WHEN** moduł startuje bez skonfigurowanego klucza API, identyfikatora albo hasła
- **THEN** odmawia startu i nazywa brakującą wartość

### Requirement: Wyłącznie środowisko demo

Moduł MUST odmówić pracy z hostem capital.com innym niż host demo. Sprawdzenie MUST nastąpić przy
starcie, przed wysłaniem jakiegokolwiek żądania.

#### Scenario: Skonfigurowany host produkcyjny

- **WHEN** skonfigurowany adres bazowy albo adres strumienia nie jest hostem demo
- **THEN** moduł odmawia startu i stwierdza, że dozwolone jest wyłącznie środowisko demo

#### Scenario: Publikowane możliwości nazywają środowisko

- **WHEN** konsument odczytuje możliwości modułu
- **THEN** odpowiedź nazywa środowisko jako `demo`

### Requirement: Sesja odnawia się niezauważalnie dla wywołującego

Sesja capital.com wygasa po około dziesięciu minutach bezczynności. Moduł MUST odnawiać ją
przezroczyście, a równoległa seria wywołań MUST spowodować najwyżej jedno logowanie.

#### Scenario: Sesja wygasła w trakcie wywołania

- **WHEN** provider odrzuca żądanie z powodu wygasłej sesji
- **THEN** moduł loguje się ponownie i jeden raz ponawia żądanie
- **AND** wywołujący dostaje wynik ponowienia, a nie odmowę

#### Scenario: Kilka wywołań trafia na brak ważnej sesji

- **WHEN** wiele żądań potrzebuje sesji w tym samym momencie
- **THEN** wysyłane jest dokładnie jedno logowanie i wszystkie idą dalej na nim

### Requirement: Konta są wyliczane, jedno jest aktywne

Moduł MUST publikować konta osiągalne skonfigurowanymi poświadczeniami, oznaczać które jest
aktywne i pozwalać je przełączyć. Handel oraz odczyt pozycji MUST działać na koncie aktywnym.

#### Scenario: Wylistowanie kont

- **WHEN** konsument wylistowuje konta
- **THEN** każde konto niesie identyfikator, nazwę, walutę, saldo, środki dostępne oraz wynik
- **AND** dokładnie jedno jest oznaczone jako aktywne

#### Scenario: Przełączenie aktywnego konta

- **WHEN** konsument przełącza się na znany identyfikator konta
- **THEN** moduł zwraca to konto oznaczone jako aktywne
- **AND** kolejne operacje na pozycjach i zleceniach działają na nim

#### Scenario: Przełączenie na nieznane konto

- **WHEN** konsument przełącza się na identyfikator, którego provider nie przyjmuje
- **THEN** moduł odpowiada błędem klienta nazywającym odrzucony identyfikator
- **AND** dotychczas aktywne konto pozostaje aktywne

### Requirement: Moduł publikuje, co potrafi

Moduł MUST publikować maszynowo czytelną deklarację swoich możliwości: providera, środowisko,
przyjmowane typy zleceń oraz to, czy streamuje.

#### Scenario: Odczyt możliwości

- **WHEN** konsument odczytuje możliwości modułu
- **THEN** odpowiedź podaje providera `capital.com`, środowisko `demo`, dostępność streamingu
  oraz przyjmowane typy zleceń
