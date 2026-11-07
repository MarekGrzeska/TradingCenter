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

Środowisko, które moduł publikuje w swoich możliwościach, MUST wynikać z hosta, z którym moduł
jest związany, a MUST NOT być wartością wpisaną niezależnie od niego. Konsument pyta o
środowisko po to, żeby wiedzieć, do czego jest podłączony; odpowiedź, która nie może być inna,
nie niesie tej informacji, tylko ją udaje.

#### Scenario: Skonfigurowany host produkcyjny

- **WHEN** skonfigurowany adres bazowy albo adres strumienia nie jest hostem demo
- **THEN** moduł odmawia startu i stwierdza, że dozwolone jest wyłącznie środowisko demo

#### Scenario: Publikowane możliwości nazywają środowisko

- **WHEN** konsument odczytuje możliwości modułu
- **THEN** odpowiedź nazywa środowisko jako `demo`
- **AND** nazwa ta jest wyprowadzona z hosta, z którym moduł jest związany

### Requirement: Sesja odnawia się niezauważalnie dla wywołującego

Sesja capital.com wygasa po około dziesięciu minutach bezczynności. Moduł MUST odnawiać ją
przezroczyście, a równoległa seria wywołań MUST spowodować najwyżej jedno logowanie na sesję.

Odnowiona sesja MUST wrócić na konto, na którym była przed wygaśnięciem. Świeży login u
dostawcy otwiera się na koncie preferowanym (zmierzone 28 października 2026), więc sesja
odnowiona bez przywrócenia konta przeniosłaby kolejne zlecenia na inny rachunek i nic by tego
nie zgłosiło. Jeśli dostawca odmówi przywrócenia konta, wywołanie MUST zakończyć się odmową
nazywającą konto, a MUST NOT zostać wykonane na koncie, na którym otworzył się login.

#### Scenario: Sesja wygasła w trakcie wywołania

- **WHEN** provider odrzuca żądanie z powodu wygasłej sesji
- **THEN** moduł loguje się ponownie i jeden raz ponawia żądanie
- **AND** wywołujący dostaje wynik ponowienia, a nie odmowę

#### Scenario: Kilka wywołań trafia na brak ważnej sesji

- **WHEN** wiele żądań potrzebuje tej samej sesji w tym samym momencie
- **THEN** wysyłane jest dokładnie jedno logowanie i wszystkie idą dalej na nim

#### Scenario: Sesja przełączona na konto inne niż preferowane wygasa

- **WHEN** sesja, której konto zostało przełączone na inne niż preferowane, wygasa, a kolejne
  żądanie wymusza ponowne logowanie
- **THEN** moduł przywraca konto sesji przed ponowieniem żądania
- **AND** żądanie działa na tym samym koncie co przed wygaśnięciem

### Requirement: Konta są wyliczane, jedno jest aktywne

Moduł MUST publikować konta osiągalne skonfigurowanymi poświadczeniami, oznaczać które jest
aktywne i pozwalać je przełączyć. Konto aktywne to konto, na którym działa żądanie, które
nie wskazuje konta.

Żądanie odczytu pozycji, zleceń oczekujących, składania, zamykania i zmiany zleceń oraz
korekty salda MUST móc wskazać konto. Żądanie, które wskazuje konto, MUST działać na tym
koncie niezależnie od tego, które konto jest aktywne i co w tym czasie robią inne żądania.
Przełączenie konta aktywnego MUST NOT zmieniać konta, na którym działa żądanie wskazujące
inne konto. Żądanie wskazujące konto, którego dostawca nie zna, MUST zakończyć się błędem
klienta nazywającym to konto, a MUST NOT zostać wykonane na koncie aktywnym.

Wszystkie sesje, które moduł utrzymuje u dostawcy, MUST dzielić jeden budżet zapytań. Dostawca
liczy go na login, a nie na sesję, więc kilka sesji z osobnymi budżetami przekroczyłoby limit
dostawcy.

Strumień notowań MUST NOT zależeć od konta aktywnego: przełączenie konta aktywnego MUST NOT
zrywać strumienia ani zmieniać tego, co strumień publikuje.

#### Scenario: Wylistowanie kont

- **WHEN** konsument wylistowuje konta
- **THEN** każde konto niesie identyfikator, nazwę, walutę, saldo, środki dostępne oraz wynik
- **AND** dokładnie jedno jest oznaczone jako aktywne

#### Scenario: Przełączenie aktywnego konta

