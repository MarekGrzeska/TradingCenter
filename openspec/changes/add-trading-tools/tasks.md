## 1. Szkielet `trading-mcp`

- [x] 1.1 Katalog `modules/trading-mcp/` z `pyproject.toml`, `README.md`, `.env.example`, `Dockerfile`
- [x] 1.2 `config.py` — adres i poświadczenie gatewaya, tożsamość, port 8060, wymóg ustalonej tożsamości wołającego
- [x] 1.3 Walidatory `Settings()`: poświadczenie gatewaya wymagane niezależnie od adresu, odmowa startu bez niego
- [x] 1.4 `server.py` i `__main__.py` — wyłącznie transport sieciowy, bez `stdio`
- [x] 1.5 `network_identity.py` — odrzucenie żądania bez ustalonej tożsamości wołającego
- [x] 1.6 `/health` bez sesji MCP i bez poświadczenia, odpowiadające wyłącznie stanem modułu
- [x] 1.7 Testy: odmowa startu przy każdej niespójnej konfiguracji z 1.3; `/health` nie ujawnia rachunku ani narzędzi

  Jedna korekta wobec `design.md`, znaleziona przy czytaniu `capital_gateway/config.py`
  i `app.py`: gateway nie ma trybu dostępu jak `market-data` (tożsamość zdalna kontra
  pętla zwrotna bez niej) — `RequireGatewayKey` sprawdza ten sam nagłówek
  `X-Gateway-Key` od każdego wołającego, loopback też. `trading-mcp-upstream-access`
  poprawiony przed implementacją: jeden wymóg (poświadczenie zawsze), nie dwa tryby.

## 2. Dostęp do `capital-gateway`

- [x] 2.1 `client.py` — poświadczenie na żądanie, górna granica czasu, brak ponawiania żądań zmieniających stan
- [x] 2.2 Sprawdzenie środowiska przez `GET /capabilities` przy starcie; odmowa startu poza demo
- [x] 2.3 Powtórzenie sprawdzenia po odzyskaniu połączenia, przed obsłużeniem narzędzia zapisującego
- [x] 2.4 `errors.py` — rozdzielenie odmowy narzędzia od awarii dostępu; poświadczenie poza logami i odpowiedziami
- [x] 2.5 Snapshot kontraktu gatewaya w `contract/` i `scripts/contract.py check` na wzór `market-mcp`
- [x] 2.6 Testy: odmowa startu przy środowisku innym niż demo, timeout jako awaria dostępu, brak ponowienia po awarii

  `GatewayClient.ensure_demo_environment()` trzyma jeden bit stanu (`_demo_verified`),
  zerowany przy każdej nieudanej rozmowie z gatewayem — 2.3 jest przez to
  mechanizmem gotowym do wpięcia w każde narzędzie zapisujące (grupa 3), nie
  wywołaniem, którego jeszcze nie ma czego strzec. `ToolRefusal` w `errors.py` jest z
  tego samego powodu: kształt gotowy, zanim pierwsze narzędzie go użyje.
  `scripts/contract.py` czyta schemat przez `app.openapi()` w `capital-gateway` (ten
  moduł nie ma dedykowanego modułu `openapi.py` jak `market-data`) — bez bazy, bez
  sesji providera i bez `CAPITAL_*`.

## 3. Zestaw narzędzi

