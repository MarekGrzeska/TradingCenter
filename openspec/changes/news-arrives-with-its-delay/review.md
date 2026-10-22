## Verdict

Zbiór newsów stoi w całości: 15 feedów RSS z własnymi odstępami, opóźnienie liczone w dwóch granicach przy
każdym newsie i per źródło, retencja 28 dni z przyciskiem „zachowaj”, trzy trasy kontraktu, zakładka News
w terminalu i czwarty ekran w pocket. **Nie zostało zweryfikowane na produkcji**: zadanie 6.4 (15 źródeł
z udanym pobraniem, heartbeat `news` w `/social/health`) jest czynnością po wdrożeniu i zostaje
niezaznaczone celowo, a nie z zapomnienia.

Dwie rzeczy, których późniejszy czytelnik nie powinien wziąć za przeoczenie. **`PUT /news/keep` jest pierwszą
trasą zapisującą w `/social`** i jest to wyjątek nazwany w `social-data-api`, a nie rozszerzenie zasady „kontrakt
wyłącznie czyta”. I **Al Jazeera jest czytana przez swój opublikowany RSS mimo regulaminu zakazującego
automatycznego zbierania** — decyzja operatora z 29 września; wyłączenie to usunięcie jednego wpisu z
`news/sources.py`.

## Verified

Uruchomione na tej gałęzi, nie deklarowane. Docker był potrzebny i został uruchomiony na czas testów.

| Co | Wynik |
|---|---|
| `modules/workbench`: `uv run pytest -q` (z testami `db` na testcontainers) | **2669 passed, 11 skipped** w 6 min 22 s (po dopisaniu treści i okien w minutach) |
| `modules/workbench`: `uv run pytest tests/social/test_news_*.py` | **74 testy nowe**, wszystkie zielone |
| `modules/workbench`: `uv run ruff check .` · `uv run pyright` | czysto · 0 błędów |
| `modules/terminal`: vitest · `tsc -b --noEmit` · `eslint .` · `node scripts/contract.mjs check` | **858 passed (70 plików)** · czysto · czysto · „Every contract is up to date” |
| `modules/pocket`: vitest · `tsc -b --noEmit` · `eslint .` · `node scripts/contract.mjs check` | **105 passed (19 plików)** · czysto · czysto · „The contract is up to date” |
| `scripts`: `uv run pytest -q` | **149 passed, 27 skipped** |
| `openspec validate news-arrives-with-its-delay --strict` | valid |
| `db-cost-check` (task 1.4): jednorazowy Postgres 17, 100 tys. wierszy `news_items`, 15 źródeł, `--cpus=1 --memory=2g` | wszystkie zapytania idą po indeksach; okno 6 h **19 buforów / 0,26 ms**, czyszczenie **3 bufory**; rachunek źródeł po przeniesieniu do SQL (`percentile_cont`, 3,6 tys. wierszy z doby) **194 bufory / 6,3 ms**; klasa **C2** |

