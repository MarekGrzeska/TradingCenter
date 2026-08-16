## Context

Zobacz `proposal.md` — „Why". Stan, z którego ta zmiana wychodzi, i ograniczenia, które
kształtują rozwiązanie:

- `market-mcp` ma w specyfikacji zapisane, że nigdy nie publikuje narzędzia zapisującego, i
  że nie SHALL istnieć przełącznik, który je dokłada (`market-mcp-tools`). Zapis nie ma tam
  wejścia, które kosztowałoby mniej niż przepisanie tamtego dokumentu.
- `teams` bierze narzędzia z sesji MCP i **nie trzyma u siebie ich nazw, opisów ani kształtu
  parametrów** (`teams-tool-access`). Definicja zespołu wskazuje narzędzie po nazwie.
- `teams` ma dziś dokładnie jeden serwer narzędzi: `ToolServer` z jednym `MARKET_MCP_URL`,
  jedną sesją i jednym `list_tools()`, z którego `plan_tools()` rozwiązuje przypisania raz
  na przebieg.
- `capital-gateway` nie jest publiczny: przyjmuje wyłącznie adresy wyjściowe `market-data`
  (zapora w `infra/app-service.tf`) i wymaga własnego poświadczenia od każdego wołającego
  (`capital-access-control`). Publikuje `GET /capabilities` z polem `environment`.
- Granice kosztu z fazy 1 mają kształt, który ta zmiana powtarza: hak `before_model_call`
  w pętli agenta jako jedyne wejście dla granicy, akumulator w pamięci przebiegu jako suma,
  granica dobowa liczona z bazy od północy UTC przed utworzeniem przebiegu.

## Goals / Non-Goals

**Goals:**

- Zespół składa zlecenia na koncie demo, a każde złożone zlecenie zostaje w śladzie w
  postaci, którą da się zestawić z rekomendacją, z której wyszło.
- Granica szkody jest w kodzie i w rewizji zespołu, nie w prompcie.
- Granica „wyłącznie odczyt" w `market-mcp` zostaje literalnie ta sama.
- Fazy 2 i 3 dają się prowadzić równolegle, z dwoma znanymi punktami styku, a nie z
  odkryciem przy merge'u.

**Non-Goals:**

- **Sprzątanie po przebiegu.** Pozycja otwarta przez zespół przeżywa przebieg — zamyka ją
  następny przebieg albo operator. Automatyczne zamykanie na koniec przebiegu byłoby
  strategią wpisaną w silnik, a strategia jest tym, co ma siedzieć w definicji zespołu.
- **Konto rzeczywiste**, w jakiejkolwiek postaci i za jakimkolwiek przełącznikiem.
- **Handel dla modułu `agent`.** Rozmowa operatora z modelem zostaje rozmową bez skutków na
  rachunku.
- **Ocena wyniku** — czy zespół zarobił. To faza 4; tutaj powstają dane, na których tamta
  może stanąć.

## Decisions

### Zapis dostaje własny serwer MCP, a nie miejsce w istniejącym

`modules/trading-mcp`, port 8060, szósty moduł. Trzy rzeczy dostaje przez to za darmo, a
każdą z nich trzeba by w innym wariancie zbudować osobno: **własną tożsamość Entra** (więc
`allowed_applications` mówi imiennie, kto ma prawo handlować), **własne wdrożenie** (więc
zatrzymanie handlu jest zatrzymaniem jednej aplikacji, a nie zmianą konfiguracji w module,
który robi też coś innego) i **własne miejsce w zaporze gatewaya**.

Rozważone: **przełącznik w `market-mcp`** — odrzucony przez `market-mcp-tools`, które wprost
nazywa przełącznik obietnicą, że kiedyś się go przestawi; cena to przepisanie tamtej
specyfikacji, a wartość — zaoszczędzony `Dockerfile`. **`teams` woła `capital-gateway`
wprost**, z narzędziami zdefiniowanymi w swoim kodzie — odrzucone, bo łamie „moduł nie trzyma
kopii tego, co ogłasza serwer": połowa narzędzi agenta pochodziłaby wtedy z sesji, a połowa z
pliku w `teams`, i tylko jedna z tych połówek zmieniałaby się bez wydania nowej wersji
modułu. Do tego `teams` musiałby wtedy sam znać poświadczenie do gatewaya i mieć wpis w jego
zaporze, czyli dokładnie to, co miało zostać wąskim gardłem.

