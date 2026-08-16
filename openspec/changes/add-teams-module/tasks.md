## 1. Szkielet modułu

- [x] 1.1 Katalog `modules/teams/` z `pyproject.toml`, `README.md`, `.env.example`, `Dockerfile`
- [x] 1.2 `config.py` — ustawienia bazy, tożsamości, dostawcy modeli, serwera narzędzi
- [x] 1.3 Walidatory `Settings()`: tryb bazy, tryb serwera narzędzi, niepusty katalog modeli ze stawkami
- [x] 1.4 `db.py` — pula połączeń, dostawca poświadczenia tożsamości, `advisory_lock` z kluczem 8050
- [x] 1.5 `migrate.py` i `schema_version.py` — bliźniaki z `agent`
- [x] 1.6 `auth.py` — odczyt tożsamości ustalonej przed modułem
- [x] 1.7 `app.py` — `lifespan` w kolejności: ustawienia, pula, blokada, migracje, sprawdzenie rewizji
- [x] 1.8 `GET /health` poza wymaganiem tożsamości
- [x] 1.9 Testy: odmowa startu przy każdej niespójnej konfiguracji z 1.3 i przy trybie lokalnym ze zdalnym adresem

  PR #105. Jedno odstępstwo od planu: pusty szkielet Alembica (`migrations/env.py`,
  `alembic.ini`, puste `versions/`) wylądował tutaj zamiast w grupie 2, bo
  `schema_version.expected_heads()` potrzebuje istniejącego katalogu migracji, żeby
  w ogóle zadziałać — zero migracji jest poprawnym stanem „na głowie".

## 2. Schemat bazy

- [x] 2.1 Alembic w module — `migrations/env.py`, pierwsza rewizja
- [x] 2.2 Tabele `teams` i `team_revisions` (definicja jako JSONB, wersja, właściciel)
- [x] 2.3 Tabele `runs`, `run_steps`, `tool_calls`
- [x] 2.4 Tabela `usage` ze stawkami zapisywanymi na wierszu
- [x] 2.5 Testy `-m db`: migracja od zera dochodzi do rewizji czołowej

  PR #106. `env.py` już istniał z grupy 1 — tu doszła pierwsza rewizja (trzy migracje:
  `0001` katalog, `0002` przebiegi, `0003` zużycie). `run_steps` to jeden wiersz na
  agenta w przebiegu, nie na rundę — rundy siedzą w `tool_calls`, jak w `agent`
  rozdzielone są `messages`/`tool_calls`.

## 3. Kontrakt i jego generowanie

- [x] 3.1 `teams/contract.py` — kształty definicji, rewizji, katalogu, przebiegu, kroku, zużycia
- [x] 3.2 `teams/openapi.py` — bliźniak z `market-data`, razem z `require_response_fields`
- [x] 3.3 Uogólnienie `modules/terminal/scripts/contract.mjs` na wiele źródeł, każde ze swoim plikiem wyjściowym
- [x] 3.4 Sprawdzenie, że wyjście dla `market-data` nie zmieniło się co do bajtu
- [x] 3.5 `pnpm contract:generate` wytwarza plik dla modułu; `contract:check` wykrywa jego nieaktualność

  PR #108. `contract.py` nie ma warstwy domenowej pod sobą — `TeamDefinition` jest
  jednocześnie tym, co siedzi w JSONB, i tym, co jedzie na drucie, a każdy `*Out` czyta
  wiersz swoim `from_row`. Wyjście dla `market-data` wyszło bajt w bajt takie samo.

## 4. Katalog zespołów

