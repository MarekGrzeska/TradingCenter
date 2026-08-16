## Verdict

Oba moduły migrują własną bazę przy starcie, pod blokadą doradczą, własną tożsamością —
i jedno wdrożenie z celowo zepsutą migracją potwierdziło, że nieudana migracja daje
**czerwone** wdrożenie tam, gdzie 16 sierpnia dawała zielone nad ciemnym modułem.

Jedno zdanie `design.md` okazało się nieprawdą i jest poniżej opisane, a nie zamiecione:
**poprzednia wersja nie serwuje dalej**. App Service bez slotów restartuje kontener
w miejscu, więc nie ma czego zostawić — moduł odpowiadał `503` przez dziewięć minut.
Wymaganie specyfikacji przetrwało (nowa wersja *nie zaczęła* obsługiwać ruchu, wdrożenie
*skończyło się* niepowodzeniem), złagodzenie ryzyka w projekcie nie.

Czego tu nie ma i nie jest przeoczeniem: testu jednostkowego na „żądanie w trakcie
migracji" po stronie agenta oraz na własność tworzonych obiektów. Pierwsze jest w
`market-data` jako test kolejności, drugie sprawdzone na produkcji zapytaniem kontrolnym.

## Verified

Uruchomione, z wynikiem:

| Komenda | Wynik |
|---|---|
| `uv run pytest` (agent) | `323 passed` |
| `uv run pytest -m db` (agent) | `219 passed, 104 deselected` |
| `uv run pytest` (market-data) | `1029 passed, 7 skipped` |
| `uv run ruff check .` · `uv run pyright` (oba) | `All checks passed` · `0 errors` |
| `terraform fmt -check -recursive` · `validate` · `plan` | czysto · `Success` · `0 to add, 3 to change, 0 to destroy`, bez `azuread_*` |
| `openspec validate <change> --type change --strict` | valid |

Na produkcji:

- `scripts/grant-schema-ownership.sql` na `agent` i `market_data` — obie kontrolki
  zwróciły **0 wierszy**;
