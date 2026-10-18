## Verdict

Platforma strategii zniknęła z działającego systemu w dwóch wydaniach: A (#305, kod, terminal, dokumentacja; wdrożone
18.10.2026 13:00 UTC) i B (#306, baza `strategy` i rola usunięte przy deployu). Wydanie B najpierw się nie wdrożyło —
serwer sprawdzał nowy `.env` starą listą `env.required` — co naprawił #307; produkcja przez cały czas działała na
poprzednich obrazach. Świadomie niekompletne: wiersz `strategy.setup` w `purposes` telegrama zostaje (cele są
obserwowane, brama nie ma ścieżki ich usuwania), lokalny kontener deweloperski zachowuje starą bazę do
`docker compose down -v`, a 4.5 (nocny zrzut bez `strategy`) przyjęto z góry decyzją operatora.

## Verified

- `modules/workbench`, 18.10.2026 na `main` po #309: `uv run pytest -q -m "not db and not live"` — 1466 passed,
  1257 deselected; `ruff check .` — All checks passed; `pyright` — 0 errors, 0 warnings. Testy `-m db` przeszły w CI
  #305.
- `uv run pytest -q` w `scripts/` — 234 passed, 1 skipped (po #306 i po #307).
- `openspec validate remove-strategy-platform --strict` — valid (przed archiwizacją).
- Produkcja po #307 (`.local/vps/vps.sh`): pięć kontenerów `healthy`; `pg_database` i `pg_roles` bez `strategy`;
  `.env` bez `STRATEGY_*`; workbench bez `error`/`traceback` w logu z 10 minut; `api`, `gateway`, `terminal`, `pocket`
  odpowiadają 200 z zewnątrz.
- Obraz workbencha `cd85148` nie zawiera pakietu `strategy` (`importlib.util.find_spec("strategy") is None`). Kod 404
  na `/strategy` nie dał się zmierzyć: z zewnątrz drzwi odpowiadają 401 przed routerem, a od środka kluczem odmawia
  rekord dostępu pakietu, także 401.
- Baza `teams` na produkcji: żadna `team_revisions.definition` i żaden `triggers.tool_name` nie nazywa
  `list_strategies`, `pending_setups`, `recent_decisions`, `last_decision`.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Wysokie | `.github/workflows/deploy-vps.yml:241` (krok „Send the environment”) | `ssh vps env` szedł przed `ssh vps sync`, więc serwer sprawdzał nowy `.env` listą `env.required` poprzedniego wydania. Usunięcie nazwy (`STRATEGY_DB_PASSWORD`) zatrzymywało każdy deploy: `deploy: refusing to deploy; missing from .env: STRATEGY_DB_PASSWORD`. Nic nie dotarło do kontenerów. | FIXED w #307 (`6a6a905`): pliki przed środowiskiem |
| Średnie | `deploy/ansible/site.yml:167-168` | `backup.sh` i `backup-check.sh` trafiają na serwer tylko przez Ansible; `deploy.sh sync` ich nie niesie. Po #306 serwer dalej zrzucałby i sprawdzał `strategy`, której już nie ma. | Obejście: oba zainstalowane ręcznie 18.10.2026 (`install -o deploy -g deploy -m 0750`), treść równa repo. Przyczyna zostaje: następna zmiana tych skryptów znów wymaga Ansible albo ręcznej instalacji |
| Niskie | `CLAUDE.md:151` | Lista kluczy blokad migracji wymieniała 8080 (platformy, już nieistniejącej), a pomijała 8110 (YouTube). | FIXED w PR z tym review |
| Niskie | `modules/workbench/README.md:65` | „the way the platform reaches the candle archive” — porównanie do drogi, która zniknęła razem z `archive_client.py`. | FIXED w PR z tym review |

Diff wydania A poza tym bez znalezisk: `workbench/app.py` zdejmuje montowanie, źródło lokalne i klienta archiwum
razem; `config.py` nie zostawia pola, które ktoś by czytał; `tests/teams/test_scheduler_triggers.py` zachowuje test
drogi „narzędzie po nazwie” na neutralnym narzędziu. `retire()` w `ensure-databases.sh` jest idempotentne
(`IF EXISTS`) i rusza po wszystkich `ensure`, więc nie blokuje baz, które zostają.

## Spec coverage

Zmiana usuwa wymagania, więc dowodem jest nieobecność kodu, a nie test zachowania.

| Requirement / Scenario | Proven by |
|---|---|
| `strategy-alerts`, `-backtest`, `-catalogue`, `-configurator`, `-database-connection`, `-liveness`, `-runtime`, `-tools` — wszystkie REMOVED (33 wymagania) | `tests/test_layering.py::PACKAGES` bez `strategy` (test generuje mapę zakazanych importów z tej listy); `strategy/`, `tests/strategy/`, `migrations/strategy/` usunięte w `8dae554`; obraz produkcji bez pakietu (Verified) |
| `strategy-database-connection` — baza i rola | Produkcja: `pg_database`/`pg_roles` bez `strategy` po #306/#307 (Verified); `tests/test_database_server_mode.py::DATABASES` bez `strategy` |
| `terminal-strategy-configurator` — 3 × REMOVED | `src/strategy/**` i `contract.strategy.generated.ts` usunięte; `contract:check` zielony w CI #305 |
| `teams-triggers` · REMOVED „Decyzja platformy strategii jest źródłem warunku” — migracja: wyzwalacz na nieogłaszanym narzędziu nie budzi zespołu | `tests/teams/test_scheduler_triggers.py::test_a_trigger_with_no_tool_server_is_recorded_as_unavailable_not_false` — ta sama gałąź `server is None` w `teams/scheduler/clock.py` |
| `telegram-gateway-delivery` · MODIFIED „Wysłanie jest jednym aktem i nie zostawia śladu” · Wiadomość dochodzi | `tests/telegram/test_rest.py::test_a_message_answers_with_the_identifier_telegram_gave_it` |
| `telegram-gateway-delivery` · MODIFIED · Nie ma czego odczytać | `tests/telegram/test_sending.py::test_nothing_is_recorded_about_what_was_sent` — tylko połowa: brak zapisu; że żadna trasa ani narzędzie o to nie pyta, nie sprawdza żaden test |

## Gaps

- „Nie ma czego odczytać” (`telegram-gateway-delivery`): nieobecność trasy i narzędzia odczytu wysłanych wiadomości
  nie ma testu. Scenariusz istniał przed tą zmianą, która zmieniła tylko opis wymagania.
- 404 na `/strategy` nie zmierzone kodem HTTP (Verified mówi dlaczego); dowodem jest obraz.
- 4.5: nocny zrzut 19.10.2026 bez `strategy` — przyjęty z góry; jeśli nie przejdzie, poprawka osobno.
- Skrypty instalowane tylko przez Ansible (Findings, średnie) — przyczyna nienaprawiona.
