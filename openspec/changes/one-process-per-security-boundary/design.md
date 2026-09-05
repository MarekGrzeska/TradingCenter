## Context

Osiem App Service na jednym planie B3 (4 vCPU, 7 168 MB). Pomiar 28 sierpnia – 4 września 2026,
co godzinę: plan zużywa medianę 4 519 MB, osiem aplikacji łącznie 2 262 MB (p90 ≈ 2 800), narzut
poza aplikacjami 2 365 MB — stały przy 6, 7 i 8 aplikacjach. Per aplikacja (p50): market-data 457,
agent 393, gateway 372, polymarket-data 290 (szczyt 655 przy `/events/{id}/changes`), social-data
273, strategy 263, trading-mcp 229, telegram-gateway ≈270. Importy każdego modułu ważą 75–150 MB;
gateway pod realnym strumieniem w Dockerze 76 MB, z `MALLOC_ARENA_MAX=2` też 76 (areny nic nie
dają, cache plików 6 MB). Log Dockera z Kudu: przy każdej aplikacji `StartingMsiContainer` i
`StartingAuthContainer`. CPU całej ósemki: 11% jednego vCPU w tygodniu. Motywacja: proposal.md.

Precedens: `agent-and-teams-one-workbench` (19 sierpnia): dwa pakiety bez wzajemnych importów,
`workbench/` jako składanie, `test_layering.py` z AST, dwa schematy pod dwoma kluczami w jednym
`lifespan`, przedrostki `AGENT_`/`TEAMS_`, kolizje tras przez `/teams`, jeden PR, plan „1 to add,
14 to change, 45 to destroy", jedna pułapka (polityka Key Vaulta kluczowana nazwą) złapana na planie.

## Goals / Non-Goals

**Goals:**

- Trzy (warunkowo cztery) procesy zamiast ośmiu, bez zmiany żadnego wymagania i bez ruszenia dwóch
  granic bezpieczeństwa.
- Każdy etap zostawia produkcję działającą i dostarcza liczbę następnemu.
- Liczba, która rozstrzyga o B2, mierzona, nie zakładana.

**Non-Goals:**

- Scalanie danych: sześć baz zostaje sześcioma.
- Scalanie pętli tury modelu, katalogów, kluczy OpenAI — nietknięte, jak 19 sierpnia.
- Zwinięcie `trading-mcp` do bramy albo do workbencha: decyzja z 20 sierpnia stoi z powodem, który
  ten pomiar nie osłabia (rachunek to inna granica niż dane).
- Optymalizacja importów (30–50 MB na proces): nie przesuwa bilansu, nie wchodzi.

## Decisions

### Cel to trzy procesy, wyznaczone regułą z 20 sierpnia, nie liczbą MB

Reguła „zwija się przed właścicielem danych, nie przed granicą bezpieczeństwa" daje dokładnie:
brama (dostawca, klucz strumienia), trading-mcp (rachunek), reszta. Alternatywa „wszystko w jednym,
z bramą włącznie" dałaby ~0,5 GB i jedną tożsamość dla zleceń i dla świec — to jest ta granica,
której workbench nie ma prawa przekroczyć od pierwszego dnia. Alternatywa „dwa procesy: core +
brama, trading-mcp w core" zdejmuje jedną parę sidecarów i wpuszcza każdą linię core na ścieżkę
zlecenia; 20 sierpnia policzono, że to 220 linii netto i zły kierunek błędu. Nie.

### Workbench jest gospodarzem; nazwa App Service zostaje

