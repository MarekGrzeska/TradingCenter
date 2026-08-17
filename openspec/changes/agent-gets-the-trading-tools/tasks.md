## 1. Trzeci serwer narzędzi w agencie

- [x] 1.1 W `agent/config.py` dołożyć `trading_mcp_url`, `trading_mcp_scope` i
  `trading_mcp_request_timeout_seconds = 35.0`, dopisać dwa pierwsze do walidatora
  `_blank_means_unset` i sprawdzić spójność trybu wywołaniem `_checked_server("TRADING_MCP", …)`
- [x] 1.2 W `agent/tools/registry.py` dołożyć `ToolServer(settings, prefix="trading_mcp")`,
  bez `forwards_operator_token`
- [x] 1.3 Testy: trzy serwery konfigurowane niezależnie, adres zdalny bez `scope` odmawia
  startu z komunikatem nazywającym `TRADING_MCP`, brak adresu nie jest błędem, nieosiągalny
  `trading-mcp` nie zabiera narzędzi dwóch pozostałych
- [x] 1.4 `modules/agent/.env.example` i `README.md`: nowe ustawienie i to, co znaczy jego brak

## 2. Zapisujące odróżnione od czytających

- [x] 2.1 W `agent/tools/client.py` dołożyć `read_only: bool | None` do `ToolDescriptor`,
  czytane z `tool.annotations.readOnlyHint`
- [x] 2.2 Dołożyć `ToolOutcomeKind.UNKNOWN` i mapować `UNAVAILABLE` → `UNKNOWN` dla wywołań
  narzędzi, które nie są `read_only is True`, na serwerach potrafiących zapisywać
- [x] 2.3 Testy: narzędzie z `readOnlyHint: true`, z `false` i bez adnotacji; nieoznaczone
  liczy się jako zapisujące

## 3. Ślad przed wysłaniem

- [x] 3.1 Migracja Alembica: `tool_calls.message_id` bez `NOT NULL`, `CHECK` na `outcome`
  rozszerzony o `unknown`
- [x] 3.2 W `agent/store.py` dołożyć `begin_tool_call` (wiersz przed wysłaniem, `message_id`
  `NULL`, `outcome` `unknown`), `settle_tool_call` (skutek, tekst, czas trwania) i
  `attach_tool_calls_to_message` (domknięcie `message_id` po `append_agent_message`)
- [x] 3.3 W `agent/store.py` dołożyć odczyt wywołań osieroconych sesji (`message_id IS NULL`)
- [x] 3.4 W `agent/turn.py` (i w `graph.py`, jeśli to tam pada wywołanie) przeprowadzić
  wywołania zapisujące dwufazowo, czytające zostawić na dotychczasowej paczce po turze
- [x] 3.5 Testy: tura przerwana po wysłaniu zostawia wiersz ze skutkiem `unknown`, powrót
  odpowiedzi domyka wiersz, `message_id` wchodzi po powstaniu wypowiedzi, odczyt czytających
  bez zmian

## 4. Czego agent nie mówi po nieznanym skutku

- [x] 4.1 W `agent/prompt.py` dopisać, że agent ma narzędzia ruszające rachunek
  demonstracyjny, że nieznany skutek nie jest ani potwierdzeniem, ani odmową, i że wywołania
  zapisującego nie ponawia z własnej inicjatywy
- [x] 4.2 Wyprowadzić do modelu wynik `unknown` odróżnialny od `refused` — zdaniem, nie samą
  wartością
- [x] 4.3 Testy: po `unknown` model nie dostaje tury, w której powtórzenie wywołania
  wygląda na poprawną drogę; po `refused` dostaje

## 5. Kontrakt i terminal

- [x] 5.1 W `agent/contract.py` dopuścić `unknown` na skutku wywołania i dołożyć listę
  wywołań osieroconych do odczytu transkryptu
- [x] 5.2 W `modules/terminal` dołożyć gałąź renderu dla skutku „nieznany" i pokazać
  wywołania osierocone w transkrypcie rozmowy
- [x] 5.3 `pnpm test`, `pnpm lint`, `pnpm typecheck`

## 6. Infrastruktura

- [x] 6.1 W `infra/app-service.tf` dopisać tożsamość zarządzaną `agent` do
  `allowed_applications` `trading-mcp` i przepisać komentarz o jednym wołającym
- [x] 6.2 W `infra/app-service.tf` dołożyć `TRADING_MCP_URL` i `TRADING_MCP_SCOPE` do
  `app_settings` agenta
- [ ] 6.3 `terraform plan` na PR, `terraform apply` ręką operatora, potem restart agenta
- [ ] 6.4 Po `apply` sprawdzić odczytem z Azure, nie ze stanu Terraforma: dwa wpisy w
  `allowedApplications` `trading-mcp` i `TRADING_MCP_*` w ustawieniach agenta

## 7. Skrypty i dokumentacja

- [x] 7.1 `scripts/dev.sh` i `scripts/dev.ps1`: podpowiedź o brakującym `TRADING_MCP_URL` w
  `.env` agenta, tak jak dziś o `MARKET_MCP_URL`
- [x] 7.2 `CLAUDE.md`: `trading-mcp` przestaje mieć jednego nazwanego wołającego — poprawić w
  mapie modułów i w akapicie o `.env` agenta
- [x] 7.3 `docs/`: dwa miejsca mówiące o jednym wpisie w `allowed_applications`
  (`teams-fazy-stan.html`, `teams-zegar-i-wyzwalacze.html`)

## 8. Zamknięcie

- [x] 8.1 `uv run pytest`, `uv run ruff check .`, `uv run pyright` w `modules/agent`
- [x] 8.2 `uv run pytest -m db` w `modules/agent` (migracja na kontenerze)
- [x] 8.3 `openspec validate agent-gets-the-trading-tools --strict`
- [ ] 8.4 Sprawdzić na żywo, że agent widzi pozycje i składa zlecenie na demo, i że wiersz
  śladu powstał przed odpowiedzią
