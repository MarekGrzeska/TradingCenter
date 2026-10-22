## Purpose

Skąd pakiet bierze newsy, jak często pyta każde źródło, czym jest źródło i news, co robi z feedem
milczącym, odmawiającym albo nieczytelnym — czyli wszystko, co decyduje, czy archiwum newsów jest
prawdziwe.

## ADDED Requirements

### Requirement: Newsy zbiera pętla pakietu, nie odczyt

Pakiet MUST zbierać newsy własną pętlą, uruchamianą przy starcie procesu, osobną od zbioru postów.
Żadna trasa kontraktu MUST NOT pobierać feedu jako skutku ubocznego odczytu, a pętla MUST pracować
bez niczyjego pytania.

#### Scenario: Odczyt nie dokłada newsów

- **WHEN** klient pyta kontrakt o newsy z dowolnego okna
- **THEN** odpowiedź MUST pochodzić wyłącznie z tego, co zebrano wcześniej
- **AND** liczba newsów w archiwum po odczycie MUST być ta sama co przed nim

#### Scenario: Pętla pracuje bez pytania

- **WHEN** proces działa, a nikt nie zadaje żadnego pytania
- **THEN** każde zadeklarowane źródło MUST być pobierane w swoim odstępie

### Requirement: Źródło jest wpisem, a nie kodem

Źródło newsów MUST być opisane danymi: stałym identyfikatorem, adresem feedu, nazwą wydawcy do
wyświetlenia i odstępem pobierania. Dołożenie, usunięcie albo zmiana adresu źródła RSS MUST NOT
wymagać zmiany schematu przechowywania, kontraktu ani kodu pobierania.

Identyfikator jest tym, pod czym zapisany jest news i stan źródła, więc MUST być stały między
wdrożeniami, a nie nazwą do wyświetlenia.

#### Scenario: Dołożenie feedu

- **WHEN** do listy źródeł dochodzi nowy wpis z adresem feedu RSS
- **THEN** po wdrożeniu pakiet MUST zacząć go pobierać
- **AND** schemat, kontrakt i pozostałe źródła MUST zostać bez zmian

### Requirement: Tożsamością newsa jest para źródło–identyfikator z feedu

Pakiet MUST rozpoznawać news po parze: identyfikator źródła i identyfikator nadany pozycji przez
feed, a przy jego braku adres pozycji. News zobaczony ponownie MUST NOT pojawić się drugi raz ani
nadpisać tego, co zapisano przy pierwszym zobaczeniu. Moment pierwszego zobaczenia jest pomiarem
i nie może się przesuwać.

#### Scenario: News wraca w kolejnym pobraniu

- **WHEN** feed wydaje pozycję, która jest już w archiwum, nawet ze zmienionym tytułem albo czasem
- **THEN** archiwum MUST zostać bez zmian, łącznie z momentem pierwszego zobaczenia

#### Scenario: Ten sam news w dwóch źródłach

- **WHEN** dwa źródła wydają pozycję o tym samym adresie albo tytule
- **THEN** oba MUST być przechowane osobno, każdy ze swoim momentem zobaczenia

### Requirement: Zapisywane jest wszystko, co feed niesie, w języku źródła

Pakiet MUST NOT filtrować newsów przy zbiorze, ani słowami kluczowymi, ani modelem. Zawężanie jest
sprawą odczytu. Tytuł i lead MUST być zapisane w języku, w którym podało je źródło, jako czysty
tekst bez znaczników i z rozwiniętymi encjami. Gdy feed niesie więcej niż lead — pełną treść artykułu
albo dłuższy fragment — pakiet MUST zapisać ją osobno, jako tekst z zachowanymi akapitami, w granicy
rozsądnego rozmiaru. Gdy feed niesie sam lead, treść MUST być pusta, a nie powtórzeniem leadu. Przy newsie
MUST być przechowany adres oryginału i nazwa wydawcy. Gdy feed agreguje cudze artykuły, wydawcą jest
ten, kto artykuł napisał, a nie agregator.

Pakiet MUST NOT pobierać stron artykułów, żeby dopełnić treść. Zapisane jest to, co feed niesie, a
pełny tekst spoza feedu wymagałby decyzji o zbieraniu stron, których regulaminy i ochrony bywają różne.

#### Scenario: News spoza tematu

- **WHEN** feed ogólny wydaje news niezwiązany z Bliskim Wschodem
- **THEN** pakiet MUST go zapisać tak samo jak każdy inny

#### Scenario: Lead ze znacznikami

- **WHEN** feed wydaje lead ze znacznikami HTML i zakodowanymi encjami
- **THEN** zapisany lead MUST być czystym tekstem z rozwiniętymi encjami

#### Scenario: Feed niesie całą treść

- **WHEN** feed wydaje pozycję z treścią w kilku akapitach
- **THEN** zapisana treść MUST zachować podział na akapity
- **AND** lead MUST być krótszy od treści i MUST NOT być jej kopią

