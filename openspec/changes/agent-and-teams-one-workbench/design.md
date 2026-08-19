## Context

Rachunek po refactorze nazywa kierunek B „największym pojedynczym zyskiem na stole" i od
razu stawia warunek: **fazować**. Ta zmiana jest fazą pierwszą i jedyną, którą da się
uzasadnić bez otwierania pętli tury: dwa routery w jednej aplikacji, osobne schematy.

Rzeczy, które trzeba było rozstrzygnąć, zanim cokolwiek się przeniosło, to nie „jak
przenieść pliki". To pięć decyzji poniżej — każda z alternatywą, która wyglądała rozsądnie
do momentu policzenia jej ceny.

## Goals / Non-Goals

**Goals**

- Jeden proces, jeden obraz, jedno App Service, jeden deploy, jeden port.
- `teams-mcp` przestaje istnieć jako proces; jego narzędzia zostają co do zachowania.
- Bliźniaki znikają konstrukcyjnie — przez to, że nie mają drugiego egzemplarza, nie
  przez wyciągnięcie ich do pakietu.
- Każdy krok zostawia repozytorium w całości działające.

**Non-Goals**

- Scalanie pętli tury (`agent/turn.py` z `teams/runner/loop.py`). Rachunek dopuszcza „na
  końcu albo wcale"; ta zmiana wybiera „nie teraz" i nie zbliża się do tego kodu.
- Scalanie baz. Dwa schematy zostają.
- Scalanie katalogów modeli i kluczy OpenAI. Zostają dwa, z powodu, dla którego powstały.
- `trading-mcp` — to kierunek C, po tej zmianie i mierzony osobno.

## Decisions

### D1 — Dwa pakiety obok siebie, nie jeden pakiet po scaleniu

`workbench/agent/` i `workbench/teams/` zostają nietknięte w środku: te same moduły, te
same importy względne, te same testy. Nowy jest wyłącznie `workbench/` — konfiguracja
i złożenie aplikacji.

Alternatywa: jeden pakiet `workbench/` z podfolderami `conversation/` i `teams/`, importy
przepisane. Odrzucona pomiarem ryzyka, nie gustu — 12 439 linii kodu i 14 493 linie testów
przenoszonych z przepisanymi importami to diff, w którym błąd jest nieodróżnialny od
przeniesienia. `git mv` bez zmiany treści jest diffem, który da się przeczytać w całości.

Cena: nazwa `agent` żyje dalej jako podpakiet czegoś, co nie jest już modułem. Zapisana
tutaj, żeby następny czytelnik nie uznał tego za niedokończone.

### D2 — App Service zostaje pod nazwą `app-tradingcenter-agent`

Nazwa App Service w tym repozytorium **nie jest etykietą, jest tożsamością**. Z niej bierze
się nazwa zarządzanej tożsamości, z tożsamości — rola w PostgreSQL (`DATABASE_USER =
local.agent_app_name`), a identyfikator aplikacji tej tożsamości stoi na dwóch listach
w cudzych modułach: `allowed_applications` i `TOOL_CALLER_APPLICATION_IDS` w `market-data`
oraz `allowed_applications` w `trading-mcp`.

Przemianowanie na `app-tradingcenter-workbench` kosztuje: nowe App Service (zniszczenie
i utworzenie), nową zarządzaną tożsamość, **dwie** nowe role w PostgreSQL z przeniesieniem
własności, trzy wpisy do poprawienia w dwóch cudzych modułach, nowy rekord Entra i nowy
host w terminalu. Kupuje: ładniejszy człon w nazwie DNS.

Zostaje więc `app-tradingcenter-agent`, z komentarzem w `infra/app-service.tf` mówiącym, że
to decyzja. Przemianowanie jest osobną, samodzielną zmianą, do zrobienia kiedykolwiek —
albo nigdy.

Konsekwencja, którą trzeba nazwać: `agent` jest odtąd nazwą **zasobu**, a `workbench`
nazwą **modułu**, i te dwie nazwy nie pokrywają się. To jest gorsze niż jedna nazwa i
lepsze niż migracja tożsamości, którą nikt nie zamawiał.

### D3 — Narzędzia zespołowe wołają `teams` transportem ASGI, nie funkcją store'a

