## Purpose

Opisuje, czym moduł jest wobec Polymarketu: jedynymi drzwiami w tym systemie, które do niego
sięgają, i granicą, na której kształt dostawcy przestaje być kształtem tego repozytorium.

## ADDED Requirements

### Requirement: Moduł jest jedynymi drzwiami do dostawcy

Żaden inny moduł ani terminal MUST NOT wywoływać API Polymarketu bezpośrednio. Wszystko, co
system o rynkach predykcyjnych wie i czego się o nie pyta, MUST przechodzić przez ten moduł — tak
jak cały ruch do capital.com przechodzi przez `capital-gateway`.

Kształt odpowiedzi dostawcy MUST NOT wyciekać do konsumentów: kontrakt REST i zestaw narzędzi
publikują własne kształty, a zmiana pola po stronie dostawcy MUST być zmianą w tym module,
a nie w terminalu ani w workbenchu.

#### Scenario: Konsument pyta o rynek predykcyjny

- **WHEN** terminal albo model potrzebuje danych z Polymarketu
- **THEN** sięga po nie przez ten moduł
- **AND** MUST NOT wywoływać dostawcy samodzielnie

#### Scenario: Dostawca zmienia nazwę pola

- **WHEN** dostawca zmienia kształt swojej odpowiedzi
- **THEN** zmiana zostaje pochłonięta w tym module
- **AND** kontrakt publikowany konsumentom pozostaje bez zmian

### Requirement: Moduł wie, z której powierzchni dostawcy pochodzi każda liczba

Dostawca udostępnia osobno metadane wydarzeń i rynków oraz osobno wyceny i szeregi czasowe, a te
same wartości bywają publikowane przez obie. Moduł MAY brać wycenę z powierzchni metadanych, gdy
ta podaje ją dla **wszystkich** wyników naraz — to jest tańsze o rząd wielkości niż odpytywanie
każdego wyniku osobno. MUST NOT natomiast przyjmować takiej równoważności na wiarę: MUST zapisać
przy każdej próbce, z której powierzchni pochodzi, i MUST mieć test sprawdzający na próbie, że obie
powierzchnie mówią to samo.

Rozejście się powierzchni MUST objawić się nieudanym testem, a nie serią, która po cichu zmieniła
znaczenie. Moduł MUST NOT wnioskować struktury wydarzenia z odpowiedzi cenowej.

Obie powierzchnie są publiczne i nie wymagają poświadczenia. Moduł MUST NOT wymagać do startu
klucza do dostawcy — brak takiej konfiguracji nie jest awarią, bo takiej konfiguracji nie ma.

Moduł MUST natomiast przedstawiać się dostawcy **własną, stałą identyfikacją klienta**, a nie
wartością domyślną biblioteki HTTP. Brzeg dostawcy wybiera po tym nagłówku i część domyślnych
wartości odrzuca — zmierzone: domyślna wartość jednego z klientów HTTP dostaje `403`, gdy brak
nagłówka przechodzi. Wartość domyślna biblioteki jest wartością, o której decyduje ktoś inny,
i jej zmiana przy aktualizacji zależności byłaby odmową dostępu bez jednej zmiany w tym
module. Identyfikacja MUST być ustawieniem, nie stałą w kodzie.

#### Scenario: Wycena wzięta z powierzchni metadanych

- **WHEN** moduł zbiera ceny obserwowanego wydarzenia z powierzchni, która podaje je dla wszystkich
  wyników w jednej odpowiedzi
- **THEN** zapisane próbki niosą, z której powierzchni pochodzą

#### Scenario: Powierzchnie przestają mówić to samo

- **WHEN** wycena z powierzchni metadanych przestaje odpowiadać wycenie z powierzchni cenowej
- **THEN** MUST to wywrócić testy modułu
- **AND** MUST NOT ujawnić się dopiero jako zmiana znaczenia zebranej serii

#### Scenario: Start bez klucza do dostawcy

- **WHEN** moduł startuje bez jakiegokolwiek poświadczenia do dostawcy
- **THEN** wstaje i pracuje normalnie

#### Scenario: Żądanie idzie z domyślną identyfikacją biblioteki

- **WHEN** moduł wysyła do dostawcy żądanie, którego `User-Agent` pochodzi z biblioteki HTTP,
  a nie z ustawienia modułu
- **THEN** MUST to wywrócić testy modułu, zanim objawi się na produkcji jako odmowa dostępu

### Requirement: Odmowa dostawcy jest raportowana jako odmowa, nie jako brak danych

Dostawca odrzucający wywołanie — z powodu limitu tempa, nieznanego identyfikatora albo awarii po
swojej stronie — zwraca odpowiedzi, które łatwo pomylić z pustym wynikiem. Moduł MUST odróżnić te
przypadki: MUST NOT zapisać odmowy jako zebranego zakresu, MUST NOT przedstawić jej konsumentowi
jako pustej historii i MUST nazwać, po której stronie leży przyczyna.

Nieznany dostawcy identyfikator wydarzenia MUST być odróżniony od awarii dostawcy: pierwsze jest
odpowiedzią na pytanie, drugie jej brakiem.

#### Scenario: Dostawca odmawia w trakcie uzupełniania

- **WHEN** dostawca odrzuca żądanie modułu o szereg czasowy
- **THEN** moduł raportuje porażkę wskazującą dostawcę jako przyczynę
- **AND** zakres, którego dotyczyło żądanie, pozostaje niezebrany

#### Scenario: Wydarzenie nieznane dostawcy

- **WHEN** ktokolwiek wskazuje do obserwacji wydarzenie, którego dostawca nie zna
- **THEN** moduł odmawia, stwierdzając, że dostawca takiego wydarzenia nie ma
- **AND** MUST NOT przedstawić tego jako własnej awarii

### Requirement: Przeszukiwanie publicznej bazy nie miesza się z archiwum

Moduł MUST udostępniać przeszukiwanie i przeglądanie publicznej bazy dostawcy na żywo — po frazie
oraz po jego własnych tagach, z porządkiem i stronicowaniem. Odpowiedź MUST nazywać, że pochodzi
od dostawcy, a nie z archiwum, i MUST NOT być utrwalana jako dane archiwum ani jako obserwacja.

Wynik przeszukania MUST wskazywać, które ze znalezionych wydarzeń są już obserwowane — bez tego
jedyną drogą do sprawdzenia jest osobne wywołanie, a najczęstszą pomyłką objęcie obserwacją czegoś,
co już jest obserwowane.

Niedostępność dostawcy MUST NOT odbierać odczytu archiwum. Przeszukanie MAY wtedy zawieść,
a historia zebranych cen MUST pozostać odczytywalna.

#### Scenario: Przeszukanie po frazie

- **WHEN** ktokolwiek przeszukuje publiczną bazę dostawcy przez ten moduł
- **THEN** dostaje wynik pochodzący od dostawcy, oznaczony jako taki
- **AND** archiwum nie zmienia się o ani jeden wiersz

#### Scenario: Wynik zawiera wydarzenie już obserwowane

- **WHEN** wśród znalezionych wydarzeń jest takie, które moduł już obserwuje
- **THEN** odpowiedź stwierdza to przy tym wydarzeniu

#### Scenario: Dostawca nieosiągalny

- **WHEN** dostawca jest nieosiągalny, a konsument odczytuje historię obserwowanego wyniku
- **THEN** odczyt jest obsłużony z archiwum
- **AND** nieosiągalność dotyczy wyłącznie odpowiedzi wymagających dostawcy na żywo