- [x] 4.1 Model domenowy definicji: agent, zależność, granice kosztu
- [x] 4.2 Zapytania `store.py`: zapis rewizji, odczyt rewizji, lista katalogu, wycofanie zespołu
- [x] 4.3 Walidacja definicji przy zapisie: cykl, agent nieosiągalny, nieznany model, nieznane narzędzie
- [x] 4.4 Routery katalogu — lista, odczyt, zapis rewizji, wycofanie
- [x] 4.5 Ograniczenie odczytu i zapisu do tożsamości właściciela; odmowa nieodróżnialna od nieistnienia
- [x] 4.6 Testy: zapis kolejnej rewizji nie rusza poprzedniej; wycofanie zespołu zostawia przebiegi
- [x] 4.7 Testy: każda odmowa z 4.3 nazywa agenta albo zależność

  PR #110. 4.1 zapadło już w grupie 3: `TeamDefinition` jest modelem domenowym i wiadomością naraz,
  więc tutaj nie doszła druga jego kopia. Walidacja rozpadła się na dwie po tym, czego
  potrzebuje: kształt (cykl, agent bez żadnej krawędzi, krawędź wskazująca nieznanego
  agenta) siedzi w `contract.py` i odrzuca ciało żądania, zanim dojdzie ono do routera;
  otoczenie (katalog modeli, ogłoszenie serwera narzędzi) w nowym `validation.py`. Obie
  drogi kończą się 422 i obie nazywają agenta.

  Narzędzia sprawdzane są przy zapisie wobec `app.state.announced_tools`, które na razie
  jest `None` — grupa 6 wstawi tam sesję z serwerem narzędzi. Do tego czasu zapis definicji
  przypisującej agentowi narzędzie jest odmawiany komunikatem nazywającym brak serwera, a
  nie brak narzędzia; zespół bez narzędzi zapisuje się normalnie, tak jak normalnie ruszy
  bez serwera (`teams-tool-access`).

  Dwa dodatki wobec litery listy: `GET /teams/{id}/revisions/latest` (canvas musi mieć od
  czego zacząć) i regeneracja `contract.teams.generated.ts` — dokument OpenAPI zmienił się
  od samych tras, mimo że `contract.py` nie drgnął.

## 5. Katalog modeli

- [x] 5.1 Wpis katalogu modeli w konfiguracji — identyfikator, nazwa, porządek kosztu, stawki jako `Decimal`
- [x] 5.2 `GET /models`
- [x] 5.3 Odmowa zapisu rewizji wskazującej model spoza katalogu i rewizji bez modelu przy agencie
- [x] 5.4 Odmowa uruchomienia rewizji wskazującej model wycofany z konfiguracji
- [x] 5.5 Testy: rewizja na wycofanym modelu pozostaje czytelna wraz ze śladem swoich przebiegów

  PR #111. 5.1 stało już w `config.py` z grupy 1 (`ModelCatalogueEntry`, stawki jako `Decimal`,
  odmowa startu przy wpisie bez stawki) — tutaj doszła nad tym warstwa odpytywalna:
  `models_catalogue.py`, bliźniak z `agent` bez `default_model_id` i bez `resolve()`.
  Ten brak jest celowy: sesja może powstać bez wskazania modelu, rewizja nie może, więc
  fallback byłby dokładnie tą cichą podmianą, której zabrania `teams-models`.

  5.3 rozpadło się na dwie odmowy w dwóch miejscach. Model spoza katalogu łapie
  `validation.py` (nazywa agenta i model). Agent bez modelu łapie `TeamDefinition` —
  walidatorem `mode="before"`, żeby komunikat nazwał agenta jego kluczem, a nie pozycją
  na liście: samo `model_id` jako pole wymagane dałoby `agents.2.model_id`, czyli
  operatora liczącego wiersze na canvasie.

  5.4 to `validation.check_runnable`, wołane przez router przebiegu z grupy 7 — tutaj
  pokryte testem na samej funkcji. Połowa narzędziowa tego sprawdzenia (narzędzie, którego
  serwer już nie ogłasza) dojdzie do niej w grupie 6.

  `contract.py` urósł o `ModelOut`, więc `contract.teams.generated.ts` przegenerowany.

## 6. Dostęp do serwera narzędzi

