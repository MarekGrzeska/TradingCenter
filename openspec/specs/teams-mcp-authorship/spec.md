# teams-mcp-authorship Specification

## Purpose
W czyim imieniu powstaje zespół, przebieg i harmonogram założony rozmową z modelem — i co
moduł robi, kiedy tożsamości operatora nie da się ustalić, zamiast podstawiać własną.
## Requirements
### Requirement: To, co powstaje z czatu, należy do operatora, który o to poprosił

Zespół, rewizja, przebieg, harmonogram i wyzwalacz utworzone przez ten zestaw narzędzi MUST
należeć do tożsamości operatora prowadzącego rozmowę. MUST NOT należeć do tożsamości modułu
`teams-mcp`, modułu `agent` ani żadnej innej tożsamości usługowej.

Katalog zespołów jest filtrowany właścicielem w samym zdaniu SQL, a cudzy zespół jest
nieodróżnialny od nieistniejącego. Zespół zapisany tożsamością usługi byłby więc dla operatora
niewidoczny w terminalu — istniałby, kosztował i nie dałby się otworzyć. To jest różnica
między narzędziem a pułapką.

#### Scenario: Zespół założony z czatu jest widoczny w terminalu

- **WHEN** operator prosi model o założenie zespołu, a potem otwiera zakładkę Teams
- **THEN** zespół jest na jego liście
- **AND** jego rewizja daje się otworzyć i edytować ręcznie

#### Scenario: Przebieg uruchomiony z czatu jest na liście przebiegów operatora

- **WHEN** model uruchamia przebieg na prośbę operatora
- **THEN** przebieg jest widoczny na liście przebiegów tego zespołu u tego operatora
- **AND** jego koszt liczy się do dobowej granicy tego zespołu

#### Scenario: Cudzy zespół pozostaje niewidoczny

- **WHEN** model pyta o zespół należący do innego operatora
- **THEN** odpowiedź jest taka sama jak dla zespołu, który nie istnieje

### Requirement: Brak tożsamości operatora zatrzymuje zapis, nie podstawia zastępczej

Gdy tożsamości operatora nie da się ustalić, a **mogła** być ustalona, narzędzie zmieniające
stan MUST odmówić i MUST nazwać ten brak jako powód. MUST NOT wykonać zapisu tożsamością
usługi, tożsamością domyślną ani żadną inną wybraną w zastępstwie. Odczyt MUST być odmówiony
tak samo — bez tożsamości nie ma katalogu, który miałby być czytany.

„Mogła być ustalona" znaczy: przed modułem stoi warstwa uwierzytelniająca **albo** moduł
`teams` jest wołany pod adresem innym niż pętla zwrotna. Wystarczy jedno z dwojga, i wtedy
obowiązuje odmowa opisana wyżej.

Zapis „w czyimś imieniu, nie wiadomo czyim" jest wierszem, którego nikt później nie umie
przypisać ani odwołać — a przy harmonogramie jest to wiersz, który zacznie sam wydawać
pieniądze.

Gdy **żadne** z dwojga nie zachodzi — nikt nie stoi przed modułem i `teams` jest lokalne —
nie istnieje warstwa, która mogłaby wystawić jakikolwiek token, więc odmowa nie chroni już
niczego: zabiera całą powierzchnię narzędzi maszynie deweloperskiej. W tym i tylko w tym
kształcie narzędzie MUST wykonać wywołanie **nie przenosząc żadnej tożsamości**, a właściciel
MUST być tym, którego `teams` przypisuje samo każdemu nieuwierzytelnionemu żądaniu. To nie
jest tożsamość zastępcza wybrana przez ten moduł: moduł nie wybiera niczego, nie wysyła
poświadczenia i nie zna nazwy, która padnie po drugiej stronie.

Moduł MUST powiedzieć przy starcie, w którym z tych dwóch stanów jest — stan, w którym
narzędzia działają bez tożsamości, MUST NOT być stanem, o którym dowiaduje się z braku
odmowy.

#### Scenario: Żądanie bez tożsamości operatora

- **WHEN** wywołanie narzędzia zapisującego dociera bez ustalonej tożsamości operatora, a
  przed modułem stoi warstwa uwierzytelniająca
- **THEN** MUST zostać odmówione z powodem nazywającym brak tożsamości
- **AND** żaden wiersz MUST NOT powstać

#### Scenario: Odczyt bez tożsamości operatora

- **WHEN** wywołanie narzędzia czytającego dociera bez ustalonej tożsamości operatora, a
  przed modułem stoi warstwa uwierzytelniająca
- **THEN** MUST zostać odmówione tak samo — bez tożsamości nie ma katalogu, który miałby być
  czytany

#### Scenario: Zdalny `teams` bez warstwy uwierzytelniającej przed modułem

