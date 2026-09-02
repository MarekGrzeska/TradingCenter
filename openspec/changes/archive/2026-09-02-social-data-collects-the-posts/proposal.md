## Why

Operator śledzi posty Trumpa z Truth Social, bo jedno zdanie o cłach rusza rynkiem szybciej
niż jakakolwiek świeca to pokaże. Dziś robi to poza tym systemem — w `MarekGrzeska/MarketTools`
(C#), gdzie ta funkcja to **1 134 linie**: pobranie RSS, tłumaczenie, ocena wpływu modelem
i strona z listą. Nie widzi jej terminal, nie widzi jej pocket i — co waży najwięcej — nie widzi
jej żaden agent: post jest przesłanką tej samej klasy co cena instrumentu i prawdopodobieństwo
na Polymarkecie, a jedyne miejsce, gdzie da się o niego zapytać, to cudza aplikacja.

`polymarket-data` przeniósł z tego samego źródła archiwum cen i **nazwał tę warstwę jako
świadomie niewziętą** — „Telegram, Truth Social, agregator newsów, oceny modelem", 1 688
z 4 715 linii źródła. To jest jej pierwsza część, bez Telegrama.

## What Changes

- **NOWY moduł `modules/social-data`** (Python, FastAPI, port **8090**), właściciel własnej bazy
  `social`, z dwiema powierzchniami w jednym procesie: kontraktem REST i trasą `/mcp`. Kształt
  wprost z `polymarket-data`, z tego samego powodu — osobny proces MCP nad cudzym archiwum
  dokłada hop i drugą kopię schematu.
- **Nazwa jest szersza niż pierwsze źródło, i to kosztuje trzy rzeczy dziś.** Moduł nazywa się
  `social-data`, nie `truth-social`, więc `source` wchodzi do klucza unikalnego, autor jest
  kolumną, a pobieranie stoi za protokołem źródła. Drugie źródło ma być plikiem, nie refaktorem.
- **Odczyt nie zbiera.** W źródle `GET /posts/{date}` pobierał feed i zapisywał do bazy — odczyt
  z efektem ubocznym. Tu zbiera wyłącznie poller w `lifespan`; kontrakt REST czyta.
- **Bez backfillu: zbiór zaczyna się w dniu wdrożenia.** Feed daje historię po dacie, więc
  nadrobienie przeszłości byłoby możliwe — i nie jest robione, bo archiwum, które zaczyna się
  urwane, kłamie mniej niż archiwum zaczynające się tam, gdzie akurat sięgnął pierwszy przebieg.
- **Odczyt modelu jest ostemplowany i nadpisywany.** Tłumaczenie na polski i ocena wpływu 1–10
  liczone są przy zbiorze i zapisywane obok posta wraz z nazwą modelu i czasem — „ten model o tej
  godzinie dał 7" jest faktem tej samej klasy co „rynek o tej godzinie wyceniał 0,63". Moduł nie
  ma opinii, przechowuje cudzą. Zmiana modelu albo promptu **nadpisuje** odczyt: historią jest
  post, nie jego ocena.
- **Ocena stoi w module, a nie w workbenchu, i to jest wybór wymuszony przez narzędzia.** Gdyby
  osąd zapadał przy pytaniu, narzędzie nie miałoby po czym filtrować, ta sama treść dostawałaby
  inny wynik w dwóch rozmowach, a tokeny szłyby per pytanie zamiast per post. Osąd workbencha
  zostaje osądem workbencha: *czy to zmienia moją pozycję teraz* — na tych danych, nie zamiast nich.
- **Brak klucza OpenAI jest konfiguracją wspieraną**, nie awarią: moduł zbiera, nie wzbogaca,
  i mówi to wprost przez `/meta` oraz przez własne narzędzie statusu.
- **CZTERY narzędzia MCP i wszystkie czytają.** `polymarket-data` ma narzędzia piszące, bo ma
  **listę obserwacji**, którą się uzupełnia; tutaj zbiór jest automatyczny per źródło i nie ma
  czego dodawać. Listy zwracają skrót treści, pełną wydaje osobne narzędzie — inaczej jedno
  wywołanie zjada okno kontekstu.
- **Czwarta para ustawień workbencha** — `SOCIAL_MCP_URL` / `SOCIAL_MCP_SCOPE`, w kształcie trzech
  poprzednich: nieobecność jest konfiguracją wspieraną, oba albo żaden.
- **Port 8090, a nie 8040 ani 8050.** Te dwa zostają niczyje celowo: `.env` sprzed dwóch zmian
  wskazuje na nie i ma się dalej czytać jako serwer wyłączony, zamiast trafiać w działający,
  cudzy moduł.
- **Zakładka „Social" w terminalu i trzecia zakładka w pocket**, obie na wygenerowanym kontrakcie
  (`contract.social.generated.ts`) — lista z ostatnich 24 h, wysoki wpływ na wierzchu, reszta
  zwinięta, treść po polsku z odwrotem na oryginał.
- **Poza zakresem: Telegram i alerty** (próg, deduplikacja powiadomień, kolumna `notified_at`),
  **agregator newsów** i **backfill**. Schemat żadnego z nich nie blokuje.

## Capabilities

### New Capabilities

- `social-data-ingest`: skąd i jak często moduł zbiera, co robi z cichym feedem, dlaczego okno
  24 h obejmuje dwie daty kalendarzowe, i dlaczego nie ma backfillu.
- `social-data-store`: co jest przechowywane i pod jakim kluczem — post, jego bieżący odczyt
  modelu, zużycie tokenów; oraz czego tu nie ma.
- `social-data-enrichment`: tłumaczenie i ocena wpływu — stempel modelu i czasu, nadpisywanie
  zamiast wersjonowania, brak klucza jako stan wspierany.
- `social-data-api`: kontrakt REST, który wyłącznie czyta.
- `social-data-tools`: cztery narzędzia dla modelu, granica „nic nie pisze" i podział na skrót
  oraz pełną treść.
- `social-data-caller-access`: która tożsamość dochodzi do której trasy, trasa po trasie.
- `terminal-social`: zakładka terminala — co pokazuje, jak dzieli posty i co mówi, gdy archiwum
  stoi albo model nie jest skonfigurowany.

Osobnej zdolności `social-data-upstream-access`, którą mają cztery inne moduły, tu nie ma
świadomie: upstreamy są dwa i każdy należy do innej zdolności — feed czyta ingest, model czyta
enrichment. Jedna wspólna powtarzałaby oba.

### Modified Capabilities

Brak. `agent-tool-access` i `teams-tool-access` mówią o „serwerze narzędzi" bez wyliczania
serwerów, a `terminal-shell` wymaga, żeby dołożenie zakładki nie ruszało istniejących — czwarty
serwer i ósma zakładka mieszczą się w tym, co te zdolności już wymagają.

Pocket nie wnosi zdolności, bo jego ekrany nigdy jej nie miały: cały moduł powstał zwykłą ścieżką
gałąź → testy → PR i nie ma dziś ani jednego pliku w `openspec/specs/`. Praca nad jego zakładką
jest w `tasks.md`.

## Impact

- **Nowe**: `modules/social-data/` (moduł, migracje, testy, README, Dockerfile),
  `.github/workflows/deploy-social-data.yml`, zasoby w `infra/` (App Service, baza, rejestracja
  Entra, `allowed_applications` + `TOOL_CALLER_APPLICATION_IDS` dla tożsamości workbencha).
- **Zmieniane**: `scripts/dev.py` (wiersz usługi, rola i baza), `compose.yaml`,
  `.github/workflows/checks.yml` (job modułu; zmiana `social_data/contract.py` odpala joby
  terminala i pocketa), `CLAUDE.md` (tabela modułów, zdanie o portach, czwarty `*_MCP_URL`),
  `docs/architecture.md`.
- **Workbench**: `workbench/config.py` i `.env.example` — czwarty serwer narzędzi.
- **Terminal i pocket**: `scripts/contract.mjs` (nowe źródło), `src/data/config.ts`, rejestr
  zakładek, nowy katalog `src/social/`.
- **Operator, dokładnie raz**: `scripts/grant-schema-ownership.sql` na nowej bazie, i `apply`,
  który musi dojechać przed obrazem egzekwującym ustawienia.
