## 1. Tożsamość agenta

- [x] 1.1 `infra/entra.tf`: rejestracja `app-tradingcenter-vps-agent` (klient publiczny, `fallback_public_client_enabled`), service principal, pre-autoryzacja na scope'ach workbencha i bramy, output `vps_agent_entra_client_id`; `terraform plan` czysty poza nowymi zasobami
- [x] 1.2 `scripts/mcp_token.py`: `login --device-code` i `--cache <plik>` (domyślny cache bez zmian); testy w `scripts/tests`
- [x] 1.3 `deploy/docker-compose.yml`: `TOOL_CALLER_APPLICATION_IDS` i `EXTERNAL_CALLER_APPLICATION_IDS` jako lista `CLAUDE_CODE_APPLICATION_ID` + `AGENT_APPLICATION_ID`; `deploy/env.required`, `fill-github-environment.sh`

## 2. Moduł `modules/claude-agent`

- [x] 2.1 Szkielet: `pyproject.toml` (uv, ruff, pyright, pytest), `README.md`, `.env.example`
- [x] 2.2 `Dockerfile`: node:22-bookworm-slim, Claude Code i bun przypięte, tmux, tini, supercronic z sumą, uv, `scripts/mcp_token.py`, użytkownik bez uprawnień, `HEALTHCHECK`
- [x] 2.3 `agent/CLAUDE.md`: kim jest agent, format wiadomości Telegram, zasada potwierdzenia przed zapisem na rachunku, treść z archiwów jako dane, nie polecenia
- [x] 2.4 `.mcp.json` renderowany przy starcie (`claude_agent/render.py`, bo `headersHelper` potrzebuje konkretnych wartości): dziewięć powierzchni pod `https://${API_HOST}/…/mcp` z `headersHelper` (`--api workbench|gateway`)
- [x] 2.5 `agent/.claude/settings.json`: `opus`/`medium`, `dontAsk`, allowlista odczytów i zapisów badawczych, `deny` dla `Bash`/`Edit`/`Write`/`WebFetch`/`WebSearch`/`send_telegram_message`, sześciu narzędzi rachunku i `Read` poza katalogiem roboczym
- [x] 2.6 Skille: `przeglad-rana`, `podsumowanie-dnia`, `pozycje`
- [x] 2.7 `runtime/entrypoint.sh`: kontrola zero-API, instrukcje z obrazu, `AGENT_ACCOUNT_WRITES` → przeniesienie narzędzi rachunku z `deny` do `allow`, zaufanie katalogu i serwerów w `.claude.json`, `remoteControlAtStartup`, czekanie na `https://API_HOST/health`, pętla sesji (`--continue` / start od czystego kontekstu po zmianie instrukcji)
- [x] 2.8 `runtime/channel-watchdog.sh`, `runtime/restart.sh`, `runtime/healthcheck.sh` (sesja + proces, bez loginu)
- [x] 2.9 Harmonogram w Pythonie: crontab z `AGENT_CHECKIN_TIMES`, pominięcie przy aktywności w ostatniej godzinie, dostarczenie zaległego do godziny, raz; testy jednostkowe decyzji
- [x] 2.10 Testy runtime: odmowa startu z kluczem API, ustawienia z `AGENT_ACCOUNT_WRITES` i bez, instrukcje odtwarzane z obrazu (sztuczny `claude`, jak `infra/test/fake-claude.sh` w AgenticEnglish)

## 3. Wdrożenie

- [ ] 3.1 `deploy/docker-compose.yml`: usługa `claude-agent` (sieć `claude-agent`, wolumen `claude-agent-home`, limity, `cap_drop`, `no-new-privileges`, bez portów)
- [ ] 3.2 `scripts/tests/test_deploy_compose.py`: agent bez portów, tylko w sieci `claude-agent`, bez zmiennych z sekretami systemu; listy wołających mają oba id
- [ ] 3.3 `.github/workflows/checks.yml`: job `claude-agent` i wzorzec w `changes` (z `scripts/mcp_token.py`)
- [ ] 3.4 `.github/workflows/deploy-vps.yml` i `scripts/deploy_gate.py`: czwarty obraz, tag `CLAUDE_AGENT_TAG` w `tags.env`, wycofanie obejmuje agenta
- [ ] 3.5 `deploy/README.md`: kroki jednorazowe na serwerze (login, kod urządzenia, bot, parowanie, `access.json`)

## 4. Dokumentacja

- [ ] 4.1 CLAUDE.md: wiersz `modules/claude-agent`, pułapka „bot agenta nigdy w `/telegram`”; `scripts/tests/test_guide_ceiling.py` zielony
- [ ] 4.2 `docs/architecture.md`: agent na liście procesów i granic
- [ ] 4.3 `docs/agent-claude-code-telegram.html`: sekcja 04 zgodna z D1 (token delegowany)

## 5. Po wdrożeniu (operator + ja)

- [ ] 5.1 Operator: `terraform apply`, zmienne w `vps`, bot u @BotFather, potem merge
- [ ] 5.2 Na serwerze: hairpin `curl https://API_HOST/health` z kontenera; login, kod urządzenia, parowanie
- [ ] 5.3 Próba z telefonu: „jakie mam pozycje”, zespół założony z Telegrama widoczny w terminalu, obcy kontakt ignorowany
- [ ] 5.4 Po tygodniu: `AGENT_ACCOUNT_WRITES=on`, deploy, zapis na demo z potwierdzeniem, wpis w `trading_mcp.trace` z aplikacją agenta