- wdrożenie agenta (PR #99) — smoke check `attempt 1: … health=200`;
- wdrożenie `market-data` (PR #100) — smoke check `attempt 1: HTTP 404` z `/ws/candles`,
  czyli proces odpowiada;
- po całości: `agent /health 200`, `market-data /ping 200`, `alembic_version = 0009`.

**Zadanie 6.4, przebieg z pomiarem.** PR #101 wniósł migrację `0010`, która rzuca pierwszą
instrukcją. Kolejno:

| Czas (UTC) | Co |
|---|---|
| — | job `agent` w CI **czerwony** — pierwsza linia obrony zadziałała, zanim cokolwiek poszło na produkcję |
| 13:10:33 | merge, start `deploy-agent` |
| 13:12 | `/health` przestaje odpowiadać (`000`, potem `503`) |
| 13:12–13:20 | `503` nieprzerwanie; smoke check ponawia |
| 13:20 | wdrożenie kończy się **niepowodzeniem** |
| 13:21 | ręczne cofnięcie obrazu na `78568c4` — `200` po **~40 sekundach** |
| 13:25 | PR #102 (revert) wdrożony, smoke check `attempt 1: … health=200` |

`alembic_version` przez cały czas na `0009` — migracja rzuciła przed jakimkolwiek DDL,
więc schemat produkcyjny nie został tknięty. Przestój: **dziewięć minut**.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Wysoka | `design.md`, „Risks / Trade-offs" | „Poprzedni kontener serwuje dalej, dopóki nowy nie przejdzie probe'a, więc produkcja nie ciemnieje" jest nieprawdą. App Service bez slotów wdrożeniowych podmienia obraz i restartuje kontener w miejscu — nie ma poprzedniej wersji, która by serwowała. Zmierzone: 9 minut `503`. Konsekwencja: nieudana migracja **jest** przestojem, a nie tylko czerwonym jobem. | FIXED w tym przebiegu — akapit poprawiony i uzupełniony o zmierzoną dźwignię ratunkową |
| Średnia | `scripts/grant-schema-ownership.sql:79` | Filtr `pg_depend` wykluczał tylko `deptype = 'a'` (kolumna `serial`). Sekwencja kolumny **identity** wisi na `'i'`, więc pierwszy przebieg padł na `cannot change owner of sequence "prompt_revisions_id_seq"`. Transakcja wycofała się w całości — nic nie zostało w połowie. | FIXED — `5156efd` |
| Średnia | `scripts/…sql:21`, `design.md`, `tasks.md` | Baza `market-data` nazwana `tradingcenter`, a tak nazywa się **serwer**. Objawia się `FATAL: database "tradingcenter" does not exist`, więc jest głośne, ale było w trzech miejscach naraz. | FIXED — `5156efd` |
| Średnia | `market_data/config.py:82` | Kres blokady 1800 s równał się sufitowi `WEBSITES_CONTAINER_START_TIME_LIMIT`, więc platforma mogła poddać się pierwsza — czyli zrestartować kontener i zacząć tę samą migrację od nowa, bez ani jednego zdania dlaczego. Obniżone do 1500 s. | FIXED — w implementacji, `720d2db` |
| Niska | `scripts/…sql:45` | `GRANT :"role" TO current_user` okazał się na tym serwerze zbędny — administrator był już członkiem obu ról aplikacji (`already been granted membership`). Zostawiony: na czystym serwerze nie będzie, a jest idempotentny. | Świadomie zostawione |
| Niska | operacyjne | Plik stdout kontenera za bieżący dzień nie pojawia się w `az webapp log download`. Linii `bringing the database up to…` nie dało się pokazać ani rano przy diagnozie awarii, ani po wdrożeniu. Dowodem pozostaje odpowiedź `/health`, która jest mocniejsza, ale przy diagnozie *nieudanego* startu tego zamiennika nie ma. | Otwarte, poza zakresem |

Nic więcej z przeglądu diffu nie przeżyło weryfikacji.

## Spec coverage

`agent-database-connection` — testy w `modules/agent/tests/`:

| Requirement / Scenario | Proven by |
|---|---|
| **Moduł sam doprowadza bazę do rewizji, dla której powstał** | |
| Wdrożenie niosące nową rewizję | `test_migrate.py::test_an_empty_database_is_brought_to_head` |
| Baza już na właściwej rewizji | `test_migrate.py::test_a_database_already_at_head_is_left_alone` |
| Żądanie w trakcie migracji | **GAP** — patrz „Gaps" |
| **Migruje dokładnie jeden proces naraz** | |
| Dwie instancje startują naraz | `test_migrate.py::test_only_one_of_two_processes_migrates` |
| Blokada nie zwalnia się w wyznaczonym czasie | `test_migrate.py::test_a_lock_that_never_frees_up_refuses_rather_than_waits_forever` |
| Migracja kończy się błędem | `test_migrate.py::test_the_lock_is_released_when_the_body_raises` |
| **Moduł jest właścicielem tego, co jego migracje tworzą** | |
| Nowa tabela jest od razu użyteczna | **GAP** w testach; na produkcji kontrolka `grant-schema-ownership.sql` (0 wierszy) |
| Migracja nie sięga po szersze uprawnienia | **GAP** w testach; wynika z `migrations/env.py`, który buduje silnik z `Settings()` modułu |
| **Moduł, który nie zdołał zmigrować, nie udaje że działa** | |
| Migracja nie przechodzi | **GAP** w testach; zadanie 6.4 na produkcji (PR #101) |
| Baza wyprzedza obraz | `test_schema_version.py::test_a_database_ahead_of_the_image_refuses_too` |
| Wdrożenie z nieudaną migracją nie wypuszcza wersji | Zadanie 6.4 — wdrożenie czerwone, nowa wersja nie obsłużyła ruchu |

`market-data-database-connection` — testy w `modules/market-data/tests/`, bliźniaczo, plus
scenariusze własne:

| Requirement / Scenario | Proven by |
|---|---|
| Wdrożenie niosące nową rewizję | `test_migrate.py::test_an_empty_database_is_brought_to_head` |
| Baza już na właściwej rewizji | `test_migrate.py::test_a_database_already_at_head_is_left_alone` |
| Żądanie w trakcie migracji | `test_migrate.py::test_nothing_is_collected_before_the_migration_finishes` (kolejność w `lifespan`) |
| Zbieranie nie rusza przed migracją | `test_migrate.py::test_nothing_is_collected_before_the_migration_finishes` |
| Dwie instancje startują naraz | `test_migrate.py::test_only_one_of_two_processes_migrates` |
| Migracja dłuższa niż start procesu | `test_migrate.py::test_the_wait_outlasts_a_long_migration` — **częściowo**: sprawdza nastawę, nie zachowanie |
| Blokada nie zwalnia się w wyznaczonym czasie | `test_migrate.py::test_a_lock_that_never_frees_up_refuses_rather_than_waits_forever` |
| Migracja kończy się błędem | `test_migrate.py::test_the_lock_is_released_when_the_body_raises` |
| Nowa tabela jest od razu użyteczna | **GAP** w testach; kontrolka na produkcji |
| Migracja nie sięga po szersze uprawnienia | **GAP** w testach |
| Migracja nie przechodzi | **GAP** w testach; 6.4 wykonane na agencie, mechanizm bliźniaczy |
| Baza wyprzedza obraz | `test_schema_version.py::test_a_database_ahead_of_the_image_refuses_too` |

## Gaps

- **„Żądanie w trakcie migracji" po stronie agenta.** `market-data` ma test kolejności
  w `lifespan`, agent nie — jego odpowiednikiem byłoby to samo wywołanie z podstawionym
  `migrate.run`. Nie napisane, bo agent nie ma nic, co odpowiadałoby `ingest.start()`,
  a samo „nie obsługuje ruchu przed `yield`" wynika z tego, jak działa `lifespan`, a nie
  z tego kodu.
- **Własność tworzonych obiektów** nie ma testu w żadnym module. Testowy kontener łączy
  się jednym użytkownikiem, który jest właścicielem wszystkiego, więc test przeszedłby
  niezależnie od tego, czy mechanizm działa — czyli nie dowodziłby niczego. Dowodem jest
  kontrolka produkcyjna.
- **„Migracja nie przechodzi" nie ma testu jednostkowego.** Sprawdzone raz, na produkcji,
  zadaniem 6.4. Test dałoby się napisać, podstawiając `migrate.run` rzucający wyjątek
  i sprawdzając, że `lifespan` się nie kończy — wart dopisania, gdy ktoś będzie tu wracał.
- **„Migracja dłuższa niż start procesu"** jest sprawdzona jako nastawa (`>= 900 s`), nie
  jako zachowanie. Zachowania nie da się sprawdzić bez migracji, która naprawdę trwa
  kwadrans.