`teams_tools/` (dawne `teams_mcp/`) trzyma **całą** swoją treść: nazwy narzędzi, opisy,
sufity, kształt odmowy, przenoszenie tokenu operatora, patchowanie rewizji. Zmienia się
jedna rzecz — jego klient przestaje otwierać połączenie sieciowe i mówi do routerów
`teams` przez `httpx.ASGITransport` na tej samej aplikacji, w tym samym procesie.

Alternatywa: narzędzia wołają `teams/store.py` wprost. Odrzucona, bo obchodzi routery,
a w routerach siedzi to, czego narzędzia nie powtarzają i nie powinny: filtr właściciela
w zdaniu SQL, walidacja rewizji, granica kosztu dobowego, sprawdzenie katalogu narzędzi
przy zapisie definicji. Wymaganie „moduł nie rozszerza uprawnień, które operator już ma"
jest dziś prawdziwe **dlatego**, że jedyną drogą do `teams` jest jego własny kontrakt.
Wywołanie store'a wprost przeniosłoby politykę dostępu do drugiego miejsca — dokładnie to,
przed czym to wymaganie ostrzega.

Cena: zostaje serializacja JSON i przejście przez stos ASGI, czyli nie jest to „wywołanie
funkcji" w sensie dosłownym rachunku. Znika za to sieć, port, proces, TLS, token
klienta-usługi, timeout i cała klasa awarii „drugi proces nie odpowiada". Hopów sieciowych:
2 → 0.

Skutek dla wymagań: `teams-mcp-upstream-access` znika w całości, ale jego treść nie jest
bezpodstawna — kształty odmowy i rozróżnienie „odmowa wobec niedostępność" zostają
w `workbench-team-tools`, bo ASGI też potrafi zwrócić 4xx.

### D4 — Reguła warstw wewnątrz procesu, w miejsce „no module imports another module"

Reguła nie przestaje obowiązywać — traci prostotę zero-jedynkową, bo dwa byty, które były
modułami, są teraz pakietami jednego. Zamiast niej, mechanicznie sprawdzalne:

1. `workbench/agent/**` MUST NOT importować `workbench.teams` ani `workbench.teams_tools`.
2. `workbench/teams/**` MUST NOT importować `workbench.agent` ani `workbench.teams_tools`.
3. `workbench/teams_tools/**` MAY importować `workbench.teams` **wyłącznie** po to, by
   zbudować transport ASGI na jego aplikacji — i nic poza tym.
4. `workbench/**` (samo złożenie) MAY importować wszystkie trzy. Jest jedynym takim
   miejscem.

To jest test, nie zasada dobrego smaku: `tests/test_layering.py` czyta importy statycznie
i odmawia. Bez niego pierwsza wygodna zależność `agent → teams.store` powstaje w tygodniu,
w którym ktoś się spieszy, i nie ma czego pokazać.

### D5 — Kolizja `/models` i `/usage` rozstrzygnięta na korzyść `agent`

Trzy trasy istnieją w obu modułach: `/health`, `/models`, `/usage`. `/health` jest
identyczne i zostaje jedno. Pozostałe dwie mają różny kształt odpowiedzi (`teams` rozbija
zużycie po **agencie** w zespole, `agent` po sesji i dniu) i muszą się rozejść.

Wybrane: `agent` zostaje na korzeniu, `teams` idzie na `/teams/models` i `/teams/usage`.
Alternatywy: prefiks `/teams` na całości powierzchni `teams` (dałby `/teams/teams/{id}`
i przepisanie każdego wywołania w terminalu) albo prefiks na `agent` (przepisanie każdego
wywołania czatu, czyli większej połowy terminala). Wybrany wariant rusza dwa wywołania.

Pułapka, którą trzeba zapisać: `/teams/models` pasuje do wzorca `/teams/{team_id}`, bo
Starlette dopasowuje segment jako `[^/]+` **zanim** FastAPI spróbuje go rzutować na `int`.
Kolejność rejestracji rozstrzyga, więc literały MUST być zarejestrowane przed routerem
katalogu — i jest na to test, bo to jest dokładnie ten rodzaj poprawności, który przeżywa
do pierwszego przestawienia dwóch linii w `app.py`.

### D6 — Jedno czytanie środowiska, dwa obiekty ustawień