`pnpm` nie działa na tej maszynie pod Node 25, więc terminal i pocket były uruchamiane binarkami z
`node_modules/.bin` i `node scripts/contract.mjs`, czyli tym samym, co skrypty `pnpm` wołają.
Testy `live` nie istnieją dla tej zmiany: feedy zostały zmierzone ręcznie 29 września (`docs/zrodla-newsow.html`),
a parser jest testowany na zapisanych dokumentach.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Poważne | `social_data/routers/news.py` (pierwsza wersja trasy `keep`) | Para źródło–identyfikator szła w ścieżce jako `{external_id:path}`, a rekord dostępu (`tc_runtime/caller_access.py:92`) dopasowuje każdy `{placeholder}` jako `[^/]+`. Identyfikator z feedu to zwykle URL, więc **„zachowaj” dostawałoby 403 dla większości newsów**, i to po zdaniu wszystkich testów, bo żaden nie użyłby identyfikatora ze slashem. | **FIXED** w `811f011` — para w ciele `PUT /news/keep`; test `test_news_api.py::test_keeping_a_headline_whose_identifier_is_a_url_reaches_it_and_the_kept_list_finds_it` |
| Średnie | `terminal/src/news/NewsCard.tsx` | Po zdjęciu znacznika ze starego newsa karta pokazywała **datę z przeszłości** („zniknie 1.09”), a spec `terminal-news` każe powiedzieć „przy najbliższym czyszczeniu”. Pocket robił to dobrze; wyszło przy przejściu po scenariuszach. | **FIXED** w `8ae00b0` — `expiryText`; `delay.test.ts::expiryText` |
| Drobne | `tests/social/test_api.py` | Istniejący test „kontrakt nie publikuje trasy piszącej” kodował starą regułę i czerwieniał na jedynym dozwolonym wyjątku. | **FIXED** w `811f011` — test wymaga dokładnie jednego zapisu, `PUT /news/keep` |
| Drobne | `news/fetch.py:MAX_DOCUMENT_BYTES` | Rozmiar sprawdzany po pobraniu całego ciała (`response.content`), więc feed serwujący setki MB zająłby pamięć przed odmową. | **FIXED** w `2e0e6da` — `fetch.py` czyta strumieniowo i odmawia po przekroczeniu limitu w trakcie pobierania; `test_news_fetch.py::test_every_way_a_feed_can_fail_is_its_own_kind` (przypadek 6 MB) |
| Drobne | `news/feed.py:11` | `from ..providers.truth_social import clean` — pakiet newsów zależy od funkcji pomocniczej dostawcy postów. Test layeringu przechodzi (to ten sam pakiet), ale to sprzężenie bez powodu. | **FIXED** w `2e0e6da` — `clean` mieszka w `social_data/text.py`; `test_truth_social.py` dalej ją importuje z dostawcy i przechodzi |
| Drobne | `news/views.py:sources_state` | Rachunek źródeł liczył percentyle w Pythonie po wszystkich wierszach doby; przy dziesięciokrotnie większej liczbie feedów to 36 tys. wierszy przez sieć co 60 s. | **FIXED** w `2e0e6da` — `store.source_figures` liczy `percentile_cont` w SQL; definicja jest zapisana dwa razy (SQL i `latency.delay`), więc trzyma je razem `test_news_store.py::test_a_sources_day_is_the_same_definition_as_a_headlines_delay` na tych samych nagłówkach, z przypadkami brzegowymi |

## Spec coverage

Ścieżki skrócone: `w/` = `modules/workbench/tests/social/`, `t/` = `modules/terminal/src/news/`.

### social-data-news-ingest

| Requirement / Scenario | Proven by |
|---|---|
| Newsy zbiera pętla, nie odczyt → Odczyt nie dokłada newsów | `w/test_news_api.py::test_reading_the_news_adds_nothing_to_the_archive` |
| → Pętla pracuje bez pytania | `w/test_news_collector.py::test_the_loop_collects_by_itself_without_anybody_asking` |
| Źródło jest wpisem → Dołożenie feedu | `w/test_news_collector.py::test_a_feed_that_refuses_costs_only_itself` (dwa zadeklarowane źródła, żadnej różnicy w kodzie) |
| Tożsamość newsa → News wraca w kolejnym pobraniu | `w/test_news_store.py::test_a_headline_seen_again_is_stored_once_and_keeps_its_first_moment` |
| → Ten sam news w dwóch źródłach | `w/test_news_store.py::test_two_feeds_may_carry_the_same_identifier` |
| Zapisywane jest wszystko → News spoza tematu | `w/test_news_collector.py::test_a_feed_that_refuses_costs_only_itself` (zapisuje wszystkie 3 pozycje fixture, w tym nietematyczne), `w/test_news_feed.py` |
| → Lead ze znacznikami | `w/test_news_feed.py::test_an_rss_item_becomes_text_with_entities_resolved_and_a_utc_time` |
| Feed, który nie odpowiada → Feed nie odpowiada | `w/test_news_collector.py::test_a_feed_that_refuses_costs_only_itself`, `w/test_news_store.py::test_a_failure_moves_nothing_forward` |
| → Feed bez zmian | `w/test_news_collector.py::test_not_modified_is_a_successful_fetch` |
| → Feed zmienił kształt | `w/test_news_fetch.py::test_every_way_a_feed_can_fail_is_its_own_kind` (`UNREADABLE`) |
| Uprzejmie → Źródło podało znacznik wersji | `w/test_news_fetch.py::test_an_answer_with_items_is_read_and_its_validators_are_sent_next_time` |
| → Źródło odmawia | `w/test_news_fetch.py::test_a_refusal_is_one_request_and_never_a_second_try_as_somebody_else`, `w/test_news_collector.py::test_a_feed_is_not_asked_again_before_its_interval` |
| Nie sięga wstecz → Pierwsze pobranie źródła | `w/test_news_store.py::test_the_first_fetch_of_a_feed_finds_headlines_there_and_the_next_measures_them` |
| Retencja → News starszy niż retencja / zachowany / znacznik zdjęty | `w/test_news_store.py::test_the_sweep_removes_the_old_and_spares_the_kept`, `w/test_news_collector.py::test_the_sweep_lets_old_headlines_go_but_not_kept_ones` |
| → Prośba o skasowanie | `w/test_api.py::test_the_contract_publishes_no_route_that_writes_but_the_keep_flag` |

