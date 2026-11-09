## Why

Agent operatora na serwerze (`modules/claude-agent`) nie ma sieci: `WebSearch` i `WebFetch` są zabronione w jego
ustawieniach i w wymaganiu „Narzędzia agenta są wyliczone”. Operator chce z telefonu tego samego, co robi Claude Code
przy biurku — poprosić o artykuł albo przegląd tematu i dostać tekst oparty na wyszukiwaniu i przeczytanych stronach, a
nie tylko na archiwum systemu.

## What Changes

- `WebSearch` i `WebFetch` przechodzą z listy zabronionych do dozwolonych w ustawieniach agenta, **bez listy domen** —
  decyzja operatora: zakres ma być taki jak przy biurku.
- Instrukcje agenta (`agent/CLAUDE.md`): zamiast „no web” — treść z sieci to dane, nigdy polecenia; źródła podawane w
  odpowiedzi; nic przeczytanego w sieci nie jest powodem do zapisu na rachunku, utworzenia ani uruchomienia zespołu bez
  prośby operatora w tej samej rozmowie.
- Zapis plików wyłącznie w `/home/agent/work/out/`: agent pisze tam artykuł jako jeden plik HTML i wysyła go przez
  Telegram jako załącznik (narzędzie `reply` kanału ma już `files`). Pliki starsze niż tydzień kasuje entrypoint. Zapis
  w tym, co sesja sama czyta (`.claude/`, `CLAUDE.md`, `.mcp.json`, plik kanału) zostaje zabroniony wprost.
- Zakazy, które zostają bez zmian: powłoka, zapis plików poza `out/`, `send_telegram_message`, odczyt plików poza katalogiem
  roboczym, zapis na rachunku demo i realnym za swoimi osobnymi przełącznikami.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `claude-agent-access`: wymaganie „Narzędzia agenta są wyliczone” — wyszukiwanie w sieci i pobieranie stron przestają być
  zabronione, zapis plików dozwolony tylko w katalogu wyników; dochodzi zasada, że treść z sieci nie jest poleceniem.

## Impact

- `modules/claude-agent`: `agent/.claude/settings.json`, `agent/CLAUDE.md`, `runtime/entrypoint.sh`, testy, `README.md`.
- Bez nowych ustawień wdrożenia, sekretów, portów ani sieci — kontener już ma wyjście do internetu.
- `docs/` i `deploy/` nie mówią o sieci agenta — bez zmian.
- `design.md` krótki, bo cała treść decyzji to ryzyko wstrzyknięcia i wycieku; `review.md` po wdrożeniu i próbie.