Core to dzisiejsze `app-tradingcenter-agent`: jego tożsamość siedzi już na każdej liście
`TOOL_CALLER_APPLICATION_IDS`, w roli Postgresa dla `agent` i `teams`, w kliencie terminala. Każda
inna tożsamość oznaczałaby przenosiny wszystkich list naraz zamiast po jednej. Nazwa modułu
została rozstrzygnięta 5 września 2026, przed etapem 3: **`modules/workbench` zostaje**. Tak nazywa
się proces w każdym dokumencie, w `dev.py`, w CI (`checks.yml` uruchamia `terminal` na każdą zmianę
pod `modules/workbench/`) i w pamięci operatora; `core` opisywałoby to samo, a rename to koszt w
pięciu przewodnikach i w każdym linku bez zmiany zachowania. Od 3.2 tabela modułów mówi o
workbenchu jako o gospodarzu archiwum, nie o market-data jako o module.

### Pod-aplikacje montowane pod przedrostkiem, nie routery z przedrostkiem

Workbench użył routerów z przedrostkiem dla `teams`, bo obie powierzchnie były jedną rozmową i
kolidowały w dwóch trasach. Tu pakietów jest pięć, każdy z własnym `/mcp`, własnym `/health`, własnym
`/openapi.json` (z którego terminal generuje kontrakt) i własnym middleware `CallerAccess` z rekordem
tras. `app.mount("/polymarket", polymarket_data.app)` zachowuje to wszystko bez edycji; router z
przedrostkiem wymagałby przepisania pięciu `caller_access` na jeden i pięciu OpenAPI na jeden.
Cena montażu: lifespan pod-aplikacji **nie jest uruchamiany** (Starlette), więc gospodarz robi
wszystko sam i zapełnia `subapp.state`; oraz `request.app` w pakiecie to pod-aplikacja, co jest
dokładnie tym, czego pakiet oczekuje.

### Sześć migracji pod sześcioma kluczami, po kolei, w jednym lifespan

Klucze zostają numerami dawnych portów (8020, 8070, 8090, 8080, 8030, 8050), bo już są w
`schema_version` i w dokumentach. Po kolei, nie równolegle: jedna blokada naraz to jeden wzorzec
oczekiwania i jedna linia w logu na bazę. Proces, który odpowiada sondzie, ma wszystkie sześć baz na
rewizji obrazu — ta sama gwarancja co dziś, tylko szersza.

### Narzędzia w procesie zamiast MCP po sieci — z zachowaniem `/mcp` na zewnątrz

Cztery rejestry narzędzi workbencha dostają źródła lokalne na wzór `LocalTeamsTools`: wywołanie
funkcji, ten sam schemat narzędzia, ten sam sufit, ta sama odmowa. `/mcp` każdego pakietu zostaje
zamontowany, bo kontrakt narzędziowy jest opublikowany (`tc-mcp-kit`, ceiling powierzchni), a pocket
może go kiedyś wołać; dziś jedynym wołającym jest workbench, więc znika transport, nie powierzchnia.

### strategy czyta archiwum przez wstrzyknięty protokół, nie przez pętlę zwrotną

Pętla zwrotna `127.0.0.1` omija sidecar Auth i `caller_access` ją odrzuci — słusznie. Wywołanie po
publicznym hostname działa (etap 3a), ale jest hopem przez platformę do własnego procesu. Docelowo
`strategy` deklaruje protokół `Archive` (dziś ma klienta `archive.py`, 386 linii z własnym
`_ManagedIdentityAuth`), a `workbench/` wstrzykuje implementację nad `market_data` — pakiety nadal
się nie importują, składanie zna oba. To jest ten sam ruch, który `teams_tools` wykonał 19 sierpnia.

### Wskaźniki w `asyncio.to_thread`, bo pętla zdarzeń jest teraz wspólna

Dziś obliczenie wskaźnika (numpy, TA-Lib, synchronicznie) blokuje tylko market-data. W jednym
procesie zablokuje strumień SSE rozmowy i pętle. CPU nie jest problemem (11% jednego vCPU), latencja
jest: dziesiątki ms na 5 000 świec, oddane każdemu tokenowi odpowiedzi w tej chwili. Jedno
`to_thread` w routerze wskaźników i jeden test, że rozmowa nie czeka na wskaźnik.

### Sidecar Auth mierzy się przed etapem 2, bo mógłby zmienić cały plan