#### Scenario: Feed niesie tylko lead

- **WHEN** feed wydaje pozycję z samym krótkim opisem
- **THEN** treść MUST być pusta, a lead MUST być zapisany

### Requirement: Feed, który nie odpowiada, jest odróżniony od feedu bez nowości

Pakiet MUST rozróżniać dla każdego źródła: odpowiedź z pozycjami, odpowiedź „bez zmian” na warunkowe
zapytanie, odmowę, brak odpowiedzi i odpowiedź, której nie da się odczytać. Każda porażka MUST
zostawić archiwum nietknięte i MUST być widoczna w stanie źródła wraz z powodem i momentem.
Porażka jednego źródła MUST NOT opóźniać ani wstrzymywać pobierania pozostałych.

#### Scenario: Feed nie odpowiada

- **WHEN** jedno źródło przekracza czas odpowiedzi albo zwraca błąd
- **THEN** jego newsy w archiwum MUST zostać nietknięte, a moment ostatniego udanego pobrania MUST NOT drgnąć
- **AND** pozostałe źródła MUST zostać pobrane w tym samym przebiegu

#### Scenario: Feed bez zmian

- **WHEN** źródło odpowiada na warunkowe zapytanie, że nic się nie zmieniło
- **THEN** pobranie MUST liczyć się jako udane, a moment ostatniego udanego pobrania MUST zostać zaktualizowany

#### Scenario: Feed zmienił kształt

- **WHEN** źródło zwraca dokument, którego nie da się odczytać jako RSS ani Atom
- **THEN** stan źródła MUST nazwać to nieczytelnym dokumentem, odróżnialnym od braku odpowiedzi

### Requirement: Pakiet pyta uprzejmie i przedstawia się sobą

Pakiet MUST NOT pobierać źródła częściej niż jego odstęp. Gdy źródło podało znaczniki wersji
dokumentu, pakiet MUST pytać warunkowo. MUST przedstawiać się własnym User-Agentem i MUST NOT
podszywać się pod przeglądarkę ani obchodzić ochrony przed automatami. Źródło, które odmawia
uczciwie przedstawionemu wołającemu, jest źródłem odmawiającym, a nie problemem do obejścia.

#### Scenario: Źródło podało znacznik wersji

- **WHEN** poprzednia odpowiedź źródła niosła znacznik wersji dokumentu
- **THEN** następne pobranie MUST przekazać ten znacznik w zapytaniu

#### Scenario: Źródło odmawia

- **WHEN** źródło odpowiada odmową dostępu
- **THEN** pakiet MUST zapisać odmowę w stanie źródła i MUST NOT ponawiać zapytania inną tożsamością

### Requirement: Archiwum nie sięga wstecz dalej, niż feed niesie

Pakiet MUST NOT dociągać historii spoza tego, co feed wydaje przy zwykłym pobraniu. Pozycje zastane
przy pierwszym udanym pobraniu źródła MUST zostać zapisane i MUST być odróżnialne od pozycji, które
pojawiły się w feedzie, kiedy pakiet już go obserwował. Tylko te drugie mówią coś o opóźnieniu.

#### Scenario: Pierwsze pobranie źródła

- **WHEN** źródło zostaje pobrane po raz pierwszy i wydaje trzydzieści pozycji z ostatnich godzin
- **THEN** wszystkie MUST trafić do archiwum oznaczone jako zastane

### Requirement: News żyje przez okres retencji, chyba że operator kazał go zachować

Pakiet MUST sam usuwać newsy, których moment pierwszego zobaczenia jest starszy niż okres retencji.
Okres jest ustawieniem, domyślnie 28 dni. News oznaczony przez operatora do zachowania MUST NOT
zostać usunięty, niezależnie od wieku. Po zdjęciu znacznika taki news znów podlega retencji, a
jeśli jest już starszy niż okres, znika przy najbliższym czyszczeniu.

Usuwanie MUST być czynnością pętli pakietu, a nie trasy. Żadna trasa ani narzędzie MUST NOT kasować
newsa wprost. Newsy to strumień, z którego operator wybiera, co ważne, a nie archiwum tej samej
klasy co posty. Retencja postów zostaje bez zmian.

#### Scenario: News starszy niż retencja

- **WHEN** news bez znacznika zachowania został zobaczony 29 dni temu, a okres wynosi 28 dni
- **THEN** najbliższe czyszczenie MUST go usunąć

#### Scenario: News zachowany

- **WHEN** news ze znacznikiem zachowania został zobaczony 90 dni temu
- **THEN** MUST zostać w archiwum i być osiągalny przez kontrakt

#### Scenario: Znacznik zdjęty ze starego newsa

- **WHEN** operator zdejmuje znacznik z newsa zobaczonego 40 dni temu
- **THEN** najbliższe czyszczenie MUST go usunąć

#### Scenario: Prośba o skasowanie

- **WHEN** klient szuka drogi do skasowania newsa
- **THEN** żadna trasa ani narzędzie MUST NOT jej dawać
