## Why

Operator steruje systemem z Claude Code przy biurku (`operator-mcp-access`), a z telefonu ma tylko pocket: archiwum do
odczytu i rozmowę z workbenchem. Chce tych samych narzędzi z czatu w Telegramie — pozycje, backtesty, zespoły, alerty, a
po okresie próbnym zapis na rachunku demo — bez otwierania komputera. AgenticEnglish na tym samym VPS dowiódł, że stała
sesja Claude Code z kanałem Telegram działa na subskrypcji, bez klucza API.

## What Changes

- Nowy moduł `modules/claude-agent`: obraz z przypiętym Claude Code, jedna sesja w tmux uruchomiona z kanałem Telegram,
  instrukcje i skille agenta kopiowane z obrazu przy każdym starcie, harmonogram (przegląd rana, podsumowanie dnia,
  nocny restart), watchdog kanału. Wzorzec: `agent/` i `infra/runtime/` AgenticEnglish.
- Nowa usługa `claude-agent` w `deploy/docker-compose.yml`: bez portów, we własnej sieci z wyjściem do internetu, bez
  `edge`, `services` i `data`, bez żadnego sekretu systemu. Wolumen na login subskrypcji, token bota i parowanie.
- Agent sięga po dziewięć powierzchni MCP produkcji tą samą drogą co Claude Code operatora: publicznym `API_HOST`, przez
  Caddy, z tokenem Entra. Token jest delegowany (osoba = operator, rola `admin` operatora), wydany **nowej rejestracji**
  `app-tradingcenter-vps-agent`, więc w każdym logu i w każdej liście wołających agent jest osobną aplikacją.
- Listy wołających narzędzi (`TOOL_CALLER_APPLICATION_IDS` workbencha, `EXTERNAL_CALLER_APPLICATION_IDS` trading-mcp)
  dostają drugi wpis.
- Narzędzia zmieniające rachunek są wyłączone, dopóki konfiguracja ich nie włączy; `send_telegram_message`, `Bash`,
  zapis plików i sieć poza MCP są zabronione bez wyjątku.
- `scripts/mcp_token.py` uczy się logowania kodem urządzenia (serwer nie ma przeglądarki) i pamięci podręcznej we
  wskazanym pliku; obraz agenta zabiera go przy budowie.

Decyzje operatora z 4 listopada 2026 (`docs/agent-claude-code-telegram.html`, sekcja 10): rola `admin`; zapis na rachunku
demo wchodzi w zakres; moduł w tym repozytorium; model `opus`, wysiłek `medium`; wysyłka do innych odbiorców
(`send_telegram_message`) nierozstrzygnięta, więc zabroniona. Odejście od dokumentu: zamiast tokenu aplikacji
(`client_credentials`) token delegowany — powód w `design.md`, D1.

## Capabilities

### New Capabilities
- `claude-agent-runtime`: stała sesja agenta na subskrypcji, kanał Telegram tylko dla operatora, instrukcje z obrazu,
  harmonogram, wznowienie po awarii i czysty start po nocy.
- `claude-agent-access`: czym agent sięga po system — tylko powierzchnie MCP przez krawędź, własna aplikacja z tokenem
  operatora, brak sekretów systemu, wyliczone narzędzia i wyłączony domyślnie zapis na rachunku.

### Modified Capabilities

Brak. Wymagania `operator-tool-access` i `trading-mcp-transport` (zmiana `operator-mcp-access`) już mówią o wyliczonej
liście aplikacji i roli `admin` osoby; agent jest drugim wpisem tej listy, nie nową regułą.

## Impact

- Nowe: `modules/claude-agent/**`; job w `.github/workflows/checks.yml`, obraz w `deploy-vps.yml`.
- `infra/entra.tf` (+ output): rejestracja agenta, klient publiczny z kodem urządzenia, pre-autoryzowana na API
  workbencha i bramy. `terraform apply` jest krokiem operatora **przed** merge.
- `deploy/docker-compose.yml`, `deploy/env.required`, `deploy/scripts/fill-github-environment.sh`,
  `scripts/tests/test_deploy_compose.py`; `scripts/mcp_token.py`.
- Jednorazowo, na serwerze: bot u @BotFather, login subskrypcji, logowanie kodem urządzenia, parowanie bota.
- CLAUDE.md (wiersz modułu, port: żaden), `deploy/README.md`, `docs/architecture.md` (nowy proces na liście granic).
- Wszystkie artefakty są pisane; `review.md` powstaje po implementacji.
