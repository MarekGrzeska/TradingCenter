## 1. Schemat i przechowywanie

- [x] 1.1 Migracja: `schedules` — właściciel, zespół, tryb rewizji (`pinned` / `latest`)
  i przypięta rewizja, wyrażenie cron, `next_fire_at`, `enabled`, powód wyłączenia, licznik
  kolejnych niepowodzeń, potwierdzenie pracy bez nadzoru
- [x] 1.2 Migracja: `triggers` — wyzwalacz samodzielny (własny `team_id` i tryb rewizji,
  bez wskazania na harmonogram — dwie równorzędne tabele, nie zagnieżdżenie), opis warunku
  jako wywołanie narzędzia (`tool_name`, `arguments`, `field_path`, `comparison`,
  `threshold`), trzystanowy wynik ostatniego sprawdzenia, moment ostatniego wyzwolenia,
  czas martwy i osobny interwał sprawdzania
- [x] 1.3 Migracja: `schedule_fires` — moment, źródło wyzwolenia (`schedule_id` albo
  `trigger_id`, dokładnie jedno), wynik (`started`, `skipped`, `unavailable`), powód,
  `run_id` dopuszczalnie pusty, liczba pominiętych wyzwoleń
- [x] 1.4 Więzy sprawdzające sprzeczne stany wierszy, wzorem `runs` i `run_steps` z fazy 1
  (wyzwolenie `started` bez `run_id`, `skipped`/`unavailable` bez powodu, tryb `pinned`
  bez rewizji, `schedule_fires` bez dokładnie jednego źródła)
- [x] 1.5 Zapytania w `store.py`: zapis i odczyt harmonogramów i wyzwalaczy z filtrem
  właściciela w samym zdaniu, przejęcie wyzwolenia warunkowym `UPDATE` (`claim_due_schedule`,
  `claim_trigger_for_check`), włączanie/wyłączanie, licznik niepowodzeń, historia wyzwoleń
- [x] 1.6 Testy `-m db` na powyższe (`tests/test_schedules_store.py`, 22 testów): cudzy
  harmonogram i wyzwalacz są nieodróżnialne od nieistniejących, dwa równoległe przejęcia
  tego samego wiersza (harmonogramu i wyzwalacza) dają dokładnie jednego zwycięzcę, wynik
  „nieznany" wyzwalacza to `NULL`, nie `false`

## 2. Kontrakt i trasy

- [x] 2.1 Modele wire w `contract.py` — **dopisane na końcu pliku**, w osobnej sekcji
  (`ScheduleOut`, `ScheduleIn`, `TriggerOut`, `TriggerIn`, `ScheduleFireOut`,
  `NextFiresOut`); walidacja czystego kształtu wyrażenia cron przez `croniter.is_valid`
  (dependency przeniesiona tu z grupy 3 — POST/PUT muszą wyliczyć `next_fire_at` przy
  zapisie, więc `croniter` jest potrzebny już teraz, nie dopiero w zegarze)
- [x] 2.2 `routers/schedules.py` — utworzenie, odczyt, zmiana, włączenie i wyłączenie
  harmonogramu oraz wyzwalacza, historia wyzwoleń. Sprawdzenie `unattended_ack` żyje w
  nowym `validation.check_unattended` (czyta `readOnlyHint` z ogłoszeń serwerów — patrz
  poprawka w `review.md`), sprawdzenie narzędzia wyzwalacza w nowym
  `validation.check_trigger_tool`
- [x] 2.3 Trasa podglądu najbliższych wyzwoleń, liczona przez moduł
  (`GET /schedules/{id}/next-fires`) — świeże liczenie z `cron_expression` przez
  `croniter`, nie odczyt zapisanego `next_fire_at`
- [x] 2.4 `include_router` w `app.py` — **dopisany po istniejących**
- [x] 2.5 Testy tras (`tests/test_schedules_routes.py`, 15 testów; plus 6 nowych w
  `tests/test_validation.py`), w tym odmowy: zły cron, rewizja z innego zespołu, wyzwalacz
  bez skonfigurowanego serwera narzędzi, wyzwalacz z nieogłaszaną nazwą narzędzia (przez
  prawdziwy stand-in MCP, `mcp_stand_in.serving_sync`), rewizja z narzędziem zmieniającym
  stan bez potwierdzenia (na poziomie `validation.py`, jawnym `read_only_tools`, oraz —
  po review — przez trasę, przeciw prawdziwemu serwerowi ogłaszającemu `place_order`)

