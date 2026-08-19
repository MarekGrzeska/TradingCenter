## ADDED Requirements

### Requirement: Jeden proces obsługuje obie powierzchnie albo żadnej

Proces MUST doprowadzić **obie** swoje bazy do rewizji, dla której obraz powstał, zanim
zacznie odpowiadać na cokolwiek. Każdy łańcuch migracji MUST być prowadzony pod własnym
kluczem blokady doradczej, w bazie, której dotyczy. Niepowodzenie któregokolwiek MUST
zatrzymać start całego procesu.

MUST NOT istnieć tryb, w którym proces serwuje jedną powierzchnię, a drugą uznaje za
niedostępną. Półstan, którego nikt nie ćwiczy, jest gorszy od awarii, którą widać: sonda
wdrożenia sięga po proces, więc proces, który odpowiada, jest dowodem, że obie bazy stoją na
właściwej rewizji.

#### Scenario: Obie bazy odpowiadają

- **WHEN** proces startuje, a obie bazy są osiągalne
- **THEN** oba łańcuchy migracji zostają zastosowane, każdy pod własnym kluczem blokady
- **AND** dopiero potem proces zaczyna odpowiadać

#### Scenario: Jedna z baz nie odpowiada

- **WHEN** proces startuje, a jedna z dwóch baz jest nieosiągalna albo jej migracja się nie
  udaje
- **THEN** proces MUST NOT zacząć serwować czegokolwiek
- **AND** komunikat MUST nazywać bazę, której to dotyczy

#### Scenario: Dwa procesy startują naraz

- **WHEN** dwa procesy tego modułu startują jednocześnie
- **THEN** dla każdej bazy dokładnie jeden migruje, a drugi czeka na jego blokadę
- **AND** blokada jednej bazy MUST NOT wstrzymywać migracji drugiej

### Requirement: Dwa schematy, dwa rachunki, dwa katalogi — w jednym procesie

Proces MUST trzymać rozmowę operatora i katalog zespołów w **osobnych** bazach danych. MUST
używać osobnego poświadczenia dostawcy modelu dla każdej z dwóch powierzchni i MUST zapisywać
koszt tury tam, gdzie ta tura zapadła. Katalogi modeli obu powierzchni MUST być
konfigurowane niezależnie.

Rozdział kosztu eksperymentów od kosztu rozmowy jest powodem, dla którego te dwa klucze
powstały, i nie jest powodem, dla którego były dwa procesy. Jeden proces z dwoma klientami
kupuje to samo.

#### Scenario: Koszt tury czatu

- **WHEN** operator prowadzi rozmowę
- **THEN** wywołanie modelu idzie poświadczeniem powierzchni czatu
- **AND** jego koszt MUST być zapisany w bazie rozmowy

#### Scenario: Koszt przebiegu zespołu

- **WHEN** przebiega zespół
- **THEN** wywołania modelu idą poświadczeniem powierzchni zespołów
- **AND** ich koszt MUST być zapisany w bazie zespołów

#### Scenario: Konfiguracja nazywa poświadczenie tylko jednej powierzchni

- **WHEN** proces startuje z poświadczeniem dostawcy modelu tylko dla jednej z powierzchni
- **THEN** MUST odmówić startu, nazywając brakujące ustawienie
- **AND** MUST NOT podstawić poświadczenia drugiej powierzchni

### Requirement: Ścieżka rozstrzyga, która powierzchnia odpowiada

Trasy obu powierzchni MUST być rozłączne. Tam, gdzie obie miały tę samą ścieżkę, powierzchnia
zespołów MUST odpowiadać pod ścieżką rozpoczynającą się od segmentu ją nazywającego, a
powierzchnia rozmowy MUST zostać tam, gdzie była.

Ścieżka literalna, która pasuje także do wzorca z parametrem, MUST być rozstrzygnięta na rzecz
literału niezależnie od kolejności, w jakiej routery zostały złożone — albo kolejność MUST być
utrwalona testem. Dopasowanie segmentu zachodzi przed rzutowaniem go na typ parametru, więc
przestawienie dwóch linii przy składaniu aplikacji jest różnicą między katalogiem a błędem
walidacji.

#### Scenario: Ścieżka kolidująca

- **WHEN** klient pyta o katalog modeli powierzchni zespołów
- **THEN** dostaje katalog tej powierzchni
- **AND** ta sama ścieżka bez segmentu nazywającego zespoły daje katalog powierzchni rozmowy

#### Scenario: Ścieżka literalna wobec wzorca z parametrem

- **WHEN** ścieżka literalna powierzchni zespołów pasuje kształtem do wzorca z parametrem tej
  samej powierzchni
- **THEN** MUST odpowiedzieć trasa literalna
- **AND** MUST istnieć test, który to utrwala

#### Scenario: Trasa niekolidująca

- **WHEN** klient woła jakąkolwiek trasę, która istniała tylko w jednej z powierzchni
- **THEN** jej ścieżka MUST być ta sama co przed połączeniem procesów

### Requirement: Jedno wejście odpowiada bez poświadczenia

Proces MUST udostępniać dokładnie jedno wejście odpowiadające bez poświadczenia, przeznaczone
wyłącznie do sprawdzenia, że proces żyje. MUST NOT ono ujawniać niczego o rozmowach, o
katalogu zespołów ani o operatorach. Każde inne wejście MUST wymagać poświadczenia tam, gdzie
przed procesem stoi warstwa uwierzytelniająca.

Wdrożenie, które umie zapytać wyłącznie warstwę sterującą platformy, dowiaduje się, że
serwowany jest właściwy obraz — nie że proces w środku wstał. Ta różnica raz już przykryła
kontener w pętli restartów zgłoszeniem „Running".

#### Scenario: Sprawdzenie po wdrożeniu

- **WHEN** wdrożenie pyta o to wejście
- **THEN** odpowiedź potwierdza, że proces odpowiada
- **AND** nie niesie żadnej informacji o rozmowach, zespołach ani ich właścicielach

#### Scenario: Każde inne wejście

- **WHEN** żądanie bez poświadczenia trafia na jakiekolwiek inne wejście, a przed procesem
  stoi warstwa uwierzytelniająca
- **THEN** MUST zostać odrzucone

### Requirement: Powierzchnie nie sięgają do siebie nawzajem

Kod powierzchni rozmowy MUST NOT importować kodu powierzchni zespołów, ani odwrotnie.
Narzędzia zespołowe MAY sięgnąć do powierzchni zespołów wyłącznie przez jej własny kontrakt.
Jedynym miejscem, które MAY importować wszystkie trzy, jest złożenie aplikacji.

Reguła „no module imports another module" traci prostotę zero-jedynkową, kiedy dwa moduły
stają się dwoma pakietami jednego procesu. To, co ją zastępuje, MUST być tak samo mechaniczne:
sprawdzane testem czytającym importy, a nie umową między czytającymi kod. Bez testu pierwsza
wygodna zależność powstaje w tygodniu, w którym ktoś się spieszy.

#### Scenario: Zależność między powierzchniami

- **WHEN** kod jednej powierzchni importuje moduł drugiej
- **THEN** test warstw MUST się nie powieść, nazywając plik i import

#### Scenario: Narzędzia sięgające po katalog zespołów

- **WHEN** narzędzia zespołowe czytają albo zapisują katalog zespołów
- **THEN** MUST zrobić to przez kontrakt tej powierzchni
- **AND** MUST NOT ominąć go, sięgając wprost do jej warstwy składowania