Podział ~150 MB między kontener tożsamości a kontener Auth nie jest znany. Jeśli Auth to ≥ 100 MB,
alternatywa „walidacja JWT w module, osiem procesów bez sidecara Auth" zdejmuje ~800 MB bez ruszania
granic i ten plan czeka. Pomiar: godzina bez `auth_settings_v2` na telegram-gateway (najmniej
ryzykowny: `REQUIRE_AUTHENTICATED_PRINCIPAL` sprawia, że bez nagłówków platformy moduł i tak odmawia,
więc godzina to godzina bez powiadomień, nie godzina otwartych drzwi), odczyt working setu, powrót.
Lekcja z 20 sierpnia (AllowAnonymous przepuszczał tokeny bez walidacji) mówi, że to platforma dziś
naprawdę waliduje — dlatego alternatywa jest tylko alternatywą, dopóki liczba jej nie poprze.

**Zmierzone 4 września 2026, 19:09–19:49 UTC**, telegram-gateway z wyłączonym `auth_settings_v2`: working set
spadł z 283 MB do 178–181 MB, czyli **sidecar Auth to ~105 MB**, a kontener tożsamości plus Python to ~180.
Dokładnie na progu. Wniosek: alternatywa „JWT w module” zdejmuje ~105 MB z każdej aplikacji, która zostaje
procesem, i nie wyklucza tego planu — każde zwinięcie zdejmuje obie pary (~230 MB), a walidacja w module
zdjęłaby resztę z trzech procesów docelowych (~315 MB). Decyzja o niej to osobna propozycja (0.3); ten plan
nie czeka na nią, bo jej zysk jest addytywny, nie zamienny.

### Godzina na B2 po etapie 3, nie przed etapem 2

Przed etapem 2 test niczego nie rozstrzyga (127% B2). Po etapie 3 (cztery procesy) rozstrzyga
wszystko: poniżej 85% → B2 zostaje; 85–100% → etap 4 zdejmuje ostatnią parę sidecarów; restarty albo
OOM → B3 zostaje z zapisanym powodem, a plan kończy się z czterema procesami i zyskiem operacyjnym.
Zmiana tieru to nowa maszyna i nowy pull obrazów: ~5 minut przerwy dla wszystkich, w spokojnej
godzinie z otwartym rynkiem, `az appservice plan update --sku B2` i ta sama komenda z `B3` w drugiej
ręce. Terraform dowiaduje się w etapie 5, nie wcześniej — godzina testu to pomiar, nie stan.

### Bilans pamięci, z dwoma założeniami nazwanymi

| Topologia | Procesy | Sidecary | Python | Aplikacje | Plan przy narzucie 2,3 GB | przy 1,5 GB |
|---|---:|---:|---:|---:|---:|---:|
| Dziś | 8 | ≈1 300 | ≈950 | 2 260 | 4 560 (127% B2) | 3 760 (105%) |
| Po etapie 2 | 5 | ≈800 | ≈800 | ≈1 600 | 3 900 (109%) | 3 100 (86%) |
| Po etapie 3 | 4 | ≈640 | ≈700 | ≈1 340 | 3 640 (102%) | 2 840 (79%) |
| Po etapie 4 | 3 | ≈480 | ≈650 | ≈1 130 | 3 430 (96%) | 2 630 (73%) |

Dwie ostatnie kolumny to dwa założenia o tym, ile z narzutu planu zostaje na maszynie o połowę
mniejszej. Nikt tego nie zmierzył; godzina z etapu 3 zamienia obie kolumny w jedną liczbę.

Pierwsza liczba zmierzona zamiast szacowana (zadanie 1.3, 4 września): obraz workbencha w Dockerze,
z dwiema pulami do lokalnej bazy, oboma rejestrami narzędzi i schedulerem, po starcie i po dwóch
minutach: **173 MB** (RSS Pythona 198, anon 164, cache plików 6). W App Service ta sama aplikacja
raportuje p50 393 MB; różnica ~220 MB to dwa sidecary, zgodnie z podłogą z tabeli.