### Definicja dalej nazywa narzędzie po nazwie; kolizja między serwerami jest odmową

`teams` trzyma **rejestr serwerów**, nie jeden serwer: każdy ma swoją sesję i swoje
`list_tools()`, a `plan_tools()` rozwiązuje przypisania wobec sumy ogłoszeń. Nazwa ogłoszona
przez dwa serwery naraz jest odmową nazywającą oba — przy zapisie rewizji i przy uruchomieniu
przebiegu.

Rozważone: **prefiks serwera w nazwie** (`trading:place_order`) — odrzucony, bo wkłada
tożsamość serwera w nazwę, którą ogłasza serwer, i przy okazji unieważnia każdą rewizję
zapisaną w fazie 1. **Pole `server` przy narzędziu w definicji** — odrzucone z tego samego
powodu po stronie danych (migracja JSONB w każdej zapisanej rewizji) i gorszego po stronie
operatora: musiałby wiedzieć, który serwer publikuje co, żeby złożyć zespół. Odmowa przy
kolizji kosztuje jedno zdanie w komunikacie i zdarza się tylko wtedy, gdy dwa **nasze** moduły
nazwą narzędzie tak samo — czyli w sytuacji, którą i tak chcemy zobaczyć, a nie rozstrzygnąć
po cichu.

Konsekwencja, którą trzeba przyjąć świadomie: nieosiągalny serwer **zapisu** zatrzymuje
przebieg tak samo jak nieosiągalny serwer odczytu, o ile ktokolwiek w definicji ma z niego
narzędzie. To nie jest nowa zasada, tylko ta sama zastosowana do drugiego serwera —
i tym razem ma mocniejsze uzasadnienie: zespół, który nie może złożyć zlecenia, ale o tym nie
wie, produkuje ślad wyglądający jak wynik eksperymentu.

### Środowisko demo jest sprawdzane u gatewaya, nie deklarowane w konfiguracji

`trading-mcp` przy starcie pyta `GET /capabilities` i odmawia startu, gdy odpowiedź nie
nazywa środowiska demo. Ta sama odpowiedź jest sprawdzana ponownie po każdym odzyskaniu
połączenia z gatewayem, zanim moduł znów obsłuży narzędzie zapisujące.

Rozważone: **flaga w konfiguracji modułu** (`ALLOW_LIVE=false`) — odrzucona jako przełącznik
z poprzedniej decyzji, tylko po drugiej stronie. Konfiguracja mówi, w co wierzy operator;
`/capabilities` mówi, do czego moduł jest naprawdę podłączony, a rozjazd między jednym a
drugim jest dokładnie tym zdarzeniem, przed którym to sprawdzenie ma chronić.

### Narzędzie zapisujące nie ponawia; nierozliczone potwierdzenie wraca jako referencja

capital.com potwierdza zlecenie referencją i rozlicza je osobno, a gateway rozwiązuje tę
referencję, zanim odpowie (`capital-trading`). Gdy nie zdąży, oddaje wynik oznaczony jako
oczekujący na rozliczenie. `trading-mcp` przekazuje to modelowi tak, jak jest, i **nigdy nie
powtarza żądania po własnej awarii** — timeout, zerwane połączenie, `5xx`.

Powód jest arytmetyczny, nie ostrożnościowy: provider nie przyjmuje klucza idempotencji, więc
powtórzone zlecenie jest **drugą pozycją**, a nie ponowieniem pierwszej. Ryzyko odwrotne —
zlecenie złożone, którego model nie zobaczył — jest odwracalne przez odczyt pozycji, i tym
właśnie są narzędzia czytające rachunek w tym samym zestawie.

### Granice handlowe siedzą w `teams`, w rewizji zespołu

Trzy liczby przy definicji: maksymalna wielkość jednego zlecenia, liczba zleceń na przebieg
i liczba zleceń dobowa na zespół. Sprawdzane w `teams` przed wywołaniem narzędzia
zapisującego, tym samym kształtem co granice kosztu — akumulator w pamięci przebiegu jako
suma bieżąca, baza jako źródło sumy dobowej liczonej od północy UTC przed utworzeniem
przebiegu.

Dlaczego w `teams`, a nie w `trading-mcp`: granica jest **własnością eksperymentu**. Dwa
warianty zespołu różniące się tym, ile zleceń wolno im złożyć, to dwa różne eksperymenty, i
ta różnica ma być widoczna w rewizji, a nie w zmiennej środowiskowej wspólnej dla obu.
Rozważone: **granice w `trading-mcp`** — odrzucone, bo dałyby jedną liczbę dla wszystkich
zespołów, niewidoczną w śladzie; **granice w prompcie** — nie są granicami.