- [x] 6.1 `tools/client.py` — bliźniak z `agent`: jedna sesja, tożsamość na żądanie, `ToolOutcome`
- [x] 6.2 Zawężenie zestawu narzędzi do przypisanych agentowi w definicji
- [x] 6.3 Odmowa uruchomienia przebiegu, gdy agent ma narzędzia, a serwer jest nieosiągalny
- [x] 6.4 Odmowa uruchomienia rewizji wskazującej narzędzie, którego serwer już nie ogłasza
- [x] 6.5 Górna granica czasu wywołania; przekroczenie odróżnione od odmowy narzędzia
- [x] 6.6 Testy: zespół bez przypisanych narzędzi rusza mimo nieosiągalnego serwera
- [x] 6.7 Testy: moduł wstaje i obsługuje katalog bez skonfigurowanego serwera narzędzi

  PR #112. Jedno świadome odstępstwo od bliźniaka i jeden podział, który warto znać:

  - **`list_tools()` rzuca, zamiast oddać pustą listę.** W `agent` brak narzędzi to
    gorsza, ale użyteczna tura; tutaj `ToolServerUnavailable` jest tym, co pozwala
    odmówić uruchomienia zamiast wypuścić kilku agentów zgadujących niezależnie, każdy
    za pieniądze. `call()` zostaje bez zmian — w trakcie przebiegu awaria kosztuje
    jednego agenta jedną odpowiedź, nie cały ślad.
  - **6.2–6.4 wylądowały w `tools/assignment.py`,** nie w kliencie. `plan_tools()`
    rozwiązuje nazwy z definicji raz na przebieg — dwa razy oznaczałoby, że dwaj agenci
    tego samego przebiegu pracują na dwóch różnych listach narzędzi.
  - **Zespół bez narzędzi w ogóle nie dotyka serwera** — nie „pyta i wybacza". Awaria
    market-mcp nie zatrzymuje przebiegu, który go nigdy nie potrzebował.
  - **`ToolServer` wisi w `lifespan`** i nie łączy się przy starcie; sesja otwiera się
    przy pierwszym użyciu. To jest to, co czyni 6.7 czymś więcej niż zapewnieniem.
  - **`app.state.announced_tools` zniknęło,** a sprawdzenie przy zapisie pyta serwer —
    tak, jak zapowiadała notka grupy 3. `announced_tool_names()` oddaje `None`, gdy nie
    ma kogo zapytać, więc `validation.py` dalej rozróżnia „nie ma serwera" od „nie ma
    tego narzędzia". Zapis zespołu z narzędziami przestał być odmawiany zawsze.
  - **Ustalenie dla grupy 7, znalezione po drodze:** sesja MCP musi zostać otwarta
    w zadaniu, które żyje tyle, co ona. Otwarta w zadaniu requestu, które zaraz wraca,
    zostawia scope'y anyio na stosie tamtego zadania i wywala „Attempted to exit a cancel
    scope that isn't the current task's current cancel scope" — w miejscu niemającym nic
    wspólnego z przyczyną. Dlatego sprawdzenie przy zapisie otwiera własną, krótką sesję,
    a nie pożycza tej z `app.state`.

## 7. Wykonanie przebiegu

- [x] 7.1 `provider.py` — bliźniak z `agent`: strumieniowanie, protokół dostawcy, odczyt zużycia
- [x] 7.2 Pętla jednego agenta: model ↔ narzędzia z granicą rund
- [x] 7.3 Kompilator definicji do grafu wykonania — węzeł na agenta, krawędzie z zależności
- [x] 7.4 Podawanie agentowi wyłącznie pracy jego poprzedników
- [x] 7.5 Równoległa praca agentów, których zależności są spełnione
- [x] 7.6 Zapis śladu na bieżąco: krok agenta, wywołanie narzędzia, wiersz zużycia
- [x] 7.7 Statusy przebiegu wraz z przyczyną zatrzymania
- [x] 7.8 Górna granica czasu przebiegu i przerwanie przebiegu przez operatora
- [x] 7.9 Routery przebiegu — uruchomienie, odczyt, przerwanie, lista przebiegów zespołu
- [x] 7.10 Strumień postępu; zerwanie odbioru nie przerywa przebiegu
- [x] 7.11 Odzysk przy starcie: przebieg zastany jako trwający zostaje zamknięty jako nieudany
- [x] 7.12 Testy: przebieg przerwany, błędny i przekraczający czas zostawiają ślad
- [x] 7.13 Testy: zmiana definicji w trakcie przebiegu nie zmienia rewizji, na której on biegnie

  PR #113. Pięć rzeczy warto znać, zanim ktoś zajrzy do `teams/runner/`:

  - **LangGraph niesie graf zespołu, nie pętlę agenta.** Węzeł na agenta i krawędzie
    operatora — to z tego bierze się i kolejność, i równoległość, bez pisania planisty.
    Wewnątrz węzła jest zwykła pętla `while` z sufitem rund: zagnieżdżanie drugiego grafu
    w każdym węźle dołożyłoby superkroków między pytaniem operatora a odpowiedzią, a sufit
    czyta się jako granica pętli, bo nią jest.
  - **Zawężenie do poprzedników jest w `graph.py`,** nie w węźle. Stan LangGrapha trzyma
    pracę wszystkich (inaczej nie da się jej przekazać), więc miejscem, w którym agent
    dostaje wyłącznie swoje wejście, jest budowa węzła — `_predecessors_of` to całość
    tego mechanizmu.
  - **Sufit rund został w kodzie (6), limit czasu w konfiguracji (900 s).** „Ile razy
    agent może sięgnąć po narzędzie" to własność bezpieczeństwa, której nie podnosi się
    dlatego, że akurat przeszkadza; „jak długo wolno biec przebiegowi" zależy od tego, jak
    duży zespół operator złożył. Sufit jest niższy niż ósemka z `agent`, bo tu mnoży się
    przez liczbę agentów.
  - **7.6 wchodzi w grupę 8 i to jest nieuniknione.** Wiersz zużycia powstaje przy każdym
    wywołaniu modelu, ze stawkami kopiowanymi na wiersz i policzonym kosztem — czyli 8.1,
    8.2 i 8.3 są zrobione po drodze, bo bez nich nie da się zapisać wiersza, którego
    schemat wymaga stawek. Dla grupy 8 zostają granice kosztu (8.4, 8.5) i `GET /usage`
    (8.6) wraz z ich testami.
  - **Rejestr przebiegów siedzi w pamięci procesu** — plan ma dokładnie jednego workera
    (`infra/app-service.tf`), a to, czego pamięć nie obejmuje, zamyka `fail_unfinished_runs`
    przy starcie: przebieg zastany jako trwający należy do procesu, którego już nie ma.

