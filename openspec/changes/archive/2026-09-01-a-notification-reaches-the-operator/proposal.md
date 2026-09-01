## Why

System wie dziś o rzeczach, o których operator dowiaduje się dopiero wtedy, gdy sam otworzy
terminal. Post z oceną wpływu 9 leży w `social` do następnego zalogowania, decyzja strategii
czeka w `strategy`, a trzy alerty z `alerts-that-still-have-a-reason` piszą **na jeden adres
e-mail jednego operatora**. Kanał, którym człowiek naprawdę dostaje wiadomość natychmiast, jest
poza tym systemem.

`social-data-collects-the-posts` odłożyło to wprost — *„Poza zakresem: Telegram i alerty (próg,
deduplikacja powiadomień, kolumna `notified_at`)"* — a `polymarket-data` nazwało tę warstwę jako
świadomie niewziętą z tego samego źródła (`MarekGrzeska/MarketTools`). To jest ta odłożona część.

## What Changes

- **NOWY moduł `modules/telegram-gateway`** (Python, FastAPI, port **8100**), właściciel bazy
  `telegram`, dwie powierzchnie w jednym procesie: kontrakt REST i trasa `/mcp`. Kształt z
  `polymarket-data` i `social-data`, z tego samego powodu — osobny proces MCP nad cudzą bramą
  dokłada hop i drugą kopię schematu.
- **Nazwa jest wąska celowo, odwrotnie niż w `social-data`.** Tam szersza nazwa kupowała drugie
  źródło za trzy koszty w schemacie. Tu połowa modułu — zakładanie botów — **nie jest przenośna
  na żaden inny kanał**, bo jest rozmową z konkretnym botem Telegrama. Nazwa `notify` obiecywałaby
  kształt, którego ten moduł nie może mieć.
- **Wysyłka jest fire-and-forget i moduł nie pamięta wiadomości.** Wywołujący dostaje odpowiedź
  Telegrama, nie identyfikator w kolejce. Baza trzyma boty, adresatów i przesunięcie `getUpdates`
  — nie treść. **Cena jest wprost**: ponowienie po `429` i deduplikacja są robotą wywołującego, a
  na pytanie „czy ten alert doszedł" moduł nie odpowiada. Dlatego oba wywołujące niżej dostają
  własną zdolność, w której ta robota jest nazwana.
- **`sendMessage` przez Bot API, ale zakładanie bota przez BotFathera — i to nie jest API.**
  BotFather jest botem na czacie, a z botem może rozmawiać wyłącznie **konto użytkownika**, więc
  automat wymaga sesji MTProto (`api_id`/`api_hash`, string sesji). BotFather ma przy tym sufit
  **20 botów na konto**.
- **`TELEGRAM_MTPROTO_SESSION` jest ustawieniem, którego *nieobecność* jest konfiguracją
  działającą** — kształt `MARKET_MCP_URL`. Bez sesji moduł wysyła przez tokeny, które operator
  wkleił, a trasa i narzędzie „załóż bota" mówią wprost, czego brakuje. Z sesją zakładają bota
  same. Credential do prywatnego konta jest wtedy włączony świadomie, nie warunkiem startu.
- **Bot nie może zagadać pierwszy, więc jeden ruch operatora zostaje — i jest jednym tapnięciem.**
  Moduł wydaje deep link `t.me/<bot>?start=<nonce>`, a `/start <nonce>` w `getUpdates` wiąże
  `chat_id` z adresatem. Nie zastępuje tego nic: to ograniczenie Telegrama, nie modułu.
- **Trzej wywołujący, każdy inaczej.** `workbench` przez **piątą parę** `TELEGRAM_MCP_URL` /
  `_SCOPE` w kształcie czterech poprzednich — model decyduje, więc żadnej reguły progu nie ma.
  `social-data` i `strategy` wołają kontrakt REST tożsamością zarządzaną, jak `strategy` woła
  dziś `market-data`, i **każdy wnosi własny próg oraz własny znacznik „już powiedziane"**.
- **Narzędzia MCP piszą, i to jest granica warta nazwania.** Wysłanie wiadomości jest jedynym
  aktem widocznym poza systemem, jaki model może tu wykonać. Model **MUST NOT** zakładać ani
  kasować bota i **MUST NOT** wiązać adresata — to zostaje trasom REST, jak kasowanie historii
  w `polymarket-data`.
- **Port 8100, nie 8040 ani 8050.** Te dwa zostają niczyje z tego samego powodu co przy
  `social-data`: `.env` sprzed zmiany ma się czytać jako serwer wyłączony.
- **Siódma baza i ósmy App Service na tym samym planie i tym samym serwerze**, a serwer to
  `B_Standard_B1ms` z `max_connections = 35`. Sześć istniejących pul po `max_size = 10` to już
  60 potencjalnych połączeń przy 35 dostępnych. Ten moduł **MUST** wziąć pulę mniejszą niż
  domyślna i nazwać powód; sufitu jako takiego ta zmiana nie rusza.