`trading-mcp` trzyma dokładnie jedną własną granicę i jest nią konto demo. Wynika to z
podziału: moduł chroni rachunek przed tym, czego nie da się cofnąć, `teams` chroni
eksperyment przed sobą samym.

### Każda granica handlowa jest pomijalna, i to jest granica między dwoma rodzajami ochrony

Wszystkie trzy są opcjonalne, każda niezależnie, a pominięta znaczy „bez ograniczenia" —
dokładnie jak `CostLimits` z fazy 1. Moduł nie podstawia wartości domyślnej i nie trzyma
w kodzie sufitu, którego operator nie może podnieść; zespół, któremu operator świadomie
pozwala handlować całym kapitałem, zapisuje się i rusza.

Rozważone i **odrzucone**: **granica wymagana przy narzędziu zapisującym** (odmowa zapisu
rewizji bez niej), co ta zmiana pierwotnie zakładała. Odrzucone, bo miesza dwie ochrony,
które muszą zostać rozdzielone:

- **czego nie wolno nikomu** — konto rzeczywiste. Wymuszone u gatewaya, bez ustawienia,
  które to wyłącza (`trading-mcp-upstream-access`). Tu sztywność jest cała wartością;
- **ile operator sobie pozwala** — trzy granice w rewizji. Tu sztywność jest wadą: to jest
  jego eksperyment, jego konto demonstracyjne i jego decyzja, a moduł odmawiający zapisania
  zespołu bez limitu podejmuje ją za niego.

Skutkiem tego rozdziału jest reguła, którą warto trzymać przy każdej kolejnej granicy
dokładanej do tego modułu: **liczba, której operator nie może zmienić, należy do
`trading-mcp`, nie do `teams`.** Wszystko, co `teams` egzekwuje, pochodzi z rewizji i daje
się z niej usunąć.

### Ślad handlowy dostaje własną tabelę, mimo że wywołanie już jest w `tool_calls`

Wiersz na wywołanie zapisujące: przebieg, agent, symbol, kierunek, wielkość, poziom, skutek,
identyfikator zlecenia od providera. Argumenty i odpowiedź narzędzia dalej lądują w
`tool_calls` — ta tabela nie znika i nie zmienia znaczenia.

Powód jest ten sam, dla którego zużycie ma własne wiersze zamiast siedzieć w JSON-ie kroku:
granica dobowa musi policzyć zlecenia zespołu **przed** uruchomieniem przebiegu, a terminal
musi pokazać listę zleceń przebiegu. Jedno i drugie na `tool_calls` to zapytanie po treści
JSON-a, którego kształt należy do cudzego modułu — `trading-mcp` może przemianować pole i
liczenie granicy przestałoby działać, nie mówiąc o tym ani słowa.

### Zestaw `trading-mcp` nie odpowiada o rynek

Ceny, świece i wskaźniki zostają w `market-mcp`. `trading-mcp` odpowiada o **rachunek** —
pozycje, zlecenia oczekujące, saldo — i wykonuje zlecenia.

Rozważone: **dołożyć bieżącą cenę** do zestawu handlowego, bo gateway ją ma, a agent
składający zlecenie i tak jej potrzebuje. Odrzucone: dwa źródła ceny w jednym przebiegu dają
ślad, w którym nie wiadomo, na czym oparta była decyzja, a różnią się one realnie (archiwum
`market-data` wobec strumienia providera). Agent, który potrzebuje ceny, dostaje narzędzie
`market-mcp` — i to, że musi je dostać jawnie, jest częścią eksperymentu.

### Jeden transport, i jest nim sieć — bez `stdio`

`market-mcp` wystawia dwa transporty, bo `stdio` jest tym, czym operator wpina archiwum do
klienta MCP na własnym biurku. `trading-mcp` wystawia wyłącznie transport sieciowy.

Powód: proces uruchomiony przez klienta nie niesie tożsamości wołającego — wołającym jest ten,
kto go uruchomił. Przy zestawie czytającym to jest wygoda; przy zestawie składającym zlecenia
oznaczałoby, że dowolny klient MCP na maszynie operatora handluje, a `allowed_applications`
przestaje być listą uprawnionych. Rozważone: **`stdio` z tym samym sprawdzeniem konta demo** —
odrzucone, bo sprawdzenie konta chroni przed rachunkiem rzeczywistym, a nie przed tym, kto
wywołał narzędzie; to są dwa różne pytania i tylko na jedno z nich `stdio` odpowiada.

