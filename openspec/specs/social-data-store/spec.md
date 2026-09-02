# social-data-store Specification

## Purpose
Co moduł przechowuje i pod jakim kluczem — post, bieżący odczyt modelu i rachunek za ten odczyt —
oraz czego z zebranych danych nie da się stracić.

## Requirements

### Requirement: Tożsamością posta jest para źródło–identyfikator

Moduł MUST rozpoznawać post po parze: nazwa źródła i identyfikator nadany przez to źródło. Ten sam
post zebrany po raz drugi MUST NOT pojawić się w archiwum dwa razy ani nadpisać treści już
zapisanej.

#### Scenario: Post wraca w kolejnym przebiegu

- **WHEN** pętla zbioru napotyka post, który jest już w archiwum
- **THEN** archiwum MUST zostać bez zmian
- **AND** liczba postów MUST NOT wzrosnąć

#### Scenario: Kolizja identyfikatorów między źródłami

- **WHEN** dwa różne źródła nadają ten sam identyfikator
- **THEN** oba posty MUST być przechowywane osobno

### Requirement: Treść jest przechowywana jako tekst, nie jako dokument źródła

Moduł MUST przechowywać treść posta w formie czytelnej dla człowieka i dla modelu: bez znaczników
dokumentu, z rozwiniętymi encjami. Adres oryginału MUST być przechowywany, żeby operator mógł
dojść do posta u źródła.

#### Scenario: Post ze znacznikami i encjami

- **WHEN** źródło wydaje treść ze znacznikami dokumentu i zakodowanymi encjami
- **THEN** zapisana treść MUST być czystym tekstem
- **AND** encje MUST być rozwinięte do znaków, które oznaczają

### Requirement: Odczyt modelu stoi obok posta i może go nie być

Moduł MUST przechowywać bieżący odczyt modelu przy poście: tłumaczenie, listę tematów i ocenę
wpływu, każde wraz z nazwą modelu i momentem, w którym powstało. Brak odczytu MUST być stanem
normalnym i MUST być odróżnialny od odczytu pustego.

#### Scenario: Post bez odczytu

- **WHEN** post został zebrany i nie był jeszcze wzbogacony
- **THEN** archiwum MUST przechowywać go w całości
- **AND** brak oceny MUST być odróżnialny od oceny równej zeru

### Requirement: Rachunek za odczyt jest zapisany przy poście

Moduł MUST zapisywać zużycie modelu — operację, model i liczbę tokenów wejściowych oraz
wyjściowych — powiązane z postem, którego dotyczyło. Zapis MUST przetrwać nadpisanie samego
odczytu, bo pieniądz został wydany także za odczyt, który już nie obowiązuje.

#### Scenario: Ponowne wzbogacenie tego samego posta

- **WHEN** post zostaje wzbogacony po raz drugi
- **THEN** przy poście MUST być widoczne oba zużycia, a nie tylko ostatnie

### Requirement: Zebrany post nie znika

Moduł MUST NOT publikować żadnej drogi — trasy kontraktu ani narzędzia — która kasuje zebrany post
albo skraca archiwum według wieku. Kasowanie po siedmiu dniach, które robiła aplikacja źródłowa,
MUST NOT być tu odtworzone.

#### Scenario: Archiwum starzeje się

- **WHEN** post jest w archiwum od dowolnie dawna
- **THEN** MUST być dalej osiągalny przez kontrakt

#### Scenario: Prośba o skasowanie

- **WHEN** klient szuka drogi do skasowania posta
- **THEN** żadna trasa ani narzędzie MUST NOT jej dawać