## 3. Zegar i przejęcie wyzwolenia

- [x] 3.1 `scheduler/clock.py` — `Clock`, jedno zadanie `asyncio` budzące się co
  `SCHEDULER_POLL_INTERVAL_SECONDS` (tick natychmiast na starcie, potem sen), startowane
  i gaszone w `lifespan` (po `RunRegistry`, przed `tools.aclose()`), pomijane przy
  `SCHEDULER_ENABLED=false`
- [x] 3.2 Przejęcie wyzwolenia warunkowym `UPDATE … WHERE next_fire_at <= now() RETURNING`
  (`store.claim_due_schedule`, z grupy 1) i wyliczenie kolejnego momentu przez `croniter`
  (`_next_fire_and_skipped`)
- [x] 3.3 Test: dwa równoległe przejęcia tego samego wiersza dają jeden przebieg —
  własność samego `UPDATE`, dowiedziona na poziomie `store.py` w grupie 1
  (`test_two_processes_racing_the_same_due_schedule_give_exactly_one_winner`); silnik nie
  dokłada tu żadnej dodatkowej synchronizacji, więc nie ma czego drugi raz dowodzić
- [x] 3.4 Zwijanie pominiętych wyzwoleń do jednego, z zapisaną liczbą pominięć —
  `_next_fire_and_skipped` (2 testy czyste + 1 integracyjny, `tests/test_scheduler_clock.py`)
- [x] 3.5 Uruchomienie przebiegu tą samą drogą co router: `teams/runner/starter.py` —
  `start_run_on_revision` wydzielone z `routers/runs.py::start_run` (który teraz go
  wywołuje), żeby harmonogram/wyzwalacz i kliknięcie w terminalu przechodziły identyczny
  ciąg sprawdzeń
- [x] 3.6 Pominięcie przy trwającym poprzednim przebiegu tego harmonogramu, z wpisem w
  historii — `store.latest_run_status_for_schedule` (nowa funkcja: `runs` celowo nie ma
  `schedule_id`, więc „poprzedni przebieg tego harmonogramu" czyta się przez ostatni
  wiersz `schedule_fires` z `outcome='started'`)
- [x] 3.7 `croniter` w `pyproject.toml` — zrobione wcześniej, w grupie 2 (`_first_fire_at`
  w `routers/schedules.py`), bo POST/PUT harmonogramu potrzebują wyliczyć `next_fire_at`
  przy zapisie. Grupa 3 dodaje drugie miejsce użycia (przeliczenie po każdym przejęciu),
  nie samą zależność

  Dodatkowo, nieprzewidziane w tasks.md: licznik `consecutive_failures` i samoczynne
  wyłączenie (spec teams-schedules) wymagają wiedzieć, jak skończył się przebieg
  uruchomiony przez harmonogram — a to dzieje się w tle, po tym jak `tick()` już wrócił.
  `_track_run` w `clock.py` czeka na task `execute_run`, czyta `store.get_run_status`
  (nowa funkcja, bez filtra właściciela — wołający zna już `run_id`) i woła
  `reset_schedule_failures` / `increment_schedule_failures` / `disable_schedule_for_failures`.
  `Clock.tick()` zwraca listę tych tasków (w produkcji ignorowaną — `_run_forever` puszcza
  je bez czekania), żeby testy mogły `asyncio.gather` zamiast zgadywać przez `sleep`.

## 4. Wyzwalacze

- [x] 4.1 Ocena warunku przez sesję narzędzi modułu (`_evaluate_condition`), bez wywołania
  modelu — jedno wywołanie `tool_server.call`, żadnego `ModelProvider`
- [x] 4.2 Test dowodzący, że wielokrotne sprawdzenie niespełnionego warunku nie tworzy ani
  jednego wiersza `usage` (`test_a_condition_below_threshold_does_not_fire_or_cost_tokens`)
- [x] 4.3 Reakcja na zbocze `false → true` ze stanem trzymanym na wierszu wyzwalacza
  (`triggers.last_result`, `store.record_trigger_check`, z grupy 1)