### Kto ma prawo wołać `trading-mcp`, jest wyliczone imiennie

`allowed_applications` modułu zawiera tożsamość `teams` i nic poza nią. `agent` jest z tej
listy nieobecny celowo i to jest wymóg, nie ustawienie: rozmowa operatora z modelem nie
sięga po rzeczy nieodwracalne.

## Risks / Trade-offs

- **Zespół może złożyć zlecenie na podstawie nieporozumienia — i to jest istota fazy** →
  konto demo wymuszone u gatewaya, trzy granice w rewizji sprawdzane przed wywołaniem, ślad
  wiążący każde zlecenie z agentem i przebiegiem. Cofnięcia zlecenia nie ma i nie da się go
  obiecać. Granice są przy tym opcjonalne, więc zespół bez nich zatrzymuje wyłącznie konto
  demo — przyjęte świadomie: to jest ten sam rachunek demonstracyjny, na którym operator
  ma prawo sprawdzić także wariant bez ograniczeń.
- **Zlecenie złożone, którego model nie zobaczył** (rozliczenie nie przyszło na czas, sesja
  padła po żądaniu) → zakaz ponawiania plus narzędzia czytające rachunek w tym samym
  zestawie; ślad zapisuje wywołanie **przed** odpowiedzią, więc zlecenie bez skutku w bazie
  jest widoczne jako takie, a nie nieobecne.
- **Szósta aplikacja na planie B2**, którego pomiar (83% pamięci) zrobiono przy czterech, a
  faza 1 dołożyła piątą → alarm `plan_memory` w `monitoring.tf` jest tym, co to wyłapie;
  odpowiedzią zostaje większy SKU, nigdy drugi worker.
- **Drugi wołający `capital-gateway`** dokłada się do budżetu 10 żądań/s liczonego przez
  capital.com **na konto**, dzielonego już z `market-data` → narzędzia handlowe wołane są w
  tempie decyzji agenta, nie zbierania świec; gateway ma własną bramkę tempa
  (`rategate.py`), a jej działanie na drugim wołającym jest rzeczą do zaobserwowania po
  pierwszym przebiegu, nie do założenia.
- **Fazy 2 i 3 idą równolegle** → punkty styku są dwa i są nazwane: `teams/contract.py`
  (obie tylko dokładają modele) i łańcuch rewizji Alembica w `teams` (ta zmiana bierze
  najbliższą wolną; faza 3 ustawia swoją za nią, gdy ta wyląduje w `feat/teams-module`).
  `runner/loop.py` ma trzeci hak dołożony przez tę zmianę — faza 3 nie rusza pętli agenta,
  tylko to, co uruchamia przebiegi, więc styku tam nie ma.
- **Pozycja przeżywa przebieg** (Non-Goal powyżej) → operator widzi otwarte pozycje w
  terminalu przez `capital-gateway` tak jak dotąd; ryzykiem jest zapomniana pozycja na
  koncie demo, a nie na rachunku.

## Migration Plan

Nie ma danych do migracji: tabela śladu handlowego jest nowa, a granice handlowe są polami
opcjonalnymi w definicji, więc **każda rewizja zapisana w fazie 1 pozostaje ważna** i
uruchamialna — zespół bez narzędzi zapisujących nie ma czego przekraczać.

Kolejność, wymuszona przez zaporę gatewaya, która czyta adresy wyjściowe aplikacji istniejącej:

1. `terraform apply -target` na App Service `trading-mcp` — aplikacja musi stanąć, żeby miała
   adresy wyjściowe;
2. pełny `terraform apply` — reguła w zaporze `capital-gateway`, polityka Key Vault,
   `allowed_applications` modułu, ustawienia `TRADING_MCP_*` w `teams`;
3. wdrożenie `trading-mcp` (`deploy-trading-mcp.yml`), potem `teams`.

Wycofanie jest tą samą dźwignią co przy narzędziach agenta w fazie 1: wyczyścić
`TRADING_MCP_URL` w `teams` i zrestartować. Moduł wraca do tego, czym był — zespoły bez
narzędzi zapisujących chodzą dalej, zespoły z nimi są odmawiane przy uruchomieniu, a wiersze
śladu zostają.
