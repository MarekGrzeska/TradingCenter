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
- [ ] 7.4 `contract.py` — kształt wiersza śladu handlowego i granic handlowych (wyłącznie dodanie modeli)
- [ ] 7.5 Trasa odczytu zleceń przebiegu, z filtrem właściciela jak reszta modułu
- [ ] 7.6 Testy `-m db`: migracja od zera dochodzi do rewizji czołowej; wiersz przeżywa przerwanie przebiegu

## 8. Terminal

- [ ] 8.1 `pnpm contract:generate` po zmianach w `teams/contract.py`
- [ ] 8.2 Granice handlowe w panelu zespołu; odmowa zapisu pokazana przy agencie
- [ ] 8.3 Narzędzia zapisujące odróżnione od czytających w wybieraku narzędzi
- [ ] 8.4 Zlecenia przebiegu przy agencie, który je złożył — symbol, kierunek, wielkość, skutek
- [ ] 8.5 Zlecenie o nieznanym skutku pokazane jako nieznane
- [ ] 8.6 Granica zleceń jako przyczyna zatrzymania, odróżniona od kosztu
- [ ] 8.7 `pnpm lint`, `typecheck`, `test`, `contract:check` przechodzą

## 9. Infrastruktura

- [ ] 9.1 Rejestracja Entra dla `trading-mcp` w `infra/entra.tf`
- [ ] 9.2 App Service w `infra/app-service.tf` — tożsamość, obraz, Easy Auth z `/health` poza wymaganiem
- [ ] 9.3 `allowed_applications` modułu ograniczone do tożsamości `teams`
- [ ] 9.4 Polityka Key Vault i odwołanie do `gateway-api-key` w ustawieniach aplikacji
- [ ] 9.5 Adresy wyjściowe `trading-mcp` w zaporze `capital-gateway`
- [ ] 9.6 `TRADING_MCP_URL` i `TRADING_MCP_SCOPE` w ustawieniach `teams`
- [ ] 9.7 Instrukcja dla operatora w `modules/trading-mcp/README.md` — `apply -target`, pełny `apply`, kolejność wdrożenia

## 10. CI i wdrożenie

- [ ] 10.1 Filtr i job modułu w `.github/workflows/checks.yml`
- [ ] 10.2 `.github/workflows/deploy-trading-mcp.yml` — obraz do GHCR, wdrożenie, smoke check pytający `/health`
- [ ] 10.3 `scripts/dev.sh` i `scripts/dev.ps1` — moduł w kolejności startu, port 8060
- [ ] 10.4 `README.md`, `docs/architecture.md` i `CLAUDE.md` — moduł w tabeli, na rysunku i w mapie

## 11. Domknięcie

- [ ] 11.1 Przykładowy zespół handlowy w katalogu jako punkt wyjścia dla operatora
- [ ] 11.2 Przebieg od końca do końca na uruchomionym stosie, zakończony zleceniem na koncie demo
- [ ] 11.3 `review.md`

## Nota o równoległości z fazą 3

Ta zmiana i faza 3 wychodzą z `feat/teams-module` i wracają do niego. Punkty styku są dwa:
`teams/contract.py` (7.4 — wyłącznie dodanie modeli) i łańcuch rewizji Alembica w `teams`
(7.1). Ta, która wyląduje w `feat/teams-module` druga, ustawia `down_revision` swojej migracji
na czoło zastane po merge'u pierwszej — bez `alembic merge`.