### social-data-news-latency

| Requirement / Scenario | Proven by |
|---|---|
| Trzy momenty → News z kompletem | `w/test_news_api.py::test_a_headline_reaches_the_wire_with_both_bounds_of_its_delay` |
| Granice → Feed spóźniony / natychmiastowy | `w/test_news_latency.py::test_a_feed_that_was_late_has_a_lower_bound_above_zero`, `::test_a_feed_that_published_between_our_two_fetches_has_a_lower_bound_of_zero` |
| → Różnica granic nie przekracza odstępu między pobraniami | `w/test_news_latency.py::test_the_two_bounds_differ_by_no_more_than_the_gap_between_our_two_fetches` (20 kombinacji) |
| Niezmierzalne → Czas z przyszłości / News zastany | `w/test_news_latency.py::test_what_cannot_be_measured_says_why_and_is_never_zero`, `w/test_news_store.py::test_a_sources_day_is_the_same_definition_as_a_headlines_delay` (niezmierzalne liczone, poza statystykami) |
| Rachunek źródła → Porównanie dwóch źródeł | `w/test_news_api.py::test_the_sources_lists_every_declared_feed_including_one_that_never_answered` |
| → Źródło dopiero dodane | `w/test_news_store.py::test_a_source_with_nothing_measured_has_empty_figures_and_the_count_of_what_it_could_not` |
| Stojące źródło → Odmawia od godziny | `w/test_news_status.py::test_a_feed_whose_latest_fetch_failed_is_failing_until_it_has_been_silent_for_six_intervals`, `w/test_news_api.py::test_a_feed_whose_latest_fetch_failed_is_named_failing_with_its_reason` |
| → Ciche, ale żywe | `w/test_news_status.py::test_a_feed_answering_within_its_intervals_is_ok_even_if_nothing_new_was_published` |

### social-data-news-api

| Requirement / Scenario | Proven by |
|---|---|
| Okno i zawężenia → Newsy o Iranie z dwóch źródeł | `w/test_news_store.py::test_a_window_narrows_by_source_and_by_text_ignoring_case` |
| → Okno bez sensu | `w/test_news_api.py::test_a_window_that_ends_before_it_starts_is_refused_with_a_reason` |
| Porządek i obcięcie → Okno większe niż limit | `w/test_news_api.py::test_a_window_bigger_than_the_limit_says_it_is_cut_and_keeps_the_newest` |
| Pola zawsze obecne → News bez czasu publikacji | `w/test_news_api.py::test_a_headline_without_a_time_carries_the_fields_and_says_why`, `w/test_openapi.py::test_a_response_model_declares_every_field_it_always_sends` |
| Znacznik zachowania → Operator zachowuje / lista zachowanych | `w/test_news_api.py::test_keeping_a_headline_whose_identifier_is_a_url_reaches_it_and_the_kept_list_finds_it` |
| → News, którego nie ma | `w/test_news_api.py::test_keeping_a_headline_that_is_not_there_is_refused_not_created` |
| Stan źródeł → Źródło, które nigdy nie odpowiedziało | `w/test_news_api.py::test_the_sources_lists_every_declared_feed_including_one_that_never_answered` |

### social-data-api (MODIFIED) i social-data-liveness (MODIFIED)

