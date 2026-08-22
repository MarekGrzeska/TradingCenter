## Why

Operator obserwuje rynki predykcyjne na polymarket.com i dziś robi to poza tym systemem —
w osobnej aplikacji (`MarekGrzeska/MarketTools`, C#), która zbiera ceny, żeby wysłać alert
na Telegrama, i kasuje historię po siedmiu dniach. Ta aplikacja nie umie odpowiedzieć na
pytanie zadane modelowi, nie widzi jej żaden agent i nie widzi jej terminal.

Prawdopodobieństwo zdarzenia wyceniane przez rynek jest **danymi tego samego rodzaju co
świeca**: szeregiem czasowym, o który operator pyta agenta i który zespół może zważyć obok
ceny instrumentu. Brakuje mu tu wyłącznie modułu, który go trzyma. Warstwa analizy — ocena
wagi zdarzenia, tłumaczenie, wniosek — już istnieje i jest nią workbench; w źródle była
zaszyta w kodzie modułu i to jest ta jedna trzecia, której ta zmiana nie przenosi.

## What Changes

- **NOWY moduł `modules/polymarket-data`** (Python, FastAPI, port **8070**) — jedyne drzwi
  do Polymarketu, właściciel własnej bazy `polymarket`, z dwiema powierzchniami w jednym
  procesie: kontraktem REST i trasą `/mcp`. Kształt wprost z `market-data`, i z tego samego
  powodu, dla którego `market-mcp` przestał istnieć: osobny proces MCP nad cudzym archiwum
  nie dokłada nic poza hopem i drugą kopią schematu.
- **Archiwum cen na wynik, nie na parę Yes/No.** Źródło zapisuje próbkę tylko dla rynku
  mającego dokładnie wyniki „Yes" i „No" — rynki wielowynikowe przepadają po cichu. Tu cena
  jest zapisywana **per wynik**, a rynek dwuwynikowy jest szczególnym przypadkiem.
- **Historia jest dociągana, nie tylko próbkowana.** Źródło zna wyłącznie chwile, w których
  jego worker akurat działał — restart to dziura na zawsze. Moduł MUST umieć uzupełnić
  przeszłość z szeregu czasowego dostawcy i łatać dziury, tak jak `market-data` łata pokrycie.
- **Zmiany w oknach liczone przy odczycie.** Druga pętla, tabela upsertów, marginesy
  dopasowania i tabela deduplikacji powiadomień istnieją w źródle po to, żeby Telegram nie
  spamował. Bez Telegrama to jedno zapytanie z oknem po historii — zawsze świeże, zero stanu.
- **NOWE — dziewięć narzędzi MCP, z czego trzy zapisują.** Sześć czyta (przeszukanie
  publicznej bazy Polymarketu na żywo, przegląd wg tagu, obserwowane wydarzenia, szczegóły,
  historia, zmiany); trzy zmieniają **listę obserwacji**: dodanie wydarzenia, zaprzestanie
  obserwacji, utworzenie grupy. To jest świadome odstępstwo od reguły, którą `market-data`
  trzyma wprost („Zestaw narzędzi wyłącznie czyta"), i dlatego jest tu nazwane, a nie
  przemycone: tam zapisem byłoby mutowanie archiwum świec, tu zapisem jest lista obserwacji —
  to samo, co operator klika w terminalu. Granica przebiega gdzie indziej i też jest twarda:
  **żadne narzędzie nie kasuje historii cen** i żadne nie dotyka pieniądza, bo na Polymarkecie
  ten system niczego nie handluje.
- **Zaprzestanie obserwacji zatrzymuje próbkowanie, ale nie kasuje danych.** Kasowanie
  historii nie jest zdolnością agenta ani żadnego narzędzia — jest czynnością operatora po
  kontrakcie REST.
- **Sufit na liczbę obserwowanych wydarzeń.** Skoro dodanie obserwacji jest zdolnością
  modelu, „dodaj co ciekawe" musi mieć gdzie się zatrzymać. Odmowa jest tania; niewidzialny
  wzrost obciążenia nie jest.
- **Trzecia para ustawień workbencha** — `POLYMARKET_MCP_URL` / `POLYMARKET_MCP_SCOPE`,
  w kształcie znanym z dwóch poprzednich: **nieobecność jest konfiguracją wspieraną**, a nie
  awarią, i oba albo żaden.
- Port **8070 przestaje być niczyj**. `CLAUDE.md` wymienia go dziś wśród trzech portów,
  których `.env` czyta się jako serwer wyłączony — ta zmiana jest świadomą edycją tej linii.
- **Poza zakresem: podstrona terminala.** UI konsumujące wygenerowany kontrakt nie dodaje
  wymagania i jedzie zwykłą ścieżką gałąź → testy → PR, po zarchiwizowaniu tej zmiany. Cięcie
  jest naturalne: moduł z `/mcp` jest użyteczny dla agentów od pierwszego dnia, zanim terminal
  cokolwiek pokaże. Poza zakresem także: cała warstwa alertowa źródła (Telegram, Truth Social,
  agregator newsów, oceny modelem) — **1 688 z 4 715 linii modułu źródłowego, 36%**.

## Capabilities

### New Capabilities

- `polymarket-data-tracking`: co moduł obserwuje i kto o tym decyduje — wydarzenie, jego
  rynki, grupy obserwacji, sufit, i co zostaje po zaprzestaniu obserwacji.
- `polymarket-data-store`: archiwum cen — próbka na wynik, co czyni ją wiarygodną, jak
  moduł doprowadza własną bazę do rewizji, zanim zacznie odpowiadać.
- `polymarket-data-ingest`: skąd biorą się ceny — takt próbkowania obserwowanych rynków,
  uzupełnianie przeszłości, łatanie dziur i co się dzieje, gdy dostawca odmawia.
- `polymarket-data-upstream-access`: jedyne drzwi do Polymarketu — dwa API dostawcy, budżet
  zapytań, kształt odmowy i przeszukiwanie publicznej bazy na żywo.
- `polymarket-data-api`: kontrakt REST dla terminala — obserwacje, grupy, ceny, zmiany
  w oknach, i to, że kasowanie danych jest tu, a nie w narzędziach.
- `polymarket-data-tools`: zestaw narzędzi dla modelu — sześć czytających i trzy zmieniające
  listę obserwacji, sufit powierzchni i to, czego w zestawie nie ma nigdy.
- `polymarket-data-caller-access`: kto sięga po którą powierzchnię — trasa narzędziowa wobec
  REST, wymóg tożsamości wołającego, sonda zdrowia poza wymogiem.

### Modified Capabilities

- `teams-tool-access`: wymaganie „Ta sama nazwa narzędzia z dwóch serwerów jest odmową" jest
  napisane dla dokładnie **dwóch** serwerów — „dwa skonfigurowane serwery", „oba serwery",
  „które z dwóch". Trzeci serwer narzędzi wywraca tę liczbę: kolizja może odtąd objąć trzy
  nazwy, a komunikat wymieniający „oba" jest wtedy niepełny. Wymaganie MUST zostać uogólnione
  do „więcej niż jeden serwer", z komunikatem nazywającym **wszystkie**, które tę nazwę
  ogłaszają.

**Czego ta zmiana w specyfikacjach nie rusza, choć wyglądało, że ruszy.** `agent-tool-access`
i `teams-tool-access` w części o konfiguracji są już napisane na N serwerów, nie na dwa
(„Serwerów MAY być kilka i MUST być konfigurowane niezależnie od siebie"), a `agent-tools`
i `teams-catalogue` biorą zestaw narzędzi od serwera i nie wymieniają żadnego z nazwy.
Trzeci serwer wchodzi w te wymagania bez jednego słowa zmiany — to zasługa uogólnienia
zrobionego przy `agent-and-teams-one-workbench`, nie zbieg okoliczności, i jedyne miejsce,
gdzie tamto uogólnienie nie sięgnęło, to policzone wyżej wymaganie o kolizji nazw.

**Świadomie bez `polymarket-data-database-connection`.** `market-data`, `agent` i `teams`
mają po jednej takiej specyfikacji, razem 3 kopie tego samego zachowania (szyfrowanie, Entra,
odmowa startu na złej konfiguracji) — a zachowanie pochodzi z `packages/tc-runtime`, czyli
z jednej implementacji, testowanej raz w `packages/`. Czwarta kopia byłaby dokładnie tym
przyrostem papieru, który `docs/dlaczego-robi-sie-wolniej.html` zmierzył jako koszt. To, co
jest tu specyficzne dla modułu — migracja przed serwowaniem, pod własnym kluczem blokady
doradczej — jest jednym wymaganiem w `polymarket-data-store`.

## Impact

**Nowy kod.** `modules/polymarket-data/` — pakiet `polymarket_data`, własny `pyproject.toml`,
lock, `Dockerfile`, `alembic`, README. Bierze `tc-runtime` (baza, migracje, Easy Auth)
i `tc-mcp-kit` (tożsamość wołającego, odchudzanie schematów narzędzi, kształt odmowy
upstreamu). Bierze `mcp` przypięty dokładnie tak jak `market-data` — 2.0.0 przeniosło
`FastMCP`.

**Workbench.** `workbench/config.py` dostaje trzecią trójkę pól obok `market_mcp_*`
i `trading_mcp_*`, przepuszczoną przez `for_conversation()` i `for_teams()` oraz przez
`AgentSettings` i `TeamsSettings`. Walidator `_blank_means_unset` obejmuje nowe pola —
`POLYMARKET_MCP_URL=` zostawione w `.env` znaczy to samo co linia nieobecna. Test kolizji
nazw narzędzi w `teams/` przestaje mówić o dwóch serwerach.

**Infrastruktura.** Przybywa: App Service z własną tożsamością zarządzaną, Easy Auth,
baza `polymarket`, wpis workbencha w `allowed_applications` i `TOOL_CALLER_APPLICATION_IDS`
nowego modułu. Listy trzymają id **aplikacji** z `azp`/`appid`, nigdy
`X-MS-CLIENT-PRINCIPAL-ID`. `terraform apply` jest operatora — ta zmiana rusza `azuread_*`,
więc jest jego z konstrukcji. Kolejność jest tą samą pułapką co przy poprzednich modułach:
ustawienia MUST dotrzeć do aplikacji **przed** obrazem, który je egzekwuje.

**CI i narzędzia.** Nowy job w `checks.yml` z filtrem `changes`, nowa para: zmiana
w `polymarket_data/contract.py` odpala job terminala, bo to on trzyma wygenerowanego klienta.
`deploy-polymarket-data.yml` na wzór pozostałych czterech, kończący się `deploy_probe.py`.
`scripts/dev.py` dostaje wiersz w tabeli startowej: port, kolejność, powód.

**Baza.** Czwarta baza w lokalnym kontenerze `compose.yaml`; dev scripts tworzą rolę
i bazę same. Na produkcji jednorazowo `scripts/grant-schema-ownership.sql` — bez tego moduł
nie wstanie.

**Dokumentacja.** `CLAUDE.md`: mapa modułów, tabela komend, linia o portach (8070 znika
z listy niczyich, zostają 8040 i 8050), akapit o `MARKET_MCP_URL` dostaje trzeciego brata.
`docs/architecture.md`. Analiza, z której ta zmiana wyrosła, jest artefaktem opublikowanym
22 sierpnia 2026.

**Czego ta zmiana nie rusza.** `capital-gateway`, `trading-mcp`, `market-data`, granicy do
capital.com ani kontraktu archiwum świec. Reguła „no module imports another module" zostaje
nietknięta: nowy moduł nie importuje niczyjego pakietu, a `packages/` bierze na warunkach,
które `docs/architecture.md` już opisuje.
