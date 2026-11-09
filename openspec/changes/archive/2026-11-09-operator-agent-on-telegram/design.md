## Context

`operator-mcp-access` otworzył dziewięć powierzchni MCP produkcji jednemu klientowi z zewnątrz: Claude Code operatora.
Drzwi (`tc-entra-auth`) sprawdzają token, rolę `admin` osoby i aplikację z wyliczonej listy. Narzędzia zespołów biorą
właściciela z `X-MS-CLIENT-PRINCIPAL-ID`, który `EdgeAuth` pisze z `oid` tokenu. Workbench nie przyjmuje klucza z sieci
(`service_key=None`), a trading-mcp przyjmuje w sieci wewnętrznej tylko `GATEWAY_API_KEY`. AgenticEnglish na tym samym
VPS uruchamia stałą sesję `claude --channels plugin:telegram@claude-plugins-official` w tmux i ma za sobą miesiąc tej
pracy, wraz z obejściami (watchdog kanału, czekanie na serwer MCP, zaufanie do katalogu w `.claude.json`).

## Goals / Non-Goals

**Goals:** agent na serwerze nie dostaje żadnego przywileju ponad to, co ma klient operatora przy biurku. Wszystko, co
robi, da się w logach przypisać jemu.

**Non-Goals:** czat webowy przez `claude -p` (bramka AgenticEnglish), bo terminal i pocket mają swój czat; głosówki;
wysyłka do innych odbiorców Telegram; zmiana `tc-entra-auth`; zastąpienie reguł alertów.

## Decisions

### D1. Token delegowany operatora, wydany własnej rejestracji agenta

Rejestracja `app-tradingcenter-vps-agent` to klient publiczny z przepływem kodu urządzenia, pre-autoryzowany na scope'ach
workbencha i bramy, tak jak `app-tradingcenter-claude-code`. Operator loguje się raz, kodem urządzenia. Token odświeżania
leży w wolumenie agenta, a token każdego żądania ma `azp` agenta, `oid` i rolę `admin` operatora.

*Odrzucone:* token aplikacji (`client_credentials`) z rolą `admin` przypisaną SP, rekomendowany w
`docs/agent-claude-code-telegram.html`. Taki token niesie `oid` service principala, nie operatora, więc `list_teams`
pokazałby pusty katalog, a zespół założony z Telegrama należałby do SP i nie pokazałby się w terminalu. Do tego dochodzi
`allowed_member_types` += `"Application"` w `infra/`. Obejście, czyli „aplikacja X działa jako osoba Y” w drzwiach, to
podszywanie się wpisane w pakiet współdzielony. *Odrzucone:* klucz współdzielony, bo otwiera REST bramy z pominięciem
strażnika trading-mcp i odwraca decyzję, że workbencha nikt nie woła po sieci. *Odrzucone:* skopiowanie cache'u Claude
Code operatora, bo agent nie byłby wtedy odróżnialny od operatora.

Decyzja operatora „rola `admin`” jest spełniona: to rola `admin` operatora.

### D2. Do systemu przez publiczny adres, nie przez sieć wewnętrzną

Kontener jest w sieci `claude-agent` (zwykły bridge, wyjście do internetu) i woła `https://API_HOST/...`. Caddy dopisuje
`X-TC-Edge` jak każdemu z zewnątrz. Agent nie potrzebuje więc żadnej nowej reguły w drzwiach ani w Caddyfile.

*Odrzucone:* dołączenie do `edge`. Agent zobaczyłby `workbench:80` i `trading-mcp:80` po nazwie, a jedyną barierą byłby
brak klucza. Lepiej, żeby tych nazw w ogóle nie widział. Jeśli hairpin do własnego publicznego IP okaże się na VPS-ie
niemożliwy, zapasem jest `extra_hosts: API_HOST → IP hosta` (bramka Dockera), nadal bez dołączania do `edge`.

### D3. Zapis na rachunku włączany zmienną, potwierdzenie w instrukcji

`AGENT_ACCOUNT_WRITES=on` (środowisko `vps`) sprawia, że entrypoint przenosi sześć narzędzi rachunku z `deny` do `allow`
w ustawieniach, które generuje z obrazu. Każda inna wartość zostawia je w `deny`. Potwierdzenie przed zapisem to reguła
w `CLAUDE.md` agenta. Twardą granicą zostaje strażnik demo w trading-mcp.