- **Poza zakresem: dwustronność, i powód jest zmierzony.** Rozmowa z workbencha przez Telegram
  wymaga zmiany w workbenchu, nie w tym module: `agent/routers/sessions.py` wiąże sesję z
  `current_principal`, a `_operator_principal` czyta `X-MS-CLIENT-PRINCIPAL-ID` — nagłówek, który
  dla tokenu app-only **nie istnieje** (zmierzone 19 sierpnia 2026, `CLAUDE.md`). Moduł wołający
  własną tożsamością zakładałby rozmowy, których terminal nie widzi, a narzędzia działające w
  imieniu operatora działałyby bez tożsamości — w tym narzędzia handlowe. To osobna zmiana, i ta
  przygotowuje jej schemat: wiązanie `chat_id` ↔ operator powstaje tu, bo `/start` i tak go
  potrzebuje.
- **Poza zakresem: webhook z Azure Monitor** i backfill czegokolwiek. Schemat żadnego nie blokuje.

## Capabilities

### New Capabilities

- `telegram-gateway-delivery`: czym jest wysłanie — fire-and-forget, co wraca do wywołującego,
  limity Telegrama jako część kontraktu, i czego moduł świadomie nie pamięta.
- `telegram-gateway-destinations`: bot, adresat i wiązanie — deep link z nonce, `/start`,
  przesunięcie `getUpdates`, oraz co się dzieje z adresatem, który zablokował bota.
- `telegram-gateway-bots`: zakładanie i kasowanie bota przez BotFathera, sesja MTProto jako
  ustawienie opcjonalne, sufit 20 botów, i co moduł odpowiada bez sesji.
- `telegram-gateway-api`: kontrakt REST — trasy, ich odmowy, i które z nich piszą.
- `telegram-gateway-tools`: narzędzia dla modelu, granica „wysyła, ale nie zakłada i nie wiąże".
- `telegram-gateway-caller-access`: która tożsamość dochodzi do której trasy, trasa po trasie.
- `telegram-gateway-upstream-access`: dwie powierzchnie Telegrama, ich sekrety i jedna droga do
  każdej z nich.
- `social-data-alerts`: który post jest wart powiadomienia, czym jest „już powiedziane", i co
  robi moduł bez skonfigurowanej bramy.
- `strategy-alerts`: która decyzja jest warta powiadomienia i jak nie powtarza się co przebieg.

Zdolności `social-data-*` nie ma dziś w `openspec/specs/` — zmiana `social-data-collects-the-posts`
nie jest jeszcze zarchiwizowana — więc próg posta wchodzi jako **nowa** zdolność obok tamtych, nie
jako delta do nich.

### Modified Capabilities

Brak. `agent-tool-access` i `teams-tool-access` mówią o „serwerze narzędzi" bez wyliczania
serwerów, więc piąty mieści się w tym, czego już wymagają — ten sam argument, którym `social-data`
uzasadniło czwarty. `strategy-runtime` zostaje nietknięte: powiadomienie o decyzji jest dodane
obok pętli, nie zmienia tego, jak decyzja powstaje.

## Impact

- **Nowe**: `modules/telegram-gateway/` (moduł, migracje, testy, README, Dockerfile),
  `.github/workflows/deploy-telegram-gateway.yml`, zasoby w `infra/` (App Service, baza
  `telegram`, rejestracja Entra, `allowed_applications` + `TOOL_CALLER_APPLICATION_IDS` dla
  workbencha oraz `REST_CALLER_APPLICATION_IDS` dla `social-data` i `strategy`), sekrety w
  Key Vault (token bota, `api_id`/`api_hash`, string sesji).
- **Zmieniane**: `scripts/dev.py` (wiersz usługi, rola i baza), `compose.yaml`,
  `.github/workflows/checks.yml` (job modułu), `CLAUDE.md` (tabela modułów, zdanie o portach,
  piąty `*_MCP_URL`), `docs/architecture.md`.
- **Workbench**: `workbench/config.py` i `.env.example` — piąty serwer narzędzi.
- **social-data i strategy**: `config.py` i `.env.example` każdego (adres bramy i scope, oba albo
  żaden), klient wychodzący w kształcie `strategy/archive.py`, oraz migracja dokładająca znacznik
  „już powiedziane" w bazie każdego z nich.
- **Operator, dokładnie raz**: `scripts/grant-schema-ownership.sql` na bazie `telegram`, oraz
  `apply`, który MUST dojechać przed obrazem egzekwującym ustawienia.
- **Terminal i pocket**: bez zmian. Ten moduł nie ma ekranu — powiadomienie *jest* jego ekranem.

`design.md`, `specs/` i `tasks.md` powstają razem z tą propozycją, bo zmiana wnosi moduł, kontrakt,
infrastrukturę i wybory, które trzeba będzie później wytłumaczyć. `review.md` powstanie **po**
zadaniach, bo recenzuje implementację i diff — i ta zmiana go zarobi: sekret w bazie, automat na
prywatnym koncie i brak kolejki to trzy miejsca, w których pudło jest ciche.