## 8. Koszt i granice

- [ ] 8.1 Wiersz zużycia na każde wywołanie modelu, ze wskazaniem przebiegu, agenta i modelu
- [ ] 8.2 Koszt liczony i zapisywany w chwili powstania wiersza, wraz ze stawkami
- [ ] 8.3 Brak informacji o tokenach zapisany jako brak, nie jako zero
- [ ] 8.4 Sprawdzenie granicy kosztu przebiegu przed wywołaniem modelu
- [ ] 8.5 Sprawdzenie granicy dobowej zespołu przed uruchomieniem przebiegu
- [ ] 8.6 `GET /usage` z rozbiciem pozwalającym przypisać koszt agentom
- [ ] 8.7 Testy: zmiana stawki nie rusza kosztu wierszy sprzed zmiany
- [ ] 8.8 Testy: przebieg dobijający do granicy zatrzymuje się ze wskazaniem kosztu

## 9. Terminal

- [ ] 9.1 Zależność `@xyflow/react`; wpis w `src/app/tabs.ts`, katalog widoków zakładki
- [ ] 9.2 `VITE_TEAMS_HTTP` w `src/data/config.ts` i proxy `/teams-api` w `vite.config.ts`
- [ ] 9.3 Warstwa wywołań modułu na typach generowanych z kontraktu
- [ ] 9.4 Widok katalogu — lista zespołów, otwarcie do edycji, uruchomienie przebiegu
- [ ] 9.5 Canvas zespołu: agenci, zależności, rola i model przy każdym agencie
- [ ] 9.6 Edycja w widoku zespołu — dodanie i usunięcie agenta, poprowadzenie i usunięcie zależności
- [ ] 9.7 Panel agenta — rola, prompt, wytyczne, wybór modelu z katalogu, wybór narzędzi z ogłaszanych
- [ ] 9.8 Odmowa zapisu pokazana przy agencie albo zależności, której dotyczy
- [ ] 9.9 Monitor przebiegu na tym samym canvasie — stan agentów, ich praca, wywołane narzędzia
- [ ] 9.10 Odbiór postępu; zamknięcie i ponowne otwarcie widoku pokazuje stan bieżący
- [ ] 9.11 Testy: wybierak modeli i narzędzi powstaje bez identyfikatorów wpisanych w kod terminala
- [ ] 9.12 `pnpm lint`, `typecheck`, `test`, `contract:check` przechodzą

## 10. Infrastruktura