`workbench/config.py` jest jedynym miejscem czytającym środowisko. Buduje z niego dwa
istniejące obiekty — `agent.config.Settings` i `teams.config.Settings` — przekazując
wartości jako argumenty. Obie klasy zachowują swoje walidatory co do znaku: spójność trybu
bazy, spójność trybu serwera narzędzi, katalog modeli, wszystko.

Alternatywa: `env_prefix="AGENT_"` / `env_prefix="TEAMS_"` na obu klasach. Wygląda taniej
o cały plik, ale podwaja **każdą** zmienną, w tym te dwanaście, których podwojenie jest
całym kosztem, który ta zmiana usuwa. Odrzucona z tego jednego powodu.

## Risks / Trade-offs

- **Jeden proces to jeden tryb awarii.** Zegar `teams` żyjący w `lifespan` przewraca się
  razem z czatem, a `agent` przestał być modułem, który wstaje, gdy `teams` nie chce.
  Łagodzenie: migracja obu baz pod osobnymi kluczami blokady w jednym `lifespan` znaczy, że
  proces albo wstaje z obiema bazami na właściwej rewizji, albo nie wstaje — i to drugie
  jest sondą deploy'u, nie cichym półstanem. Świadomie **nie** dodajemy trybu „wstań bez
  `teams`": półstan, którego nikt nie ćwiczy, jest gorszy od awarii, którą widać.
- **Ceny nie ma za darmo po stronie kosztu.** Rachunek mówi to wprost i to zdanie zostaje:
  tokeny na turę **nie spadają**, bo narzędzia zespołowe nadal jadą do modelu w tej samej
  liczbie. Spada latencja, infrastruktura i liczba miejsc do poprawienia.
- **Ziarnistość deployu spada.** Poprawka w czacie i poprawka w zespołach jadą jednym
  obrazem. Przy jednym operatorze to nie kupuje niczego, czego nie kupi taniej — i to
  zdanie warto sfalsyfikować przy pierwszym wdrożeniu, które trzeba będzie cofnąć.
- **Rola w bazie `teams` jest krokiem operatora.** Jedyny. Reguła „migracje nie są robotą
  operatora" dotyczy schematu i zostaje spełniona; własność schematu przez rolę aplikacji
  jest tym jednym, co repozytorium zawsze robiło raz na bazę ręcznie.
- **Test warstw można obejść importem w funkcji.** Statyczny czytnik importów widzi też
  `import` wewnątrz ciała funkcji, bo czyta AST, nie górę pliku — ale nie zobaczy
  `importlib`. Uznane za wystarczające: obejście przez `importlib` nie jest pomyłką,
  a reguła jest tu po to, żeby łapać pomyłki.

## Migration Plan

Kolejność ma znaczenie tylko w dwóch miejscach i oba są w produkcji, nie w repozytorium.

1. **Rola w bazie `teams`.** Zanim nowy obraz wstanie: `app-tradingcenter-agent` jako rola
   w bazie `teams`, z własnością schematu (`scripts/grant-schema-ownership.sql`). Bez tego
   `lifespan` nie zmigruje drugiego łańcucha i proces nie wstanie — głośno, nie cicho.
2. **`terraform apply` przed deployem.** Nowe ustawienia (`AGENT_*`, `TEAMS_*`) muszą
   dotrzeć do App Service, zanim dotrze obraz, który ich wymaga. Ta sama zależność, którą
   `CLAUDE.md` opisuje dla narzędzi agenta, i ta sama konsekwencja pomyłki: apply po
   deployu to przerwa w działaniu, nie kwestia kolejności.

Cofnięcie: poprzedni obraz `agent` plus przywrócone App Service `teams` i `teams-mcp`
z Terraforma. Dane obu baz są nietknięte przez całą operację — żadna migracja nie jest
częścią tej zmiany.

## Open Questions

- Czy `/teams/models` i `/teams/usage` to docelowe nazwy, czy przystanek przed jedną
  powierzchnią `/usage` z parametrem? Rozstrzygalne dopiero po tym, jak terminal pokaże
  oba rachunki na jednym ekranie — dziś pokazuje na dwóch.
- Czy dwa katalogi modeli mają dalej sens w jednym procesie. Zostają, bo ich rozdzielenie
  ma powód (rachunek eksperymentów osobno), ale powód dotyczy **klucza**, nie katalogu.