| Requirement / Scenario | Proven by |
|---|---|
| Kontrakt wyłącznie czyta → Klient szuka drogi do wymuszenia zbioru | `w/test_api.py::test_the_contract_publishes_no_route_that_writes_but_the_keep_flag` |
| → Znacznik nie dotyka treści | `w/test_news_store.py::test_keeping_is_idempotent_and_touches_nothing_else` |
| Wiek pętli → Pętla chodzi / druga pętla nie zasłania | `w/test_news_collector.py::test_serving_runs_both_loops_and_publishes_each_beat_under_its_own_name` (prawdziwy `serving`, `/health` wymienia `collect` i `news`); wiek w interwałach pętli: `packages/tc-runtime/tests/test_liveness.py` |
| → Pętla stanęła | `packages/tc-runtime/tests/test_liveness.py` (wiek rośnie bez uderzeń); alert `social_data.loop_passes_late` bierze maksimum po wymiarze `loop` (`infra/monitoring.tf`) |

### terminal-news

| Requirement / Scenario | Proven by |
|---|---|
| Okno z nazwą → Otwarcie zakładki | `t/NewsView.test.tsx::shows a headline with its delay as a range and names the window` |
| → Lista obcięta | `t/NewsView.test.tsx::says the list is cut instead of pretending to show the whole window` |
| Opóźnienie na karcie → ze zmierzonym / bez czasu publikacji | `t/delay.test.ts` (`delayText`, wszystkie trzy powody), `t/NewsView.test.tsx::says why a headline has no delay instead of showing a zero` |
| Przycisk zachowania → Zachowanie / Zmiana nieudana | `t/NewsView.test.tsx::keeps a headline with one click and asks for it by the pair`, `::puts the headline back as it was, and says so, when keeping is refused` |
| → Zdjęcie znacznika ze starego newsa | `t/delay.test.ts::expiryText` (po poprawce `8ae00b0`) |
| Zestawienie źródeł → Jedno źródło odmawia (stan, powód, ostatnie pobranie, mediana i p90 obu granic) | `t/NewsView.test.tsx::flags a refusing source in the table with its reason and its last success` |
| Pusta lista → Wszystkie źródła stoją | `t/NewsView.test.tsx::says collection has stopped rather than letting an empty list speak for it` |
| Odświeżanie → Odświeżenie nie dochodzi | `t/NewsView.test.tsx::keeps the headlines on screen when a refresh fails` |

## Gaps

1. **Zadanie 6.4** — weryfikacja po wdrożeniu, czynność po merge: `/social/news/sources` ma wymienić 15 źródeł z udanym pobraniem, a `/social/health` heartbeat `news`. Do zapisania tutaj po pierwszym przebiegu, które źródła faktycznie odpowiadają na produkcji (IRNA odpowiadała 504 przy pierwszej próbie, Google News nie podaje znaczników wersji).

Trzy luki z pierwszego przejścia (heartbeat `news` w `serving`, niezmiennik różnicy granic, liczby w tabeli źródeł) zostały zamknięte w `2e0e6da` i są w tabelach wyżej.

**Nie mylić z przeoczeniem:** retencja jest liczona od **pierwszego zobaczenia**, nie od publikacji. News zastany przy pierwszym pobraniu feedu żyje więc 28 dni od tej chwili, niezależnie od swojego wieku. To zapisane wprost w `social-data-news-ingest`, a nie luka.


## Addendum: pierwszy dzień na produkcji

Po wdrożeniu operator zgłosił trzy rzeczy, wszystkie w tej samej zmianie (zadania 7.1–7.5, commity `183afc5`, `7e276cc`, `3f408bd`).