Druga liczba (bramka 2.5/2.6, 5 września, 07:30–08:15 UTC): workbench z oboma archiwami w środku raportuje
`AverageMemoryWorkingSet` 286 → 344 MB w pierwszej godzinie po deployu — wobec 393 + 290 + 273 = 956 MB
trzech osobnych aplikacji. Bramka skrócona z doby do godziny decyzją operatora; alerty pętli obu archiwów
dostały dane dopiero po #248 (workbench nie konfigurował telemetrii), a rekord wołających pod montażem
wymagał #249 — obie rzeczy, których lokalne testy nie widziały.

Trzecia liczba (po 2.7, 5 września, 09:59–10:44 UTC, z pełnym etapem 2 od ~11:35): workbench z trzema
pakietami raportuje 357–375 MB wobec 393 + 290 + 273 + 263 = 1 219 MB czterech osobnych aplikacji; plan
ma pięć App Service zamiast ośmiu.

## Risks / Trade-offs

- **Jedna domena awarii dla sześciu** → App Service nie ma limitu per aplikacja, więc plan był nią
  od zawsze; nowe jest, że restart kontenera restartuje wszystko. Mitygacja: `/events/{id}/changes`
  ograniczone w SQL przed etapem 2 (szczyt 655 MB), `to_thread` dla wskaźników, heartbeat każdej pętli
  w `/health` gospodarza.
- **Deploy restartuje ingest i strumień** przy każdej zmianie dowolnego pakietu → luka ~40 s jak przy
  dzisiejszym deployu market-data, częściej. Brama osobno, więc sesja Capital i jej limit nietknięte.
- **Jedna tożsamość dla powierzchni o różnych regułach zapisu** → rekord tras per pod-aplikacja
  (`caller_access` każdego pakietu bez zmian); model przenosi się z listy w Terraformie do kodu, a
  kod ma testy odmowy, których Terraform nie ma.
- **Pułapka Key Vault z 19 sierpnia wraca** → `azurerm_key_vault_access_policy.apps` kluczowana nazwą,
  adresowana parą (vault, object id); plan każdego etapu musi czytać `0 to add` na dotacji
  workbencha. Zapisane w tasks.md jako warunek apply, nie notatka.
- **Terminal i pocket zmieniają adresy w tym samym PR co pakiet** → `contract:check` jest bramką
  CI; preview environment terminala na PR pokazuje to przed merge.
- **CI traci precyzję** (jeden job na ~40 000 linii) → 3–4 minuty zamiast 1; akceptowane, bo
  równolegle znika pięć jobów.
- **Stare role w Postgresie** zostają puste po przeniesieniu własności → `DROP ROLE` w etapie 5, po
  tygodniu bez błędu połączenia, nie od razu.
- **22,6 EUR może nie przyjść** → plan tak jest zbudowany, żeby po etapie 3 dać zysk operacyjny
  niezależnie od wyniku godziny na B2; proposal.md nazywa to wprost.

## Migration Plan

Kolejność i bramki są w tasks.md; każdy etap to osobny PR (etap 2: trzy), merge dopiero po zielonym
`checks` i zielonym planie Terraforma z `0 to add` na dotacji Key Vaulta. Rollback etapu: revert PR-a
i `terraform apply` poprzedniego stanu; obrazy zwiniętych modułów zostają w GHCR pod swoimi tagami
do końca etapu 5, więc powrót do osobnego App Service to `apply` starego bloku i redeploy starego
tagu. Własność schematu jest przenoszona tym samym skryptem w obie strony.

## Open Questions

- Czy pocket kiedykolwiek zawoła `/mcp` pakietów bezpośrednio. Jeśli nie, montaż `/mcp` na
  zewnątrz można zdjąć w etapie 5; jeśli tak, zostaje. Nie zmienia żadnego zadania.
