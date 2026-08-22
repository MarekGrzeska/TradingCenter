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

### Requirement: Moduł korzysta z dwóch powierzchni dostawcy i wie, po co z której

Dostawca udostępnia osobno metadane wydarzeń i rynków oraz osobno ceny i ich szeregi czasowe.
Moduł MUST sięgać po metadane po strukturę wydarzenia i jego rozstrzygnięcie, a po ceny po wycenę
wyniku — i MUST NOT wnioskować struktury z odpowiedzi cenowej ani ceny z metadanych, nawet gdy
któraś z nich chwilowo taką wartość niesie.

Obie powierzchnie są publiczne i nie wymagają poświadczenia. Moduł MUST NOT wymagać do startu
klucza do dostawcy — brak takiej konfiguracji nie jest awarią, bo takiej konfiguracji nie ma.

#### Scenario: Struktura i cena z dwóch źródeł

- **WHEN** moduł odświeża obserwowane wydarzenie
- **THEN** strukturę i stan rozstrzygnięcia bierze z powierzchni metadanych
- **AND** cenę wyniku z powierzchni cenowej

#### Scenario: Start bez klucza do dostawcy

- **WHEN** moduł startuje bez jakiegokolwiek poświadczenia do dostawcy
- **THEN** wstaje i pracuje normalnie

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
