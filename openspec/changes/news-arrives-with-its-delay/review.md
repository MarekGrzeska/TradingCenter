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
| `modules/workbench`: `uv run pytest -q` (z testami `db` na testcontainers) | **2643 passed, 11 skipped** w 6 min 34 s |
| `modules/workbench`: `uv run pytest tests/social/test_news_*.py` | **54 testy nowe**, wszystkie zielone |
| `modules/workbench`: `uv run ruff check .` · `uv run pyright` | czysto · 0 błędów |
| `modules/terminal`: vitest · `tsc -b --noEmit` · `eslint .` · `node scripts/contract.mjs check` | **842 passed (68 plików)** · czysto · czysto · „Every contract is up to date” |
| `modules/pocket`: vitest · `tsc -b --noEmit` · `eslint .` · `node scripts/contract.mjs check` | **87 passed (17 plików)** · czysto · czysto · „The contract is up to date” |
| `scripts`: `uv run pytest -q` | **149 passed, 27 skipped** |
| `openspec validate news-arrives-with-its-delay --strict` | valid |
| `db-cost-check` (task 1.4): jednorazowy Postgres 17, 100 tys. wierszy `news_items`, 15 źródeł, `--cpus=1 --memory=2g` | wszystkie sześć zapytań idzie po indeksach; okno 6 h **19 buforów / 0,26 ms**, rachunek źródeł (3,6 tys. wierszy z doby) **153 bufory / 1,0 ms**, czyszczenie **3 bufory**; klasa **C2** |

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
| Drobne | `news/fetch.py:MAX_DOCUMENT_BYTES` | Rozmiar sprawdzany po pobraniu całego ciała (`response.content`), więc feed serwujący setki MB zająłby pamięć przed odmową. Lista feedów jest stała i sprawdzona w review, największy zmierzony to 212 KB (Axios). | **OPEN, przyjęte** — strumieniowanie dopiero z feedem spoza tej listy |
| Drobne | `news/feed.py:11` | `from ..providers.truth_social import clean` — pakiet newsów zależy od funkcji pomocniczej dostawcy postów. Test layeringu przechodzi (to ten sam pakiet), ale trzeci użytkownik `clean` to powód, żeby przenieść ją do neutralnego modułu. | **OPEN, przyjęte** |
| Drobne | `news/views.py:sources_state` | Rachunek źródeł liczy percentyle w Pythonie po wszystkich wierszach doby (3,6 tys. dziś, 1 ms w SQL). Przy dziesięciokrotnie większej liczbie feedów to 36 tys. wierszy na każde odpytanie co 60 s. | **OPEN, przyjęte** — do przeniesienia na `percentile_cont`, gdy feedów przybędzie |

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
| Niezmierzalne → Czas z przyszłości / News zastany | `w/test_news_latency.py::test_what_cannot_be_measured_says_why_and_is_never_zero`, `::test_the_figures_leave_the_unmeasured_out_of_every_statistic_but_count_them` |
| Rachunek źródła → Porównanie dwóch źródeł | `w/test_news_api.py::test_the_sources_lists_every_declared_feed_including_one_that_never_answered` |
| → Źródło dopiero dodane | `w/test_news_latency.py::test_a_source_with_nothing_measured_has_empty_figures_not_zeros` |
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
| Wiek pętli → Pętla chodzi / stanęła / druga pętla nie zasłania | **luka** — patrz Gaps |

### terminal-news

| Requirement / Scenario | Proven by |
|---|---|
| Okno z nazwą → Otwarcie zakładki | `t/NewsView.test.tsx::shows a headline with its delay as a range and names the window` |
| → Lista obcięta | `t/NewsView.test.tsx::says the list is cut instead of pretending to show the whole window` |
| Opóźnienie na karcie → ze zmierzonym / bez czasu publikacji | `t/delay.test.ts` (`delayText`, wszystkie trzy powody), `t/NewsView.test.tsx::says why a headline has no delay instead of showing a zero` |
| Przycisk zachowania → Zachowanie / Zmiana nieudana | `t/NewsView.test.tsx::keeps a headline with one click and asks for it by the pair`, `::puts the headline back as it was, and says so, when keeping is refused` |
| → Zdjęcie znacznika ze starego newsa | `t/delay.test.ts::expiryText` (po poprawce `8ae00b0`) |
| Zestawienie źródeł → Jedno źródło odmawia | `t/NewsView.test.tsx::flags a refusing source in the table with its reason and its last success` |
| Pusta lista → Wszystkie źródła stoją | `t/NewsView.test.tsx::says collection has stopped rather than letting an empty list speak for it` |
| Odświeżanie → Odświeżenie nie dochodzi | `t/NewsView.test.tsx::keeps the headlines on screen when a refresh fails` |

## Gaps

1. **`social-data-liveness` → wszystkie trzy scenariusze pętli newsów** nie mają testu wprost. Nazwanie pętli i wiek w jej własnych interwałach są w `tc_runtime` i tam testowane; nie ma natomiast testu, że `serving` rejestruje *drugą* heartbeat i że `/health` ją wydaje. Pisanie go wymagałoby uruchomienia całego `serving`, czyli sięgnięcia po sieć (kolektor postów odpytuje Truth Social). Zamiast tego pokrywa to zadanie 6.4: `/social/health` ma wymienić `collect` i `news`.
2. **`social-data-news-latency` → „różnica między granicami nie przekracza odstępu między dwoma pobraniami”** nie ma testu. Wynika wprost z konstrukcji (różnica to `first_seen_at − previous_fetch_at`), a odstęp jest egzekwowany osobnym testem, ale niezmiennik nie jest zapisany jako asercja.
3. **`terminal-news` → mediana i p90 obu granic w tabeli źródeł** — test tabeli sprawdza stan, powód i moment ostatniego pobrania, ale nie tekst liczb; formatowanie czasu trwania jest testowane osobno (`delay.test.ts`).
4. **Zadanie 6.4** — weryfikacja po wdrożeniu, czynność po merge. Do zapisania tutaj po pierwszym przebiegu: które z 15 źródeł faktycznie odpowiadają na produkcji (IRNA odpowiadała 504 przy pierwszej próbie, Google News nie podaje znaczników wersji).
5. **Retencja jest liczona od pierwszego zobaczenia**, nie od publikacji. News zastany przy pierwszym pobraniu feedu żyje więc 28 dni od tej chwili, niezależnie od swojego wieku.