- [x] 3.1 Narzędzia czytające rachunek: pozycje, zlecenia oczekujące, saldo
- [x] 3.2 Narzędzia zapisujące: złożenie zlecenia MARKET/LIMIT/STOP, zamknięcie pozycji, zmiana stopów, anulowanie zlecenia oczekującego
- [x] 3.3 Adnotacje MCP zgodne z tym, co narzędzie robi — zapisujące oznaczone jako zmieniające stan
- [x] 3.4 Odmowy przed dotknięciem rachunku: brak poziomu przy LIMIT/STOP, nieznany albo niehandlowalny symbol
- [x] 3.5 Opis zestawu wskazujący archiwum jako miejsce pytań o rynek; brak narzędzi o cenach i świecach
- [x] 3.6 Testy: lista narzędzi z adnotacjami, każda odmowa z 3.4, brak narzędzia rynkowego w zestawie

  `amend_stops` dostał dwie dodatkowe flagi (`clear_stop_loss`, `clear_take_profit`)
  wobec gołego tri-state z `UpdatePositionRequest` — model dostający jawny parametr
  do wyczyszczenia stopu radzi sobie lepiej niż model, który ma pominąć pole w
  JSON-ie. `_shared.py` niesie oba narzędzia (`_read`, `_write`), nie każde
  osobno — to jest jedyne miejsce tłumaczące `GatewayError` na `ToolRefusal`, więc
  ma być jedno.

  Nieznany symbol nie dostał osobnego sprawdzenia przed wysłaniem — provider
  odpowiada `REJECTED` z powodem, a `_write` zamienia to w odmowę zanim rewizja
  zobaczy cokolwiek jako wykonane; osobna walidacja duplikowałaby to, co gateway już
  robi, i mogłaby się z nim rozjechać.

## 4. Wynik zlecenia

- [x] 4.1 Mapowanie wyniku gatewaya na wynik narzędzia — rozliczony albo jawnie nierozliczony z referencją
- [x] 4.2 Odrzucenie providera jako wynik odrzucony z jego powodem, nie jako awaria
- [x] 4.3 Awaria dostępu jako wynik nazywający nieznany skutek
- [x] 4.4 Testy: nierozliczone potwierdzenie nie jest raportowane jako wykonanie; awaria nie jest raportowana jako odrzucenie

  Jeden podział doszedł wobec design.md, warty odnotowania: `5xx` na zapisie trafia
  do awarii dostępu, nie do odmowy — inaczej niż `4xx`, `5xx` może zdarzyć się już
  po tym, jak provider zobaczył żądanie, więc tylko `4xx` (walidacja gatewaya
  zatrzymana przed providerem) jest bezpieczną odmową „nic się nie zmieniło".

## 5. Dwa serwery narzędzi w `teams`

- [x] 5.1 `config.py` — `TRADING_MCP_URL` i `TRADING_MCP_SCOPE` obok istniejących, każdy ze swoim sprawdzeniem trybu
- [x] 5.2 Rejestr serwerów w miejsce jednego `ToolServer`; sesja i `list_tools()` per serwer
- [x] 5.3 `plan_tools()` rozwiązujący przypisania wobec sumy ogłoszeń, z zapamiętaniem, z którego serwera pochodzi narzędzie
- [x] 5.4 Odmowa przy kolizji nazw — przy zapisie rewizji i przy uruchomieniu przebiegu, z nazwami obu serwerów
- [x] 5.5 Pytany jest tylko ten serwer, z którego ktokolwiek w definicji ma narzędzie
- [x] 5.6 `GET /tools` ogłaszające narzędzia obu serwerów wraz z oznaczeniem zapisujących
- [x] 5.7 Testy: niespójna konfiguracja drugiego serwera odmawia startu; nieosiągalny serwer zapisu nie zatrzymuje zespołu bez zapisu; kolizja nazw odmawia w obu miejscach

  Jedna korekta wobec litery 5.5, znaleziona przy pisaniu `plan_tools()`: „pytany jest
  tylko serwer, z którego ktokolwiek ma narzędzie" nie da się pogodzić z niezawodnym
  wykrywaniem kolizji (5.4) bez wiedzy, którego serwera nazwa dotyczy — a tej wiedzy
  nie ma, dopóki się nie zapyta. Rozwiązanie: każdy *skonfigurowany* serwer jest pytany
  współbieżnie (`asyncio.gather`), a jego awaria jest składana na bok, dopóki jakaś
  przypisana nazwa nie zostanie bez wyjaśnienia — dokładnie wtedy i tylko wtedy
  nieosiągalność tego serwera zatrzymuje przebieg. Zespół, którego żadna przypisana
  nazwa nie brakuje po stronie serwerów, które odpowiedziały, rusza — nieosiągalny
  serwer *jest* pytany, ale jego porażka nigdy nie dociera do wywołującego, gdy nikt
  jej nie potrzebuje. `teams-tool-access`'s scenariusz „nieosiągalny serwer nie jest w
  ogóle pytany" poprawiony na „jego nieosiągalność nie wpływa na wynik" — literalne
  niepytanie złamałoby 5.4 w drugą stronę: kolizja na serwerze, który nigdy nie został
  zapytany, przeszłaby bez odmowy.

  `ToolServer.__init__` dostał parametr `prefix` (domyślnie `"market_mcp"`) zamiast
  nowej sygnatury biorącej `url`/`scope`/`timeout` wprost — każde dotychczasowe
  wywołanie `ToolServer(settings)` w kodzie i w testach zostaje dokładnie tym, czym
  było, a drugi serwer to `ToolServer(settings, prefix="trading_mcp")`. `ToolPlan`
  niesie teraz `server_by_name` obok `per_agent` i własną metodę `call()` —
  `runner/engine.py` przestał przekazywać `tool_server` do węzła agenta osobno, bo
  `plan.call` już wie, gdzie wysłać każde wywołanie.

  `announced_tool_names`/`announced_tools` (pojedynczy serwer) zastąpione przez
  `announced_snapshot` (zapis — nazwa → serwery, plus lista nieosiągalnych) i
  `announced_tools_by_server` (`GET /tools` — pełne deskryptory, 503 gdy którykolwiek
  skonfigurowany serwer nie odpowiedział). `ToolDescriptor` dostał pole `read_only`
  czytane z `readOnlyHint` narzędzia; `teams/contract.py`'s `ToolOut` to samo pole
  publikuje na drucie — `contract.teams.generated.ts` przegenerowany
  (`pnpm contract:generate`), `contract:check` i `pnpm typecheck` przechodzą. Terminal
  poza tym nietknięty — wpięcie `read_only` w wybierak narzędzi zostaje zadaniem 8.3.

