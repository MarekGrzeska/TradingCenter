## Verdict

Wdrożone: druga instancja `capital-gateway` i `trading-mcp` na koncie realnym (profil Compose `live`), granica
`LIVE_ORDER_LIMITS` przed dostawcą, zespoły sięgające konta przez `trading.environment`. Produkcja 9 listopada 2026:
`LIVE_TRADING=on`, `LIVE_ORDER_LIMITS={"US100": "1.0"}`, kontenery `gateway-live` i `trading-mcp-live` zdrowe, team 11
handluje na koncie realnym, a przebieg 338 złożył na nim zlecenie (`team-deterministic-steps`, zadanie 8.2). Zadania
7.1 i 7.2 są więc wykonane. Agent operatora na serwerze ma zapis na koncie realnym włączony
(`AGENT_LIVE_ACCOUNT_WRITES=on`), na demo wyłączony.

Świadomie niedokończone: 7.3 (odczyt `/accounts/preferences` obu kont do README bramy) — README go nie zawiera; 7.4
(próba zlecenia ponad granicę i obserwacja 429) nie została zapisana.

## Verified

- Tylko stan produkcji przy archiwizacji: `docker ps`, `.env` serwera, `list_teams` (team 11 na koncie realnym).
  Testy i CI tej zmiany przeszły przy jej scaleniu; w tym przebiegu nie były uruchamiane ponownie.
- Archiwizowane po `operator-agent-on-telegram`, jak wymaga 7.5 (`claude-agent-access` ma `## Purpose`).

## Gaps

- 7.3: preferencje konta realnego i demo (hedging, dźwignie) w `modules/capital-gateway/README.md`; czy klucz demo loguje
  się na host realny.
- 7.4: zapisany przypadek odmowy ponad `LIVE_ORDER_LIMITS` i obserwacja 429 przy pracy archiwum.
- Pokrycia specyfikacji testami nie odtwarzano przy archiwizacji.
