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

- [ ] 2.1 Modele wire w `contract.py` — **dopisane na końcu pliku**, w osobnej sekcji
  (`ScheduleOut`, `ScheduleIn`, `TriggerOut`, `TriggerIn`, `ScheduleFireOut`,
  `NextFiresOut`); walidacja czystego kształtu wyrażenia cron tam, gdzie nie wymaga bazy
- [ ] 2.2 `routers/schedules.py` — utworzenie, odczyt, zmiana, włączenie i wyłączenie
  harmonogramu oraz wyzwalacza, historia wyzwoleń
- [ ] 2.3 Trasa podglądu najbliższych wyzwoleń, liczona przez moduł
- [ ] 2.4 `include_router` w `app.py` — **dopisany po istniejących**
- [ ] 2.5 Testy tras, w tym odmowy: zły cron, nieznana wielkość warunku, brak serwera narzędzi

## 3. Zegar i przejęcie wyzwolenia

- [ ] 3.1 `scheduler/` — zadanie budzące się co ustawiony interwał, startowane i gaszone
  w `lifespan`, wyłączane ustawieniem `SCHEDULER_ENABLED`
- [ ] 3.2 Przejęcie wyzwolenia warunkowym `UPDATE … WHERE next_fire_at <= now() RETURNING`
  i wyliczenie kolejnego momentu przez `croniter`
- [ ] 3.3 Test: dwa równoległe przejęcia tego samego wiersza dają jeden przebieg
- [ ] 3.4 Zwijanie pominiętych wyzwoleń do jednego, z zapisaną liczbą pominięć
- [ ] 3.5 Uruchomienie przebiegu tą samą drogą co router: rozwiązanie rewizji zgodnie z trybem,
  właściciel z harmonogramu, rejestracja w `RunRegistry`
- [ ] 3.6 Pominięcie przy trwającym poprzednim przebiegu tego harmonogramu, z wpisem w historii
- [ ] 3.7 `croniter` w `pyproject.toml`, schowany za własną funkcją rozwijania

## 4. Wyzwalacze

- [ ] 4.1 Ocena warunku przez sesję narzędzi modułu, bez wywołania modelu
- [ ] 4.2 Test dowodzący, że wielokrotne sprawdzenie niespełnionego warunku nie tworzy ani
  jednego wiersza `usage`
- [ ] 4.3 Reakcja na zbocze `false → true` ze stanem trzymanym na wierszu wyzwalacza
- [ ] 4.4 Czas martwy po wyzwoleniu, z wpisem w historii przy odrzuconym wyzwoleniu
- [ ] 4.5 Niedostępność serwera narzędzi jako trzeci stan obok prawdy i fałszu — bez
  wyzwolenia, z zapisem; odmowa narzędzia zapisywana odrębnie
- [ ] 4.6 Sprawdzenie przy zapisie, że warunek nazywa wielkość ogłaszaną przez serwer narzędzi

## 5. Bezpieczniki pracy bez nadzoru

- [ ] 5.1 Dobowa granica kosztu zespołu sprawdzana **przed** utworzeniem przebiegu, z wpisem
  w historii zamiast odpowiedzi HTTP
- [ ] 5.2 Samoczynne wyłączenie harmonogramu po serii nieudanych przebiegów, z zapisanym
  powodem i możliwością włączenia z powrotem
- [ ] 5.3 Odmowa utworzenia harmonogramu lub wyzwalacza nad rewizją, której agent ma narzędzie
  zmieniające stan poza modułem, bez jawnego potwierdzenia — wraz z testem, który dziś
  przechodzi w próżni (żadne narzędzie takie nie jest)
- [ ] 5.4 Rewizja, której nie da się uruchomić (model zniknął z katalogu), pomija wyzwolenie
  z zapisanym powodem zamiast przewracać zegar

## 6. Terminal

- [ ] 6.1 `pnpm contract:generate` po scaleniu kontraktu — plik generowany, nigdy ręcznie
- [ ] 6.2 Panel harmonogramów i wyzwalaczy w zakładce `Teams` jako **nowe pliki**; jedna linia
  montująca w `TeamsView.tsx`
- [ ] 6.3 Najbliższe wyzwolenia brane z modułu; test, że terminal nie nosi własnego parsera
  wyrażeń czasowych
- [ ] 6.4 Moment wyzwolenia pokazany w UTC i w czasie lokalnym obok siebie
- [ ] 6.5 Historia wyzwoleń, z wyzwoleniami bez przebiegu i przejściem do śladu tam, gdzie
  przebieg był
- [ ] 6.6 Odmowa modułu pokazana jego słowami, ścieżką `refusal.ts` z fazy 1
- [ ] 6.7 `pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm contract:check`

## 7. Konfiguracja, infrastruktura i CI

- [ ] 7.1 Ustawienia `SCHEDULER_*` w `config.py` — **dopisane na końcu klasy** — i w
  `.env.example`
- [ ] 7.2 `SCHEDULER_ENABLED` w ustawieniach aplikacji `teams` w `infra/app-service.tf`
- [ ] 7.3 `modules/teams/README.md` — harmonogramy, wyzwalacze i lever wyłączający zegar
- [ ] 7.4 `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`, `uv run pyright`

## 8. Domknięcie

- [ ] 8.1 Uzgodnienie z fazą 2, jeśli scala się jako druga: przenumerowanie rewizji Alembica
  i `down_revision`, ponowne `pnpm contract:generate`
- [ ] 8.2 Przebieg od końca do końca na uruchomionym stosie: harmonogram co kilka minut,
  jedno wyzwolenie pominięte celowo (drugi przebieg w trakcie), jedno wyzwolenie warunkowe
- [ ] 8.3 `review.md`