- **WHEN** konsument przełącza się na znany identyfikator konta
- **THEN** moduł zwraca to konto oznaczone jako aktywne
- **AND** kolejne operacje bez wskazanego konta działają na nim

#### Scenario: Przełączenie na nieznane konto

- **WHEN** konsument przełącza się na identyfikator, którego provider nie przyjmuje
- **THEN** moduł odpowiada błędem klienta nazywającym odrzucony identyfikator
- **AND** dotychczas aktywne konto pozostaje aktywne

#### Scenario: Dwa żądania wskazują dwa różne konta jednocześnie

- **WHEN** jedno żądanie składa zlecenie na koncie X, a drugie w tym samym czasie odczytuje
  pozycje konta Y
- **THEN** zlecenie trafia na konto X
- **AND** odczyt konta Y nie zawiera pozycji otwartej na koncie X

#### Scenario: Żądanie wskazuje konto, a konto aktywne się zmienia

- **WHEN** konsument przełącza konto aktywne, gdy inne żądanie wskazuje konto X
- **THEN** żądanie wskazujące konto X działa na koncie X

#### Scenario: Żądanie wskazuje nieznane konto

- **WHEN** żądanie składania zlecenia wskazuje konto, którego dostawca nie zna
- **THEN** moduł odpowiada błędem klienta nazywającym to konto
- **AND** do dostawcy nie trafia żadne zlecenie

#### Scenario: Strumień po przełączeniu konta

- **WHEN** konsument przełącza konto aktywne, gdy strumień notowań jest zestawiony
- **THEN** strumień publikuje dalej bez przerwy
- **AND** konsument strumienia nie dostaje stanu mówiącego o odtwarzaniu połączenia

### Requirement: Moduł publikuje, co potrafi

Moduł MUST publikować maszynowo czytelną deklarację swoich możliwości: providera, środowisko,
przyjmowane typy zleceń oraz to, czy streamuje.

#### Scenario: Odczyt możliwości

- **WHEN** konsument odczytuje możliwości modułu
- **THEN** odpowiedź podaje providera `capital.com`, środowisko `demo`, dostępność streamingu
  oraz przyjmowane typy zleceń

### Requirement: Saldo konta demo daje się skorygować

Moduł MUST pozwalać skorygować saldo konta demo o zadaną kwotę. Kwota ujemna MUST być
przyjmowana tak samo jak dodatnia: ustawienie chudego rachunku jest częścią ustawiania
warunku eksperymentu, a nie pomyłką, przed którą trzeba bronić.

Korekta MUST dotyczyć konta wskazanego w żądaniu, a bez wskazania konta aktywnego. To jest
to samo konto, na którym takie samo żądanie odczytałoby pozycje, żeby „ile mam" i „ile
dosypuję" nigdy nie dotyczyły dwóch różnych rachunków.

Moduł MUST NOT powtarzać we własnym kodzie granic, które stawia dostawca: sufitu salda,
zakresu kwoty ani limitu dobowego. Dostawca je zna i zmienia bez pytania nas, a kopia
przestaje być prawdą w dniu, w którym się rozejdzie. Odmowa dostawcy MUST dotrzeć do
wywołującego jako odmowa nazywająca powód, odróżnialna od awarii dostępu do dostawcy.

Możliwość ta MUST być dostępna wyłącznie w środowisku demo, co wynika z hosta, do którego
moduł jest związany, i nie wymaga osobnego sprawdzenia.

#### Scenario: Dosypanie środków

- **WHEN** konsument koryguje saldo konta demo o kwotę dodatnią
- **THEN** moduł potwierdza wykonanie
- **AND** kolejny odczyt kont pokazuje saldo powiększone o tę kwotę

#### Scenario: Zabranie środków

- **WHEN** konsument koryguje saldo konta demo o kwotę ujemną
- **THEN** moduł wykonuje korektę tak samo jak dodatnią

#### Scenario: Korekta wskazanego konta

- **WHEN** konsument koryguje saldo, wskazując konto inne niż aktywne
- **THEN** zmienia się saldo wskazanego konta
- **AND** saldo konta aktywnego pozostaje bez zmian, a konto aktywne się nie zmienia

#### Scenario: Dostawca odmawia korekty

- **WHEN** dostawca odrzuca korektę, bo kwota wykracza poza przyjmowany zakres, saldo
  przekroczyłoby sufit albo limit dobowy został wyczerpany
- **THEN** moduł odpowiada odmową nazywającą powód podany przez dostawcę
- **AND** odmowa jest odróżnialna od awarii dostępu do dostawcy

