## ADDED Requirements

### Requirement: Zestaw jest zredukowany do zadań operatora, nie odwzorowuje tras

Zestaw narzędzi MUST być mniejszy niż powierzchnia HTTP modułu `teams` i MUST być pogrupowany
wedle tego, co operator chce zrobić — założyć zespół, poprawić go, uruchomić, przeczytać
wynik — a nie wedle tego, jak `teams` dzieli swoje trasy. Narzędzie MUST NOT wymagać od modelu
złożenia dwóch wywołań tam, gdzie operator wypowiedział jedno życzenie.

Katalog, w którym „załóż zespół" to trzy wywołania w ustalonej kolejności, jest katalogiem, w
którym model pomyli kolejność — a każda pomyłka kosztuje turę i pieniądze. Redukcja jest tą
samą zasadą, którą narzędzia archiwum stosują wobec REST-u `market-data`, przeniesioną na
powierzchnię, której trasy są liczniejsze i bardziej ze sobą splecione.

#### Scenario: Zespół zakładany jednym wywołaniem

- **WHEN** operator opisuje zespół zdaniem, a model woła narzędzie zakładające zespół
- **THEN** powstaje zespół wraz z jego pierwszą rewizją
- **AND** odpowiedź niesie identyfikator zespołu i rewizji, wystarczający do kolejnego kroku

#### Scenario: Poprawka nie wymaga odczytania całej definicji

- **WHEN** model poprawia jedną rolę w istniejącym zespole
- **THEN** MUST móc to zrobić bez przepisywania niezmienionych ról
- **AND** powstaje nowa rewizja, a poprzednia zostaje nietknięta

### Requirement: Narzędzie zapisujące jest oznaczone jako zmieniające stan

Każde narzędzie, które tworzy albo zmienia cokolwiek w module `teams`, MUST być ogłoszone jako
zmieniające stan. Narzędzie wyłącznie czytające MUST być ogłoszone jako czytające.

Oznaczenie nie jest ozdobą: `teams` odmawia harmonogramu nad rewizją z narzędziem, którego nie
potwierdzi jako odczyt, i czyta to z ogłoszenia serwera. Serwer, który nie oznacza swoich
narzędzi, przenosi tę decyzję na zgadywanie po drugiej stronie.

#### Scenario: Katalog rozróżnia odczyt od zapisu

- **WHEN** konsument czyta ogłoszony katalog narzędzi
- **THEN** przy każdym narzędziu widać, czy zmienia stan
- **AND** narzędzia zakładające zespół, zapisujące rewizję, uruchamiające przebieg i
  zakładające harmonogram są oznaczone jako zmieniające stan

### Requirement: Opis narzędzia jest częścią kontraktu

Opis każdego narzędzia MUST nieść to, czego model potrzebuje, żeby wołać je poprawnie bez
zgadywania: co narzędzie robi, czego wymaga, co odpowiada i czego **nie** zrobi. Opis MUST
nazywać granice, które zatrzymają wywołanie — dobową granicę kosztu zespołu i granice handlowe.

Model nie ma innego źródła wiedzy o tym module niż te zdania. Opis, który przemilcza granicę,
zamienia odmowę modułu w niespodziankę, którą model tłumaczy operatorowi zgadywaniem.

#### Scenario: Opis niesie warunki odmowy

- **WHEN** model czyta opis narzędzia uruchamiającego przebieg
- **THEN** opis mówi, że przebieg może zostać odmówiony przez dobową granicę kosztu zespołu
- **AND** mówi, że odmowa nazywa liczbę, która ją spowodowała

### Requirement: Zestaw odpowiada na pytania o to, co się wydarzyło

Zestaw MUST umożliwiać odczytanie śladu przebiegu — kto pracował, co odpowiedział, jakie
narzędzia wołał, ile to kosztowało — w kształcie, z którego model może wyciągnąć wniosek o
poprawce. Odczyt śladu MUST być możliwy bez uruchamiania czegokolwiek.