- [x] 4.4 Czas martwy po wyzwoleniu, z wpisem w historii przy odrzuconym wyzwoleniu —
  `last_fired_at` przesuwa się tylko wtedy, gdy zbocze faktycznie przejdzie przez czas
  martwy, inaczej migoczący warunek nigdy by go nie wyczyścił
- [x] 4.5 Niedostępność serwera narzędzi jako trzeci stan obok prawdy i fałszu — bez
  wyzwolenia, z zapisem (`outcome='unavailable'`, `last_result=NULL`). Odmowa narzędzia
  zapisywana **tym samym** `outcome='unavailable'`, ale osobnym tekstem powodu
  („the tool refused the call: …" vs „the tool server could not be asked: …") — nie osobną
  wartością w `schedule_fires.outcome`, bo z punktu widzenia wyzwalacza obie znaczą to
  samo („nie dowiedział się, co robi rynek"), a rozróżnienie w tekście już wystarcza do
  odczytania, co dokładnie się stało. Zapisane tu jako świadome odejście od dosłownego
  brzmienia `specs/teams-triggers`, do rewizji, gdyby okazało się za słabe w praktyce.
- [x] 4.6 Sprawdzenie przy zapisie, że warunek nazywa wielkość ogłaszaną przez serwer
  narzędzi — `validation.check_trigger_tool`, zrobione w grupie 2
  (`routers/schedules.py::_check_trigger_tool`)

## 5. Bezpieczniki pracy bez nadzoru

Zrobione jako efekt uboczny grup 3–4, nie osobno — oba źródła wyzwoleń przechodzą przez
`_start_from` w `clock.py`, które woła dokładnie to samo `start_run_on_revision` co router.

- [x] 5.1 Dobowa granica kosztu zespołu sprawdzana **przed** utworzeniem przebiegu, z wpisem
  w historii zamiast odpowiedzi HTTP (`test_the_daily_cost_limit_stops_a_schedule_before_it_spends`)
- [x] 5.2 Samoczynne wyłączenie harmonogramu **i** wyzwalacza po serii nieudanych
  przebiegów, z zapisanym powodem i możliwością włączenia z powrotem (po 3/8 —
  `_track_run`, testy w obu plikach `test_scheduler_*.py`)
- [x] 5.3 Odmowa utworzenia harmonogramu lub wyzwalacza nad rewizją, której agent ma
  narzędzie zmieniające stan poza modułem, bez jawnego potwierdzenia — zrobione w grupie 2
  (`validation.check_unattended`; przy review dopięte do `readOnlyHint`, bo pusty zbiór
  nazw znaczył kontrolę, która niczego nie łapała)
- [x] 5.4 Rewizja, której nie da się uruchomić (model zniknął z katalogu), pomija
  wyzwolenie z zapisanym powodem zamiast przewracać zegar
  (`test_a_revision_naming_a_model_outside_the_catalogue_is_skipped`)

## 6. Terminal

- [x] 6.1 `pnpm contract:generate` po scaleniu kontraktu — plik generowany, nigdy ręcznie.
  Znaczna część już przyszła zmergowana: równoległy agent (PR #124) trafił na ten sam
  martwy kontrakt przy naprawie kolizji migracji i zregenerował go przy okazji; tu doszła
  tylko końcówka (`start_run_on_revision` w docstringu `start_run`). `contract.generated.ts`
  (market-data) bajt w bajt bez zmian, zgodnie z wymogiem.
- [x] 6.2 Panel harmonogramów i wyzwalaczy w zakładce `Teams` jako **nowe pliki**
  (`SchedulesPanel.tsx`, `FireHistoryList.tsx`, `scheduleDraft.ts`) — dwie linie montujące
  w `TeamsView.tsx` (nowy wariant `Open` + jego gałąź JSX), nie jedna: `TeamCatalogue.tsx`
  dostał też przycisk „Schedules" obok „Runs", bo bez wejścia z listy zespołów panel
  byłby nieosiągalny
- [x] 6.3 Najbliższe wyzwolenia brane z modułu (`GET /schedules/{id}/next-fires`, wołane
  przy otwarciu formularza edycji, nie przy każdym uderzeniu klawisza) — test przechodzi
  na wartościach, których żaden parser cron by nie wyliczył, co dowodzi, że wyświetlony
  czas pochodzi z odpowiedzi, a nie z lokalnego liczenia
- [x] 6.4 Moment wyzwolenia pokazany w UTC (`formatUtcInstant`, nowe w `ui/formatTime.ts`)
  i w czasie lokalnym (`formatInstant`, istniejące) obok siebie — „lokalny" czyta się tu
  jak wszędzie w tym terminalu: stała strefa Europe/Warsaw (`terminal-shell`,
  „Czas jest pokazywany w polskiej strefie czasowej"), nie surowa strefa przeglądarki,
  której terminal nigdzie indziej nie używa
- [x] 6.5 Historia wyzwoleń (`FireHistoryList.tsx`, wspólna dla harmonogramów i
  wyzwalaczy — `ScheduleFire` już jest wspólny), z wyzwoleniami bez przebiegu (przycisk
  „Watch" nieobecny, gdy `runId` puste) i przejściem do śladu (`onWatchRun`) tam, gdzie był
- [x] 6.6 Odmowa modułu pokazana jego słowami — `MarketDataError.kind === "refused"` ->
  `cause.message` bez przetwarzania, ta sama ścieżka co `TeamEditor.tsx`'s `save()` dla
  odmowy nienazywającej agenta. Bez wywołania `locateRefusal` z `refusal.ts` — nie ma tu
  kanwy, na której umieszczałoby się odmowę przy węźle, więc nie ma czego lokalizować
- [x] 6.7 `pnpm test` (840 przechodzi, 35 nowych: 25 `teamsApi.test.ts`, 10
  `SchedulesPanel.test.tsx`), `pnpm lint`, `pnpm typecheck`, `pnpm contract:check`, plus
  `pnpm build` (produkcyjny bundle się buduje). Bez ręcznego smoke testu w przeglądarce na
  żywym stosie — nieprzetestowane interaktywnie na prawdziwym backendzie; testy RTL
  renderują prawdziwe DOM i wchodzenia w interakcje, ale przeciwko fake API, nie
  uruchomionemu modułowi

## 7. Konfiguracja, infrastruktura i CI

- [x] 7.1 Ustawienia `SCHEDULER_*` w `config.py` — **dopisane na końcu klasy** — i w
  `.env.example` — było zrobione przy grupie 3, tylko nieodhaczone
- [x] 7.2 `SCHEDULER_ENABLED` w ustawieniach aplikacji `teams` w `infra/app-service.tf`
- [x] 7.3 `modules/teams/README.md` — harmonogramy, wyzwalacze i lever wyłączający zegar
- [x] 7.4 `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`, `uv run pyright`

  **7.2 wylądowało jako `"false"` i to jest decyzja, a nie stan przejściowy.** Warto ją
  znać z góry: `config.py` domyśla się `true`, więc *nieumieszczenie* tego ustawienia w
  mapie włączyłoby zegar — nie zostawiłoby go w spokoju.

  Powód, dla którego zostaje wyłączony, zmienił się przy review i jest teraz słabszy.
  **Był** nim zepsuty bezpiecznik: `STATE_CHANGING_TOOLS` w `validation.py` było pustym
  zbiorem nazw, więc sprawdzenie odmawiające harmonogramu nad rewizją z narzędziami
  zapisującymi chodziło, przechodziło testy i nie łapało niczego — a aplikacja ma
  `TRADING_MCP_URL`. Review to zamknęło: sprawdzenie czyta `readOnlyHint` z ogłoszeń
  serwerów i odmawia wszystkiego, czego nie potwierdzi jako odczyt. **Zostaje** to, że
  żaden harmonogram nigdy nie wyzwolił na uruchomionym stosie (8.2), więc włączenie zegara
  to decyzja operatora po tamtym przebiegu, a nie efekt uboczny poprawki. Przełączenie to
  jedna linia i `apply`; ani jeden wiersz w katalogu się przy tym nie zmienia.

  `apply` wykonany (0 dodanych, 1 zmieniony, 0 usuniętych) i sprawdzony odczytem:
  `az webapp config appsettings list` oddaje `SCHEDULER_ENABLED=false`.

  **17 sierpnia 2026 przełączone na `"true"` decyzją operatora**, bez czekania na 8.2 —
  operator zgłosił, że harmonogram `35 * * * *` zapisany na produkcji nie wyzwolił, i tym
  właśnie było: zegar nie startował. `plan` `0 to add, 4 to change, 0 to destroy` (trzy
  aplikacje to znane `allowed_applications` → `(known after apply)`), `apply` `0 added,
  1 changed, 0 destroyed`, odczyt z Azure oddaje `SCHEDULER_ENABLED=true`, `GET /health`
  na `teams` wraca **200** po restarcie. Pierwsze wyzwolenie w produkcji jest więc
  jednocześnie przebiegiem z 8.2 — bez nadzoru, z definicji.

  7.3 przy okazji odświeżyło sekcję „What", która stała na fazie 1: `config.py` ma trzy
  przełączniki trybu, nie dwa; `tools/` to rejestr dwóch serwerów, nie jedna sesja; doszły
  `scheduler/clock.py` i `routers/schedules.py`, `runner/trading.py` obok `cost.py`, a lista
  migracji kończyła się na `0003` zamiast na `0006`. Nowa sekcja „Schedules and triggers"
  niesie oba mechanizmy, trzy bezpieczniki pracy bez nadzoru, zwijanie pominiętych wyzwoleń
  do jednego (`_next_fire_and_skipped`, sprawdzone w kodzie, nie założone) i lewarek — oraz
  wyżej opisaną dziurę, wprost, jako rzecz do zamknięcia najpierw.

  7.4: `ruff` czysto, `pyright` 0 błędów, `pytest` **337 passed**, `pytest -m db`
  **159 passed** przeciw prawdziwemu PostgreSQL-owi w kontenerze jednorazowym.

## 8. Domknięcie

- [x] 8.1 Uzgodnienie z fazą 2 — zrobione, tyle że w drugą stronę: to faza 2 scaliła się
  jako druga, więc jej `0004_trades` została przenumerowana na `0006` nad
  `0005_schedules_and_triggers`. Przy okazji zegar przeszedł na `ToolServerRegistry`, a
  narzędzie wyzwalacza jest rozwiązywane przez serwer, który je ogłasza, zamiast przez
  jedyny, jaki wcześniej istniał.
- [x] 8.2 Przebieg od końca do końca na uruchomionym stosie: harmonogram co kilka minut,
  jedno wyzwolenie pominięte celowo (drugi przebieg w trakcie), jedno wyzwolenie warunkowe

  **Odhaczone jako świadoma decyzja operatora, nie jako wykonane.** Ręczny przebieg na
  żywym stosie zostaje na później i nie blokuje domknięcia fazy. Co go zastępuje: te same
  trzy sytuacje są dowiedzione testami `-m db` przeciw prawdziwemu PostgreSQL-owi
  (`test_scheduler_clock.py`, `test_scheduler_triggers.py`) — wyzwolenie uruchamiające
  przebieg, wyzwolenie pominięte przy trwającym poprzednim przebiegu, wyzwolenie warunkowe
  na zboczu przez prawdziwy serwer MCP. Czego nie zastępują: `SCHEDULER_ENABLED` na
  produkcji i zegar budzący się sam w procesie App Service. Do zrobienia, zanim 7.2
  przejdzie na `true` — patrz „Gaps" w `review.md`.

  **Kolejność wyszła odwrotna: 7.2 przeszło na `true` 17 sierpnia 2026, zanim ten przebieg
  się odbył.** Zapisane tak, jak było, a nie odhaczone wstecz — pierwsze wyzwolenie na
  produkcji jest tym przebiegiem i nikt przy nim nie stoi. Co przy tej okazji wyszło i
  zostaje otwarte: `check_unattended` jest wołane **wyłącznie** z `routers/schedules.py`,
  czyli przy zapisie. Ścieżka wyzwolenia (`scheduler/clock.py` → `runner/`) nie pyta o nie
  ani razu, a `_resolve_revision` przy `revision_mode='latest'` bierze rewizję **z chwili
  wyzwolenia**. Harmonogram zapisany nad zespołem bez narzędzi zapisujących — więc z
  `unattended_ack = false`, całkiem legalnie — dalej wyzwala sam po tym, jak operator doda
  do zespołu `place_order`. Zabezpieczenie nie jest zepsute; jest w jednym miejscu, a
  potrzebne w dwóch. Harmonogram `pinned` tego nie ma, bo jego rewizja jest ustalona.
- [x] 8.3 `review.md`