- **WHEN** wywołanie dociera bez tożsamości operatora, przed modułem nie stoi warstwa
  uwierzytelniająca, ale `teams` jest wołane pod adresem spoza pętli zwrotnej
- **THEN** MUST zostać odmówione
- **AND** powód MUST nazywać brak tożsamości, a nie adres — brakuje tożsamości, adres tylko
  mówi, że mogła istnieć

#### Scenario: Maszyna deweloperska, gdzie nikt nie może być uwierzytelniony

- **WHEN** wywołanie dociera bez tożsamości operatora, przed modułem nie stoi warstwa
  uwierzytelniająca i `teams` jest wołane w pętli zwrotnej
- **THEN** wywołanie MUST zostać wykonane bez przeniesienia jakiejkolwiek tożsamości
- **AND** to, co powstanie, MUST należeć do principala, którego `teams` przypisuje
  nieuwierzytelnionemu żądaniu
- **AND** MUST być widoczne w terminalu na tej samej liście, na której stoi zespół złożony
  ręcznie na tej samej maszynie

#### Scenario: Moduł mówi, w którym stanie wstał

- **WHEN** moduł startuje w kształcie, w którym narzędzia działają bez tożsamości operatora
- **THEN** MUST powiedzieć to przy starcie, nazywając oba warunki, które go do tego stanu
  doprowadziły

#### Scenario: Tożsamość z argumentu narzędzia pozostaje bez znaczenia w każdym stanie

- **WHEN** wywołanie niesie tożsamość w argumencie narzędzia — niezależnie od tego, czy przed
  modułem stoi warstwa uwierzytelniająca
- **THEN** argument MUST zostać zignorowany albo odrzucony
- **AND** MUST NOT powstać nic należącego do tożsamości z argumentu

### Requirement: Tożsamość operatora jest przenoszona, a nie odgadywana z rozmowy

Tożsamość, którą moduł się posługuje, MUST pochodzić z warstwy uwierzytelniającej wołającego,
przeniesionej przez łańcuch wywołań. MUST NOT pochodzić z treści rozmowy, z argumentu
narzędzia wypełnionego przez model ani z żadnego innego pola, które model potrafi napisać.

Model pisze wszystko, co mu się wyda właściwe, i nie ma powodu, żeby akurat to pole traktować
inaczej. Tożsamość dająca się wpisać jest tożsamością dającą się podszyć — z czatu, jednym
zdaniem operatora, który wie, jak brzmi cudzy identyfikator.

#### Scenario: Model podaje cudzą tożsamość w argumencie

- **WHEN** wywołanie narzędzia niesie w argumencie tożsamość inną niż przeniesiona przez
  łańcuch wywołań
- **THEN** MUST zostać użyta tożsamość przeniesiona, a argument zignorowany albo odrzucony
- **AND** MUST NOT powstać nic należącego do tożsamości z argumentu

### Requirement: Moduł nie rozszerza uprawnień, które operator już ma

Zestaw narzędzi MUST NOT pozwolić operatorowi zrobić niczego, czego nie mógłby zrobić sam w
terminalu. Każda odmowa modułu `teams` — cudzy zespół, wyczerpana granica dobowa, rewizja
nie do uruchomienia — MUST obowiązywać tak samo, gdy o to samo prosi model.

Zdanie działa też w drugą stronę i to jest ta strona, której brakowało: czego operator może
dokonać w terminalu, tego MUST móc dokonać przez model. Zestaw, który zakłada harmonogram, a
zatrzymać go każe iść do terminala, jest polityką dostępu zapisaną tutaj, a nie w `teams` —
tyle że napisaną przez pominięcie.

Nowa droga do modułu nie jest nową polityką dostępu. Gdyby była, każda decyzja zapisana w
`teams` musiałaby być zapisana drugi raz tutaj — i rozjechałaby się przy pierwszej poprawce.

#### Scenario: Granica dobowa zatrzymuje przebieg zamówiony z czatu

- **WHEN** model uruchamia przebieg zespołu, który wyczerpał dobową granicę kosztu
- **THEN** przebieg MUST NOT ruszyć
- **AND** model dostaje odmowę nazywającą granicę i liczbę, która ją wyczerpała

#### Scenario: Odmowa modułu dociera do operatora jego słowami

- **WHEN** `teams` odmawia zapisu, nazywając agenta albo narzędzie, przez które odmowa zapadła
- **THEN** ten sam powód MUST dotrzeć do modelu
- **AND** MUST NOT zostać zastąpiony komunikatem ogólnym

#### Scenario: Czynność dostępna w terminalu jest dostępna z czatu

- **WHEN** operator może wykonać czynność na swoim harmonogramie w terminalu
- **THEN** zestaw narzędzi ma czynność, którą model robi to samo
- **AND** odmowa, jeśli padnie, pochodzi z `teams`, a nie z braku narzędzia