## 6. Granice handlowe

- [x] 6.1 Granice handlowe w `TeamDefinition` — maksymalna wielkość zlecenia, liczba zleceń na przebieg, liczba dobowa; każda pomijalna, pominięta znaczy „bez ograniczenia"
- [x] 6.2 Brak granicy nigdy nie jest odmową zapisu; moduł nie podstawia wartości domyślnej ani nie trzyma sufitu w kodzie
- [x] 6.3 Hak w pętli agenta sprawdzający granice przed wywołaniem narzędzia zapisującego
- [x] 6.4 Wyczerpana liczba zleceń zatrzymuje przebieg statusem odróżnialnym od kosztu
- [x] 6.5 Zlecenie ponad maksymalną wielkość jako odmowa wywołania, bez zatrzymania przebiegu
- [x] 6.6 Sprawdzenie granicy dobowej przed utworzeniem przebiegu, liczone od północy UTC
- [x] 6.7 Testy: rewizja sprzed tej zmiany pozostaje uruchamialna; zespół dobijający do granicy zostawia ślad; granica dobowa odmawia przed wywołaniem kogokolwiek

  **Odwrócona decyzja, na polecenie operatora — i to jest najważniejsza rzecz w tej
  grupie.** Pierwotne 6.2 brzmiało „odmowa zapisu rewizji z narzędziem zapisującym i bez
  granic". Zostało odwrócone przed napisaniem linijki kodu: granice mają być mechanizmem,
  którym operator dysponuje, a nie zgodą, której moduł mu udziela. Zespół, któremu
  operator świadomie pozwala handlować całym kapitałem, zapisuje się i rusza. Poprawione:
  `teams-catalogue` (wymóg odwrócony w „Granice handlowe są wyborem operatora, nie
  warunkiem zapisu"), `teams-trading` (nowy wymóg „Każda granica handlowa daje się
  wyłączyć, a moduł żadnej nie narzuca"), `proposal.md` i `design.md`.

  Zasada, którą warto trzymać przy każdej następnej granicy w tym module: **liczba,
  której operator nie może zmienić, należy do `trading-mcp`, nie do `teams`.** Tam
  siedzi konto demo wymuszone u gatewaya, którego nie wyłącza żadne ustawienie; tutaj
  wszystko pochodzi z rewizji i daje się z niej usunąć.

  Wykrywanie, że wywołanie jest zleceniem, opiera się na `read_only is False` z
  ogłoszenia serwera (grupa 5) — nie na nazwie narzędzia i nie na tym, z którego serwera
  pochodzi. Narzędzie bez adnotacji jest „nieznane" i nie jest awansowane na zapisujące:
  oba nasze serwery adnotują wszystko, co publikują, a zgadywanie za trzeci byłoby
  trzymaniem opinii o cudzym kontrakcie.

  **Części grupy 7 zrobione tutaj, bo 6.6 bez nich nie działa** — dobowa liczba zleceń
  potrzebuje czegoś, co je liczy. Zrobione: 7.1 (rewizja `0004`, tabela `trades`), 7.2
  (wiersz przed wysłaniem wywołania, uzupełniany po odpowiedzi) i 7.3 (skutek nieznany
  zapisany jako `unknown`). Dla grupy 7 zostają 7.4 (`contract.py` — modele wiersza na
  drucie), 7.5 (trasa odczytu) i 7.6 (jej testy). `TradingLimits` wylądowało w
  `contract.py` już teraz, bo definicja jedzie na drucie — `contract.teams.generated.ts`
  przegenerowany.

## 7. Ślad handlowy

- [x] 7.1 Rewizja Alembica w `teams` z tabelą śladu handlowego (numer rewizji brany przy implementacji — patrz nota o fazie 3 na końcu) — `0004`, zrobione z grupą 6
- [x] 7.2 Zapis wiersza przed wysłaniem wywołania; uzupełnienie o skutek po odpowiedzi — zrobione z grupą 6
- [x] 7.3 Skutek nieznany zapisany jako nieznany, nie jako nieudany — zrobione z grupą 6
- [x] 7.4 `contract.py` — kształt wiersza śladu handlowego i granic handlowych (wyłącznie dodanie modeli)
- [x] 7.5 Trasa odczytu zleceń przebiegu, z filtrem właściciela jak reszta modułu
- [x] 7.6 Testy `-m db`: migracja od zera dochodzi do rewizji czołowej; wiersz przeżywa przerwanie przebiegu

  `TradingLimits` doszło już z grupą 6 (definicja jedzie na drucie, więc nie dało się
  jej odłożyć), tu doszedł `TradeOut` — kolumny zamiast JSON-a, `size` i `level` jako
  łańcuchy jak każda inna liczba na tym drucie, którą się porównuje, a nie przelicza.
  `status` (odczyt tego modułu) obok `result_status` (słowo providera) zostały osobno:
  wiersz może nieść pierwsze bez drugiego, gdy odpowiedź nigdy nie przyszła.

  `GET /runs/{id}/trades` obok `/tool-calls`, nie zamiast — tamta trasa odpowiada „o co
  agenci prosili", ta „co się stało z rachunkiem", a operator po przebiegu pyta o
  drugie. Filtr właściciela ten sam co wszędzie: cudzy przebieg to 404.

  Pierwsza połowa 7.6 była już spełniona, zanim ta grupa się zaczęła:
  `test_migrate.py::test_an_empty_database_is_brought_to_head` porównuje `applied_heads`
  z `expected_heads()`, więc rewizja `0004` weszła do niego sama. Zamiast duplikatu
  doszły dwa testy, których tamten nie pokrywa: zamknięty zbiór statusów w schemacie
  (`CheckViolationError` na szóstej pisowni) i przerwanie przebiegu po złożonym
  zleceniu — wiersz zostaje, ze statusem `settled`, bo przerwanie przyszło później.

## 8. Terminal

- [x] 8.1 `pnpm contract:generate` po zmianach w `teams/contract.py` — zrobione przy
  scaleniu fazy 2 do `feat/teams-platform`; plik niesie teraz oba wiersze naraz, handlowy
  i harmonogramowy
- [x] 8.2 Granice handlowe w panelu zespołu; ~~odmowa zapisu pokazana przy agencie~~ —
  drugiej połowy nie ma, bo po odwróceniu decyzji z grupy 6 taka odmowa nie istnieje
- [x] 8.3 Narzędzia zapisujące odróżnione od czytających w wybieraku narzędzi
- [x] 8.4 Zlecenia przebiegu przy agencie, który je złożył — symbol, kierunek, wielkość, skutek
- [x] 8.5 Zlecenie o nieznanym skutku pokazane jako nieznane
- [x] 8.6 Granica zleceń jako przyczyna zatrzymania, odróżniona od kosztu
- [x] 8.7 `pnpm lint`, `typecheck`, `test`, `contract:check` przechodzą — 853 zielone
  (było 840), `contract:check` bez zmian w wygenerowanym pliku: grupa 5 i 7 wygenerowały
  go już wcześniej

  **Ostatni ślad odwróconej decyzji z grupy 6 był w `terminal-teams`, nie w kodzie.** Delta
  tej zmiany dalej wymagała „odmowy zapisu z powodu brakującej granicy pokazanej przy
  agencie" — wymogu, którego moduł od grupy 6 nie stawia. Poprawione tutaj, z zapisanym
  powodem: pusta granica jest wyborem operatora, terminal niczego nie wymusza i niczego z
  tego powodu nie ostrzega. Test `saves an agent given a write tool and no limit at all` jest
  tego dowodem od tej strony.

  Granice handlowe dostały **panel zespołu** (`TeamPanel.tsx`) w prawej kolumnie edytora —
  ten sam pas, w którym siedzi panel agenta, pokazywany, gdy żaden agent nie jest wybrany, z
  nowym przyciskiem `Team` jako drogą powrotną. Powód: to jedyne miejsce w tym widoku, które
  należy do zespołu, a nie do agenta. Granice kosztu (`limits`) zostały tam świadomie **nie**
  dołożone — jadą na drucie od fazy 1 i nigdy nie miały wybieraka; dołożenie ich tutaj byłoby
  rozszerzeniem tej zmiany o cudzy brak. Warte odnotowania jako dziura, nie jako zadanie tej
  grupy.

  8.6 opiera się na zdaniu modułu, bo nic innego nie jedzie na drucie: `stopped_reason` to
  proza, a obie granice piszą własną (`runner/trading.py`, `runner/cost.py`). `stopCause()`
  w `runs.ts` czyta z niej **wyłącznie nagłówek** („Order limit" / „Cost limit"); samo zdanie
  zawsze idzie w całości. Przeredagowane u źródła kosztuje nagłówek i nic więcej — zdanie
  dalej mówi prawdę, bo jest modułu. Precedens jest w tym samym katalogu: `refusal.ts` czyta
  klucze agentów z odmowy modułu i z tego samego powodu.

  Zlecenia nie jadą strumieniem — moduł publikuje postęp, a zlecenie jest wierszem do
  odczytania — więc `useRunMonitor` czyta `/runs/{id}/trades` po migawce, przy każdym zdarzeniu
  wywołania narzędzia (bo tylko wtedy może przybyć wiersz) i raz jeszcze na końcu przebiegu
  (ostatni wiersz domyka się po odpowiedzi, która przychodzi po zdarzeniu). Jeden odczyt naraz,
  strażnik na `useRef` — runda trzech agentów inaczej startuje trzy odczyty tej samej listy.

  `outcomeOf()` czyta wiersz `sent` przez to, czy przebieg się skończył: w trakcie to zlecenie
  w drodze, po końcu to zlecenie o nieznanym skutku — dokładnie to, co o tym wierszu mówi
  docstring `TradeOut` w `contract.py`. Zgadywanie? Nie: to jedyne zdanie, jakie ten wiersz
  niesie, i moduł sam je tak nazywa.

  `pickersComeFromTheModule.test.ts` musiał dostać wyjątek na `read_only`: jego wzorzec na
  nazwę narzędzia (`(get|list|read)_…`) łapie tę **właściwość drutu**, którą wybierak czyta,
  żeby oznaczyć narzędzia ruszające rachunek — czyli dokładne przeciwieństwo listy narzędzi
  wpisanej w terminal. Wycięta przed sprawdzeniem, zamiast rozluźniania samego wzorca.

## 9. Infrastruktura

- [x] 9.1 Rejestracja Entra dla `trading-mcp` — w `infra/app-service.tf`, nie w `entra.tf`
- [x] 9.2 App Service w `infra/app-service.tf` — tożsamość, obraz, Easy Auth z `/health` poza wymaganiem
- [x] 9.3 `allowed_applications` modułu ograniczone do tożsamości `teams`
- [x] 9.4 Polityka Key Vault i odwołanie do `gateway-api-key` w ustawieniach aplikacji
- [x] 9.5 Adresy wyjściowe `trading-mcp` w zaporze `capital-gateway`
- [x] 9.6 `TRADING_MCP_URL` i `TRADING_MCP_SCOPE` w ustawieniach `teams`
- [x] 9.7 Instrukcja dla operatora w `modules/trading-mcp/README.md` — `apply -target`, pełny `apply`, kolejność wdrożenia

  **9.1 wylądowało w `app-service.tf`, nie w `entra.tf` jak mówi litera zadania**, i to jest
  ta sama zasada, którą trzyma `market-mcp`: w `entra.tf` siedzą rejestracje, które ktoś
  woła jako *użytkownik* — terminal i trzy API z delegowanym zakresem. Rejestracja bez
  zakresu, istniejąca tylko po to, żeby cudza tożsamość zarządzana miała co pokazać, stoi
  obok swojej aplikacji, bo czytana jest razem z nią. Rozdzielenie ich zostawiłoby dwa
  pliki, w których trzeba trzymać palec naraz.

  `allowed_applications` ma **jeden wpis** i to jest cała treść 9.3. U `market-mcp` są dwa,
  bo archiwum czyta i agent, i teams; tutaj nikt poza `teams` nie ma po co składać zleceń, a
  terminal najmniej ze wszystkich — przeglądarka rozmawia z `teams`, a `teams` tutaj.

  Reguła w zaporze gatewaya jest **osobnym blokiem** (`AllowTradingMcp-*`, priorytety od
  200), a nie poszerzeniem reguły `market-data`. Obie aplikacje stoją dziś na jednym planie
  i najpewniej zgłoszą te same adresy — ale to fakt o planie, nie obietnica, a regułę
  nazwaną modułem da się usunąć razem z modułem.

  Nowego sekretu nie ma: moduł czyta `gateway-api-key`, ten sam, który gateway sprawdza, a
  market-data przedstawia. Polityka Key Vaulta (9.4) jest mimo to obowiązkowa i z dwóch
  powodów naraz — bez niej nie rozwiąże się ani ten klucz, ani `docker_registry_password`, a
  ta druga porażka wygląda jak zepsute poświadczenie do GHCR i kosztowała już godzinę
  diagnozy przy `market-mcp` (komentarz w `app-service.tf`).

  Sprawdzone `terraform plan` na żywym stanie (odczyt, bez `apply`): **5 do utworzenia, 12
  do zmiany, 0 do usunięcia**. Piątka to rejestracja, jej sekret, service principal,
  polityka Key Vaulta i sama aplikacja. Dwunastka to w większości szum, który plan tego
  roota ma od dawna — puste `tags` i listy `allowed_applications` przechodzące w „known
  after apply", bo źródła danych czytające tożsamości zarządzane są odraczane, gdy
  cokolwiek w planie czeka. Prawdziwe zmiany w tej dwunastce są dwie: zapora gatewaya i
  ustawienia `teams`.

## 10. CI i wdrożenie

- [x] 10.1 Filtr i job modułu w `.github/workflows/checks.yml`
- [x] 10.2 `.github/workflows/deploy-trading-mcp.yml` — obraz do GHCR, wdrożenie, smoke check pytający `/health`
- [x] 10.3 `scripts/dev.sh` i `scripts/dev.ps1` — moduł w kolejności startu, port 8060
- [x] 10.4 `README.md`, `docs/architecture.md` i `CLAUDE.md` — moduł w tabeli, na rysunku i w mapie

  **Filtr modułu jest szerszy, niż wyglądałby z nazwy: łapie cały `modules/capital-gateway/`.**
  Ten moduł trzyma migawkę *całego* dokumentu OpenAPI gatewaya, a ten powstaje z tras tak
  samo jak z DTO — węższy filtr (`dtos.py`) byłby filtrem nieprawdziwym, przepuszczającym
  dokładnie tę zmianę, dla której `scripts/contract.py check` istnieje. Logika filtra
  sprawdzona lokalnie na wyciętym kawałku skryptu: zmiana w `capital_gateway/dtos.py`
  uruchamia `capital-gateway` i `trading-mcp`, zmiana w `docs/` nie uruchamia niczego,
  zmiana w samym `checks.yml` uruchamia wszystko.

  Cztery komendy joba przebiegły lokalnie na tym module: `contract.py check` (aktualny),
  `ruff`, `pyright` (0 błędów) i `pytest` — **58 zielonych**.

  **Smoke check tego modułu dowodzi więcej niż żywotności i to jest jego treść.** Proces
  pyta gateway `GET /capabilities` i nie otwiera portu, dopóki odpowiedź nie mówi `demo`
  (`__main__.py`), więc 200 na `/health` znaczy, że kontener dotarł do gatewaya, przez jego
  zaporę, ze wspólnym kluczem — i że sesja jest demonstracyjna. Kontener, któremu nie udało
  się cokolwiek z tych trzech, nigdy nie słucha, a to sprawdzenie zamienia go w nieudane
  wdrożenie zamiast w ciche.

  W skryptach `dev.*` doszły dwie rzeczy ponad literę 10.3, obie z tego samego powodu — bo
  ten moduł **wychodzi** zamiast się degradować, a skrypt ubija wtedy cały stos:

  - `.env` modułu jest wymagany (nie jak `market-mcp`, który ma działające domyślne
    ustawienia dla pętli zwrotnej): gateway sprawdza `X-Gateway-Key` u każdego wołającego,
    loopback włącznie, więc nie ma trybu lokalnego bez klucza;
  - **oba skrypty porównują `CAPITAL_GATEWAY_API_KEY` z `GATEWAY_API_KEY` gatewaya** i
    odmawiają przed startem czegokolwiek. Niezgodność nie jest nieudanym wywołaniem
    narzędzia później — to moduł kończący się w trakcie startu i komunikat „A service
    exited", który nie mówi, o co chodziło.

  `modules/teams/.env.example` dostał `TRADING_MCP_*` — nie było ich tam od grupy 5, a
  skrypty odsyłają do tego pliku („as .env.example does"), więc notatka odsyłałaby do
  czegoś, czego nie ma.

  10.4 zamiast wciskać `trading-mcp` w główny rysunek `docs/architecture.md` dokłada **osobny
  rysunek ścieżki zleceń**: gateway ← `trading-mcp` ← `teams`, prosta linia obok wachlarza
  odczytów. Wciśnięcie jej w tamten rysunek przecięłoby trzy strzałki, żeby powiedzieć coś
  prostszego od każdej z nich. Przy okazji zapisana tam jest zasada podziału gwarancji: demo
  jest sprawdzane w `trading-mcp` i nie da się go wyłączyć ustawieniem, a wszystko, co
  operator *ma* móc zmienić, siedzi w rewizji `teams`.

## 11. Domknięcie

- [ ] 11.1 Przykładowy zespół handlowy w katalogu jako punkt wyjścia dla operatora
- [ ] 11.2 Przebieg od końca do końca na uruchomionym stosie, zakończony zleceniem na koncie demo
- [ ] 11.3 `review.md`

## Nota o równoległości z fazą 3

Ta zmiana i faza 3 wychodzą z `feat/teams-module` i wracają do niego. Punkty styku są dwa:
`teams/contract.py` (7.4 — wyłącznie dodanie modeli) i łańcuch rewizji Alembica w `teams`
(7.1). Ta, która wyląduje w `feat/teams-module` druga, ustawia `down_revision` swojej migracji
na czoło zastane po merge'u pierwszej — bez `alembic merge`.