Poprawianie zespołu jest powodem, dla którego ta zmiana powstaje. Zestaw pozwalający tylko
zakładać i uruchamiać zostawia najdroższą część pracy tam, gdzie jest dzisiaj.

#### Scenario: Model czyta ślad zakończonego przebiegu

- **WHEN** operator pyta, dlaczego przebieg wyszedł tak, jak wyszedł
- **THEN** model MUST móc odczytać ślad tego przebiegu i jego koszt
- **AND** MUST NOT musieć w tym celu uruchamiać przebiegu ponownie

#### Scenario: Przebieg wciąż trwa

- **WHEN** model czyta ślad przebiegu, który jeszcze pracuje
- **THEN** dostaje stan bieżący wraz z informacją, że przebieg nie jest zakończony
- **AND** MUST NOT przedstawić stanu częściowego jako wyniku końcowego

### Requirement: Harmonogram założony przy wyłączonym zegarze mówi o tym wprost

Narzędzie zakładające harmonogram albo wyzwalacz MUST powiedzieć, gdy budzenie się modułu
`teams` jest wyłączone ustawieniem. Zapis MUST się mimo to udać.

Harmonogram zapisany do bazy, o którym operator sądzi, że działa, jest gorszy niż odmowa —
a zegar jest dziś na produkcji wyłączony i pozostanie wyłączony, dopóki ktoś nie zobaczy jego
pierwszego wyzwolenia.

#### Scenario: Zegar wyłączony

- **WHEN** model zakłada harmonogram, a budzenie się modułu `teams` jest wyłączone
- **THEN** harmonogram zostaje zapisany
- **AND** odpowiedź narzędzia mówi, że nic nie wyzwoli, dopóki zegar nie zostanie włączony

### Requirement: Zestaw obejmuje zarządzanie harmonogramem, nie samo jego założenie

Zestaw MUST pozwalać modelowi zatrzymać, wznowić, poprawić i usunąć harmonogram oraz
wyzwalacz — nie tylko go założyć. Poprawka MUST NOT wymagać usunięcia i założenia od nowa:
harmonogram poprawiony zachowuje swoją historię wyzwoleń, a założony od nowa jej nie ma.

Operator, który zakłada harmonogram zdaniem, poprawia go też zdaniem. Zestaw, który umie
tylko zakładać, zostawia katalog rosnący w jedną stronę i odsyła do terminala po każdą
zmianę — a wtedy zdanie w rozmowie jest krótszą drogą do drugiego harmonogramu niż do
poprawienia pierwszego.

Narzędzie usuwające MUST nazywać w swoim opisie to, co usunięcie zabiera nieodwracalnie
(historię wyzwoleń) i czego nie rusza (przebiegi), bo model nie ma innego źródła tej wiedzy.

#### Scenario: Model zatrzymuje harmonogram

- **WHEN** operator prosi, żeby harmonogram przestał na razie chodzić
- **THEN** model ma narzędzie, którym go wyłącza, bez usuwania
- **AND** ten sam harmonogram daje się wznowić

#### Scenario: Poprawka zachowuje wpis

- **WHEN** model zmienia porę harmonogramu
- **THEN** harmonogram zostaje ten sam, z tą samą historią
- **AND** nie powstaje drugi wpis

#### Scenario: Model usuwa wyzwalacz

- **WHEN** operator prosi o usunięcie wyzwalacza
- **THEN** model ma narzędzie, którym go usuwa
- **AND** odpowiedź mówi, że historia wyzwoleń zniknęła razem z nim

#### Scenario: Opis narzędzia usuwającego mówi, co znika

- **WHEN** model czyta opis narzędzia usuwającego harmonogram
- **THEN** opis mówi, że historia wyzwoleń znika bezpowrotnie
- **AND** mówi, że przebiegi i ich koszt zostają

### Requirement: Powierzchnia narzędzi ma zapisany sufit