*Odrzucone:* hook `PreToolUse` szukający potwierdzenia w ostatniej wiadomości operatora. Czytałby transkrypt i zgadywał,
co jest „tak”, a fałszywe „tak” w treści z archiwum przeszłoby przez niego tak samo jak przez model. *Odrzucone:* dwa
obrazy (z zapisem i bez), bo zmiana zakresu wymagałaby wtedy budowy obrazu zamiast zmiany jednej zmiennej.

### D4. Runtime w bashu i Pythonie, nie kopia `.mjs` z AgenticEnglish

`entrypoint.sh`, `healthcheck.sh` i `channel-watchdog.sh` przechodzą prawie bez zmian. Harmonogram przeglądów
(odpowiednik `checkin.mjs`) jest w Pythonie z testami `uv run pytest`, jak każdy moduł Pythona tutaj: jedna komenda w
CI, `ruff`, `pyright`. Node w obrazie służy tylko Claude Code.

*Odrzucone:* skopiowanie `checkin.mjs` z testami Node. Pierwszy moduł TS/JS poza frontendami wymagałby osobnego
toolchainu w CI dla ~200 linii.

### D5. `scripts/mcp_token.py` w obrazie, z logowaniem kodem urządzenia

Helper dostaje `login --device-code` i `--cache <plik>`. Obraz kopiuje go przy budowie (kontekst budowy to katalog
główny repo, jak dla pozostałych obrazów), a `.mcp.json` agenta woła go jako `headersHelper` z `--api workbench|gateway`.
Jedna ścieżka MSAL dla obu klientów.

*Odrzucone:* osobny helper w module. Dwie kopie tego samego wyboru scope'u i obsługi cache'u, które z czasem by się
rozjechały.

### D6. Moduł w tym repozytorium, w tym Compose

Decyzja operatora. Agent wdraża się `deploy.sh` razem z resztą, z tym samym wycofaniem obrazu. Kontraktem jest MCP,
więc agent nie importuje niczego z innych modułów.

## Risks / Trade-offs

- [Wstrzyknięcie z treści archiwum (posty, transkrypty) w sesji z narzędziami zapisu] → zapis na rachunku domyślnie
  wyłączony; włączenie dopiero po tygodniu samych odczytów; konto demo sprawdzane przez strażnika.
- [Token odświeżania operatora w wolumenie] → działa tylko dla aplikacji agenta i jej dwóch scope'ów; odwołanie przez
  zdjęcie z listy wołających (natychmiast) albo usunięcie rejestracji; `Read` poza katalogiem roboczym zabroniony.
- [Jedna subskrypcja dla agenta i pracy przy repo] → `opus`/`medium`; przegląd zużycia po tygodniu.
- [Kanały Claude Code to research preview; plugin bywa „failed” przy starcie] → wersja przypięta w obrazie, watchdog z
  AgenticEnglish.
- [Hairpin do własnego publicznego IP] → sprawdzić jednym `curl` z kontenera; zapas opisany w D2.
- [Pamięć VPS-a, na którym działa też AgenticEnglish] → `mem_limit` 1536m; `prod-health` przed i po wdrożeniu.
- [Wolumen agenta nie jest w nocnym zrzucie] → strata oznacza ponowny login, kod urządzenia i parowanie, bez utraty
  danych systemu.

## Migration Plan

1. `terraform apply` (operator): rejestracja agenta i pre-autoryzacje; `AGENT_APPLICATION_ID` do środowiska `vps`.
2. Bot u @BotFather (operator); `AGENT_TELEGRAM_OWNER_CHAT_ID` do środowiska `vps`.
3. Merge → deploy. Kontener jest zdrowy bez loginu, więc wdrożenie reszty nie zależy od kroku 4.
4. Na serwerze (`.local/vps/vps.sh`): `/login` subskrypcji, `mcp_token.py login --device-code`, token bota i parowanie
   w sesji.
5. Tydzień samych odczytów, potem `AGENT_ACCOUNT_WRITES=on` w `vps` i deploy.

Wycofanie: zdjęcie `AGENT_APPLICATION_ID` z list wołających zamyka agentowi system bez nowego obrazu. Pełne wycofanie to
revert, a `deploy.sh` przywraca poprzednie obrazy.

## Open Questions

- Pory przeglądów (domyślnie 08:30 i 21:30, czas warszawski) ustawia zmienna, więc da się je zmienić bez zmiany specyfikacji.