- [x] 10.1 Rejestracja Entra dla modułu w `infra/entra.tf`
- [x] 10.2 App Service w `infra/app-service.tf` — tożsamość, obraz, Easy Auth z `/health` poza wymaganiem
- [x] 10.3 Polityka dostępu do Key Vault dla tożsamości modułu
- [x] 10.4 Sekret `teams-openai-api-key` i odwołanie do niego w ustawieniach aplikacji
- [x] 10.5 Baza logiczna `teams` i reguły zapory dla adresów wyjściowych aplikacji w `infra/database.tf`
- [x] 10.6 Tożsamość modułu w `allowed_applications` serwera narzędzi
- [x] 10.7 Instrukcja dla operatora: `apply -target`, pełny `apply`, `grant-schema-ownership.sql`

  PR #107. Kod napisany, `terraform validate` przechodzi; `apply` pozostaje robotą
  operatora, więc
  w Azure nie stoi jeszcze nic. Cztery rzeczy warte odnotowania:

  - **Katalog modeli i klucz są osobne od `agent`.** `var.teams_models` obok
    `var.agent_models` i sekret `teams-openai-api-key` obok `openai-api-key` — dwie linie
    na rachunku OpenAI zamiast jednej, inaczej kosztu eksperymentów nie da się ocenić.
  - **Easy Auth modułu przyjmuje też audience `market-data`,** dokładnie jak `agent`.
    Terminal ma dziś jeden token, brany na zakres `market-data`; własny zakres modułu jest
    zarejestrowany i pre-autoryzowany, ale nic go jeszcze nie prosi. Grupa 9 nie musi więc
    ruszać `src/auth/`.
  - **Piąta aplikacja na planie B2,** którego pomiar (83% pamięci) zrobiono przy czterech.
    Alarm `plan_memory` w `monitoring.tf` jest tym, co to wyłapie; odpowiedzią zostaje
    większy SKU, nigdy drugi worker.
  - **10.7 wylądowało w `modules/teams/README.md`** (sekcja „Deploy") — nie ma w repo
    strony operatorskiej, a instrukcje `agent` zostały wtedy w Migration Plan zmiany,
    czyli tam, gdzie po archiwizacji nikt ich nie szuka. Jedna rzecz jest tam jawnie
    oznaczona jako do sprawdzenia: dokładne wywołanie zakładające rolę Entra w bazie nie
    zostało nigdzie zapisane, gdy robiono to dla `agent`.

## 11. CI i wdrożenie

- [x] 11.1 Filtr i job modułu w `.github/workflows/checks.yml`
- [x] 11.2 Rozszerzenie filtra terminala o `modules/teams/teams/contract.py`
- [x] 11.3 `.github/workflows/deploy-teams.yml` — obraz do GHCR, wdrożenie, smoke check pytający `/health`
- [x] 11.4 `scripts/dev.sh` i `scripts/dev.ps1` — moduł w kolejności startu, tworzenie bazy i roli, gdy ich nie ma
- [x] 11.5 `README.md` i `docs/architecture.md` — moduł w tabeli i na rysunku
- [x] 11.6 `CLAUDE.md` — moduł w mapie, jego komendy i port

  PR #109. Cztery rzeczy warte odnotowania:

  - **`deploy-teams.yml` pyta o jedno i drugie** — płaszczyzny sterowania o obraz i
    `/health` o proces, dokładnie jak `deploy-agent.yml` po 16 sierpnia. Kolejność jest
    tu odwrotna niż w grupie 10: workflow istnieje, zanim aplikacja stoi w Azure, więc
    pierwszy jego przebieg będzie dopiero po `apply` operatora.
  - **Zakładanie bazy i roli wyszło do funkcji** (`ensure_database` w `dev.sh`,
    `Confirm-LogicalDatabase` w `dev.ps1`) — trzecia baza była momentem, w którym kopia
    tego samego bloku przestała się bronić.
  - **Poprawione po drodze:** `README.md` i `CLAUDE.md` twierdziły, że `agent` nie ma
    ścieżki wyjętej spod Easy Auth i potwierdza wdrożenie tylko przez płaszczyznę
    sterowania. Ma ją od 16 sierpnia i jego workflow pyta `/health` — jedyną aplikacją
    bez tej możliwości jest `capital-gateway`, do którego runner nie ma dostępu sieciowego.
  - **Rysunek w `docs/architecture.md` przerysowany:** `teams` stoi obok `agent`, nie pod
    nim, i oba biorą narzędzia z `market-mcp`. Między nimi nie ma krawędzi — i o to
    chodziło.

## 12. Domknięcie

- [ ] 12.1 Zespół przykładowy w katalogu jako punkt wyjścia dla operatora
- [ ] 12.2 Przebieg od końca do końca na uruchomionym stosie
- [ ] 12.3 `review.md`