Cały zestaw — opisy, schematy wejścia i schematy wyjścia razem — jest czytany przez model w
**każdej** turze rozmowy, więc jego rozmiar jest kosztem, nie szczegółem implementacji.
Moduł MUST trzymać zserializowaną postać tego, co ogłasza, poniżej sufitu zapisanego w jego
własnym teście, i MUST wywrócić ten test, gdy sufit zostanie przekroczony.

Moduł MUST NOT publikować w schemacie rzeczy, które nie niosą modelowi informacji ponad to,
co sam schemat już mówi. Ten moduł ogłasza najwięcej narzędzi z trzech, więc płaci za to
rusztowanie najczęściej.

#### Scenario: Zestaw urósł ponad sufit

- **WHEN** zmiana dokłada narzędzie, pole albo akapit opisu, po którym zserializowany
  zestaw przekracza sufit
- **THEN** test powierzchni narzędzi MUST wywrócić się, nazywając zmierzoną wielkość i sufit
- **AND** moduł MUST NOT zostać wdrożony, dopóki jedno z dwóch nie zostanie zmienione świadomie

#### Scenario: Schemat bez rusztowania

- **WHEN** model czyta ogłoszony schemat narzędzia
- **THEN** schemat MUST NOT nieść nazw pól powtórzonych jako ich własne etykiety ani
  wartości domyślnych dla odpowiedzi, której model nie konstruuje
- **AND** MUST nadal nieść każde pole, jego typ i to, czy jest wymagane

### Requirement: To, co powstaje z czatu, należy do operatora, który o to poprosił

Zespół, rewizja, przebieg, harmonogram i wyzwalacz utworzone przez ten zestaw narzędzi MUST
należeć do tożsamości operatora prowadzącego rozmowę. MUST NOT należeć do tożsamości modułu
samego procesu, powierzchni czatu ani żadnej innej tożsamości usługowej.

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

„Mogła być ustalona" znaczy: przed procesem stoi warstwa uwierzytelniająca. Warunek jest
odtąd jeden, nie dwa — drugi mówił o adresie, pod którym wołany jest katalog zespołów, a ten
katalog jest w tym samym procesie i żadnego adresu nie ma.

Zapis „w czyimś imieniu, nie wiadomo czyim" jest wierszem, którego nikt później nie umie
przypisać ani odwołać — a przy harmonogramie jest to wiersz, który zacznie sam wydawać
pieniądze.

Gdy warunek nie zachodzi — nikt nie stoi przed procesem — nie istnieje warstwa, która
mogłaby wystawić jakikolwiek token, więc odmowa nie chroni już niczego: zabiera całą
powierzchnię narzędzi maszynie deweloperskiej. W tym i tylko w tym kształcie narzędzie MUST
wykonać wywołanie **nie przenosząc żadnej tożsamości**, a właściciel MUST być tym, którego
powierzchnia zespołów przypisuje sama każdemu nieuwierzytelnionemu żądaniu. To nie jest
tożsamość zastępcza wybrana przez narzędzie: narzędzie nie wybiera niczego, nie wysyła
poświadczenia i nie zna nazwy, która padnie po drugiej stronie.

Proces MUST powiedzieć przy starcie, w którym z tych dwóch stanów jest — stan, w którym
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

#### Scenario: Maszyna deweloperska, gdzie nikt nie może być uwierzytelniony

- **WHEN** wywołanie dociera bez tożsamości operatora i przed procesem nie stoi warstwa
  uwierzytelniająca
- **THEN** wywołanie MUST zostać wykonane bez przeniesienia jakiejkolwiek tożsamości
- **AND** to, co powstanie, MUST należeć do principala, którego powierzchnia zespołów
  przypisuje nieuwierzytelnionemu żądaniu
- **AND** MUST być widoczne w terminalu na tej samej liście, na której stoi zespół złożony
  ręcznie na tej samej maszynie

#### Scenario: Moduł mówi, w którym stanie wstał

- **WHEN** proces startuje w kształcie, w którym narzędzia działają bez tożsamości operatora
- **THEN** MUST powiedzieć to przy starcie, nazywając warunek, który go do tego stanu
  doprowadził

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