| Severity | Where | Finding | Status |
|---|---|---|---|
| Średnie | `news/sources.py` `timesofisrael` | Feed odpowiada **403 z adresów Azure** (Cloudflare), a 200 z domowego IP tym samym User-Agentem — więc nie problem tożsamości, tylko blokada, której spec każe nie obchodzić. Źródło stało od pierwszego przebiegu. | **FIXED** w `183afc5` — wpis zastąpiony zapytaniem Google News `site:timesofisrael.com` (Iran, Israel, Hormuz, Hezbollah) |
| Średnie | `news/feed.py` (`summary` ≤ 1000 znaków) | Operator chce czytać **cały news w aplikacji**, a archiwum trzymało tylko krótki lead i ucinało resztę. Pomiar feedów: pełny artykuł niesie w RSS tylko Axios (~3,2 tys. znaków), Guardian i Middle East Eye ~700, pozostałe 100–300. | **FIXED w tym, co feed niesie** — `183afc5`: kolumna `content`, akapity zachowane. **Reszta pozostaje otwarta** (patrz Gaps) |
| Drobne | terminal `NewsCard` | Tytuł był odnośnikiem do strony źródła, więc kliknięcie wyrzucało z aplikacji. | **FIXED** w `7e276cc` i `3f408bd` — karta rozwija się w miejscu, oryginał to osobny odnośnik w rozwiniętej części |

### Spec coverage (nowe wymagania i scenariusze)

Skróty jak wyżej; `p/` = `modules/pocket/src/news/`.

| Requirement / Scenario | Proven by |
|---|---|
| ingest: Feed niesie całą treść | `w/test_news_feed.py::test_a_feed_that_carries_the_body_keeps_it_with_its_paragraphs_and_a_short_lead_beside_it`, `w/test_news_store.py::test_the_body_is_stored_beside_the_lead_and_an_empty_one_stays_empty` |
| ingest: Feed niesie tylko lead | `w/test_news_feed.py::test_a_feed_that_carries_only_a_lead_has_no_body_and_not_the_lead_twice`, `::test_an_aggregator_lead_that_only_repeats_the_headline_yields_neither` |
| api: Okno w minutach | `w/test_news_api.py::test_a_window_in_minutes_reaches_as_far_back_as_asked_and_no_further` |
| api: News z treścią i bez | `w/test_news_api.py::test_the_body_reaches_the_wire_and_is_empty_not_missing_where_the_feed_had_none` |
| terminal: Zmiana okna | `t/NewsView.test.tsx::offers the windows from five minutes to a week and asks for the one chosen`, `t/windows.test.ts`, `t/newsApi.test.ts::asks for more headlines over a week than over an hour` |
| terminal: Rozwinięcie newsa z treścią | `t/NewsView.test.tsx::opens the whole news in place and does not send the operator to the site` |
| terminal: News z samym leadem | `t/NewsView.test.tsx::says when the feed carried only a lead, and shows that lead in full` |
| terminal: Zachowanie nie rozwija | `t/NewsView.test.tsx::does not open the news when the keep button is pressed` |
| terminal: Sortowanie po oczekiwaniu / odwrócenie kierunku | `t/NewsView.test.tsx::orders by the wait when asked, and flips the direction`, `t/sort.test.ts` |
| terminal: Wszystkie i żadne | `t/NewsView.test.tsx::switches every source off and on with one click, and says so when none is chosen` |
| terminal: Tylko działające | `t/NewsView.test.tsx::keeps only the sources that answer with one click` |
| pocket (bez speca, jak reszta ekranu) | `p/NewsScreen.test.tsx` (rozwinięcie, sam lead, zachowanie nie rozwija, żądanie `minutes`), `p/sort.test.ts`, `p/window.test.ts`, `p/api.test.ts` |

### Gaps

1. **Pełny tekst poza tym, co niesie feed.** Dla większości źródeł (BBC, NYT, Al Jazeera, Tehran Times, IRNA, Iran International, Google News) archiwum ma tylko krótki lead, a ekran mówi to wprost. Pełniejszy tekst wymaga pobierania stron artykułów: scraping HTML per portal, paywall (NYT), ochrona Cloudflare (jak Times of Israel) i regulaminy zakazujące tego wprost (Al Jazeera). **Świadomie poza tą zmianą** — to decyzja operatora, nie techniczna; spec `social-data-news-ingest` mówi, że pakiet stron nie pobiera.
2. **Wymóg „pakiet nie pobiera stron artykułów”** nie ma testu: to brak zachowania, a test na brak wymagałby czytania importów (zakaz reguły 3 z `CLAUDE.md`).
3. **Zadanie 6.4** — po wdrożeniu: które z 15 źródeł faktycznie odpowiadają i które niosą treść.
