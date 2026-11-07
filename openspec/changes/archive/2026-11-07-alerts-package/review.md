## Verdict

Pakiet `alerts` jest gotowy w jedenastu PR-ach w stosie (#311–#321). Żaden nie jest scalony, więc to review dotyczy kodu, a nie
wdrożenia. Review znalazło dwa błędy w regule jednorazowej, jeden w formularzu i ryzyko utraty danych przy scalaniu. Po
review poprawiono wszystkie znaleziska Wysokie i Średnie oraz pokryto testem scenariusze, które go nie miały (wiersze FIXED
niżej). Znaleziska Niskie zostają otwarte. Świadomie niekompletne: kasowanie `purposes`, `assignments`, `alert_rule`
i `migrations_done` jest teraz osobnym krokiem 11.5 (`alerts/12-drop-old-data`), scalanym po sprawdzeniu konwersji w produkcji.

## Verified

- `modules/workbench`, 18.10.2026 na `alerts/11-cleanup` (`44c7a7f`): `uv run pytest -q -m "not db and not live"` — 1545 passed,
  1313 deselected. Testów `-m db` w tym review nie uruchamiano. Z raportu implementacji wynika, że przeszły lokalnie.
- `modules/terminal`, ten sam commit: `pnpm test` — 75 plików, 914 passed.
- `openspec validate alerts-package --strict` — valid.
- Diff `origin/main...HEAD` (199 plików, +11 890 / −2 478) przejrzany skillem `code-review` (poziom high) dwa razy: raz cały
  zakres, raz sam ostatni commit. Ręcznie potwierdzone w kodzie: wiersze 2–6 tabeli niżej (cytaty pod tabelą). Reszta pochodzi z przeglądu i nie była
  odtwarzana.
- Po poprawkach (18.10.2026, ten sam branch): `uv run pytest -q -m "not live"` w `modules/workbench` — exit 0 (z bazą, `-m db`
  włącznie); `ruff check .` — All checks passed; `pyright` — 0 errors; `pnpm test` w `modules/terminal` — 918 passed;
  `pnpm lint`, `pnpm typecheck`, `pnpm contract:check` — czyste; `uv run pytest -q` w `scripts/` — 235 passed, 1 skipped.
- **Nie sprawdzono:** całego stosu na prawdziwej bazie, wiadomości wysłanej przez Telegram i konwersji na kopii danych
  produkcji. Nie było też osobnego `/security-review`.

## Findings

Kolumna „PR” wskazuje, gdzie kod powstał (w przybliżeniu, wg zakresu grup w `tasks.md`).

| Severity | Where | Finding | Status |
|---|---|---|---|
| Wysokie | `modules/workbench/migrations/telegram/versions/0005_purposes_and_assignments_go.py:26`, `migrations/youtube/versions/0003_*` (#321) | Migracje kasują `purposes`, `assignments` i kolumny `alert_rule`, a ten sam commit usuwa konwersję (`alerts/conversion.py`, `legacy.py`, `workbench/legacy_alerts.py`). Migracja niczego nie sprawdza: ani znacznika konwersji (alerts 0003 kasuje nawet `migrations_done`), ani tego, czy `ALERTS_DATABASE_URL` jest ustawione. Scenariusze: (a) #318 i #321 scalone tuż po sobie, a deploy idzie tylko z HEAD (`deploy_gate.py:4` sam opisuje anulowanie checków pierwszego merge'a); (b) konwersja poddała się po 60 próbach, a jej ponowienie przy następnym starcie już nie istnieje; (c) instalacja bez `ALERTS_DATABASE_URL`. W każdym z nich przypisania znikają, nie stając się regułami. Alerty milkną bez komunikatu, a `downgrade` tworzy tylko puste tabele. Kolejność wdrożeń wymagana w `design.md` §8 jest dziś tylko instrukcją w opisie PR. | FIXED: kasowanie wydzielone do 11.5 (`alerts/12-drop-old-data`), w #321 tabele zostają, a klucz kaskaduje |
| Wysokie | `modules/workbench/alerts/publishing.py:60`, `alerts/store.py:131` (`set_enabled`) | Reguła jednorazowa po doręczeniu jest wyłączana, ale `last_fired_at` zostaje. Ani `set_enabled`, ani `replace_rule` go nie czyszczą, a `_consider` pomija regułę `once` z ustawionym `last_fired_at`. Gdy operator włączy ją ponownie, lista pokazuje „działa”, a reguła już nigdy nie odpali. | FIXED: `set_enabled` i `replace_rule` czyszczą `last_fired_at` reguły `once` |
| Średnie | `modules/workbench/alerts/clock.py:144` | Ścieżka zdarzeń ma strażnika „reguła `once` już odpaliła”, ścieżka zegara nie ma. Scenariusz: reguła stanu `once` odpala, brama odpowiada 429 lub 503 i wysyłka czeka na ponowienie. Po czasie martwym cena przecina próg drugi raz i powstaje drugie odpalenie. Gdy pierwsze dojdzie, drugie zostaje porzucone, a porzucenie woła `reopen_once_rule` i czyści `last_fired_at` reguły, która już powiadomiła. Przy dłuższej awarii „powiedz raz” daje więcej niż jedną wiadomość. | FIXED: `decide(..., once=)` nie odpala drugi raz |
| Średnie | `modules/terminal/src/alerts/dialogs.tsx:421`, `src/alerts/present.ts:266` | Warunek na atrybucie logicznym przy pustej wartości pokazuje „tak” (`term.value \|\| "true"`), a `valueOf` zapisuje `term.value === "true"`, czyli `false`. `blankTerm` startuje z `value: ""`. Operator, który zostawi „tak” bez zmiany, zapisuje regułę dopasowującą odwrotne zdarzenia (np. `simulated`, `translated`). | FIXED: `valueOf` traktuje pustą wartość jak „tak” |
| Średnie | `modules/workbench/workbench/app.py:162` | Pakiet `alerts`, a z nim zegar, startuje przed `polymarket_data`, `social_data`, `market_data` i `youtube_data`. Pierwszy obrót po każdym starcie czyta narzędzia pakietów bez puli. Każda należna reguła stanu dostaje wtedy wpis „unavailable” i przesuwa się o pełny interwał. W historii każdej reguły zostaje fałszywa niedostępność z każdego deployu. | FIXED: zegar wstrzymany (`hold_clock`) do chwili, gdy wszystkie pakiety serwują |
| Średnie | `modules/workbench/alerts/routers/state.py:28` | `rules_with_defects = max(drifted, gone)`, gdzie `gone` liczy **nazwy** brakujących adresatów, a nie reguły. Przykład: trzy reguły z rozjechanym filtrem i pięć wskazujących jednego usuniętego adresata dają 3 zamiast 8. Nagłówek terminala zaniża liczbę wadliwych reguł. | FIXED: `store.rules_with_defects` liczy reguły |
| Średnie | `modules/workbench/teams/alerts.py:53` (też `social_data/alerts.py`, `youtube_data/alerts.py`) | Blokowanie kolejki przez pierwsze elementy: przebieg lub post odrzucony na stałe (422) nie dostaje żadnego znacznika i zostaje na początku partii (`ORDER BY … LIMIT 20/50`). Wystarczy partia takich odrzuceń, a nowsze elementy nie zostaną przekazane, dopóki stare nie wypadną z okna 6 h / `since`. | FIXED: odrzucony element jest pomijany przez 10 minut (`SULK`) |
| Średnie | `modules/workbench/workbench/app.py:108` | Reguły stanu dostają wszystkie narzędzia tylko do odczytu, także te, które pytają dostawcę na żywo (`polymarket` `search_events`/`browse_events`, `market` `search_instruments` przez bramę Capital). Reguła z interwałem 30 s to ok. 2880 zapytań na dobę do Polymarket albo wydatek z budżetu 10 req/s konta Capital, dzielonego ze strumieniem bramy. `design.md` zakłada, że sprawdzenie to tani odczyt archiwum. | FIXED: `LIVE_READS` poza ofertą dla reguł |
| Niskie | `modules/workbench/alerts/gateway.py:56` | Za przejściowe uznawane są tylko 429, 503 i `retryable=true`. Każdy inny błąd 5xx (500 z nieprzewidzianego `GatewayError`, 502, 504) jest ostateczną odmową, więc alert przepada przy pierwszej próbie, choć z wiadomością nic nie było nie tak. | otwarte |
| Niskie | `modules/workbench/alerts/routers/drafts.py:53` | Tokeny szkicu są zapisywane tylko po udanym `drafter.draft()`. Odmowa modelu (`content=None`) albo błąd po wywołaniu podnosi wyjątek po tym, jak dostawca już policzył tokeny. Dobowy sufit `ALERTS_DRAFT_DAILY_TOKEN_LIMIT` nie widzi tego zużycia. | otwarte |
| Niskie | `modules/workbench/alerts/drafts.py:167` | Gdy model zwróci `destination: ""` (pusty napis zamiast null), a adresat nie jest jednoznaczny, szkic zostaje z zastępczym `'?'`. Do wady dochodzi wtedy „'?' is not a recipient”, a formularz otwiera się z `?` w polu adresata. | otwarte |
| Niskie | `modules/terminal/src/alerts/present.ts:216` | `formFrom` zamienia każdy argument narzędzia na napis, a `inputFrom` odsyła jako napis wszystko, co nie jest liczbą. Reguła z argumentem logicznym lub listą (np. `include_closed: true`) po „Edytuj” i zapisie zostaje odrzucona przez walidację schematu wejścia. | otwarte |
| Niskie | `modules/terminal/src/alerts/dialogs.tsx:435` | Dla `in` na atrybucie z widzianymi wartościami formularz pokazuje tylko pola wyboru, a `valueOf` scala `picked` z wpisanym wcześniej `term.value`. Wartości wpisane przed zmianą operatora albo spoza widzianych przy edycji idą w zapisie, ale w formularzu ich nie widać i nie da się ich usunąć. | otwarte |
| Niskie | `modules/workbench/migrations/teams/versions/0010_runs_announced.py:33` | Przebiegi nigdy nieogłoszone (brak pakietu alertów albo odmowa przez 6 h) nie dostają znacznika, więc częściowy indeks `ix_runs_unannounced` rośnie bez końca, w skrajności do rozmiaru tabeli `runs`. | otwarte |
| Niskie | `modules/workbench/telegram_gateway/routers/destinations.py:75` (#321) | Usunięty został strażnik `StillAssigned`, który nie pozwalał skasować adresata ani bota, do którego coś wysyła. Teraz usunięcie adresata wskazywanego przez włączone reguły zwraca 204, a każde odpalenie kończy się „unknown recipient”. Zgodne ze specyfikacją (`alerts-rules`: znikający adresat to stan reguły, `terminal-telegram`: okno potwierdzenia ostrzega). Jedynym śladem jest jednak licznik w `/state`, który zaniża (znalezisko o `state.py:28`), choć `store.destinations_in_use` już istnieje. | otwarte, decyzja |
| Niskie | `modules/workbench/youtube_data/alerts.py:199` (#321) | Film jest cichy tylko wtedy, gdy `origins == ('manual',)`. Gdy film wskazany ręcznie znajdzie przed przebiegiem także kanał lub temat, `ON CONFLICT` scali źródła i film zostanie opublikowany. Wcześniej `alert_rule='never'` przy wstawieniu wyciszał go na stałe. Zgodne ze scenariuszem „Film wskazany ręcznie” („jedynym źródłem jest wskazanie”), ale to zmiana zachowania. Literał `"manual"` jest przy tym zdublowany w `watchlist.py:198`, a wyciszanie idzie film po filmie, każdy z własnym połączeniem z puli. | otwarte, decyzja |
| Niskie | `modules/workbench/alerts/routers/drafts.py:44`, `alerts/routers/rules.py:39` | Jeden szkic pyta bramę o adresatów dwa razy i listuje narzędzia trzy razy. Zapis reguły (`_checked`) woła bramę wewnątrz `deps.connection`, trzymając jedno z dwóch połączeń puli przez czas odpowiedzi Telegrama. Przy wolnej bramie równoległe trasy dostają 503 „no database connection came free”. | otwarte |
| Niskie | `modules/workbench/alerts/routers/deps.py:55` | `deps.connection` łapie każdy `TimeoutError` z wnętrza bloku `async with` i raportuje go jako brak wolnego połączenia, także przekroczony czas zapytania albo wywołania narzędzia. Diagnoza idzie w złą stronę. | otwarte |
| Niskie | `modules/workbench/alerts/conditions.py:101` | Narzędzie, które odmawia w treści odpowiedzi (polymarket zwraca `{"refused": …, "retryable": true}` jako zwykły wynik), jest zapisywane jako „the answer holds no number”, a nie jako odmowa ze słowami narzędzia. | otwarte |
| Niskie | `modules/workbench/teams/alerts.py:127` | `RunAnnouncer.failing` jest zapisywane w każdym przebiegu, ale nic go nie czyta: brak trasy stanu, inaczej niż `telling` u producentów YouTube i postów. Odrzucenie każdego przebiegu widać tylko w logu. | otwarte |
| Niskie | `youtube_data/alerts.py:71`, `social_data/alerts.py`, `teams/alerts.py` | `Publisher`, `Rejected`, `Unreachable`, `_detail` i `slug` skopiowane niemal słowo w słowo w trzech pakietach. Zmiana kształtu `/events` lub `/event-types` wymaga trzech zgodnych poprawek. Kandydat na `packages/` albo przynajmniej na pomiar `scripts/measure-duplication.py`. | otwarte |
| Niskie | `modules/workbench/.env.example:112`, `:169-171` | Zostało aktywne `SOCIAL_ALERT_MIN_IMPACT_SCORE=8`, które ten diff dopisuje do `RETIRED_SETTINGS`. Każdy start z `.env` skopiowanym z przykładu ostrzega o wycofanym ustawieniu. Linie 169–171 dalej opisują przypisanie `youtube.film` i progi kanałów. | otwarte |
| Niskie | `modules/workbench/README.md:13`, `:66-68`, `docs/architecture.md`, komentarz w `deploy/compose` | README nadal opisuje drogę „archiwa → brama” i przypisania operatora, a nagłówek mówi „The ten packages” (CLAUDE.md i zadanie 11.3: dziewięć pakietów plus złożenie). `docs/architecture.md` ma nadal „seven databases” i „OpenAI ×2”, komentarz Compose mówi o celach przypisywanych w terminalu. | otwarte |
| Niskie | `modules/terminal/src/telegram/TelegramView.tsx:31`, `telegramApi.ts:105`, `data/config.ts:54`, `src/youtube/youtubeApi.test.ts:101` | Komentarze opisują usunięte cele i przypisania, a mock `ChannelOut` w teście dalej niesie `alert_rule: "always"`, którego kontrakt już nie ma. | otwarte |
| Niskie | `modules/terminal/src/alerts/alertsApi.ts:269`, `alerts/config.py:24-26`, `migrations/alerts/versions/0001_rules_events_and_fires.py:110-112`, `.env.example:113` | Bloki komentarza po trzy linie, wbrew regule CLAUDE.md „Two lines is the ceiling”. | otwarte |

Cytaty potwierdzone ręcznie:

- `store.set_enabled` ustawia `enabled`, `disabled_reason`, `next_check_at`, `last_result` i `last_known_result`, ale nie `last_fired_at`.
  `publishing._consider:60` zwraca 0 dla `mode == 'once' and last_fired_at is not None`.
- `clock.py` nie zawiera słowa `once`. `verdict.fire` prowadzi prosto do `store.record_fire`.
- `present.ts:246` `blankTerm` → `value: ""`; `present.ts:266` `kind === "boolean"` → `term.value === "true"`.
- `workbench/app.py:162-182`: `alerts.app.serving(...)` jest wchodzone przed `polymarket_data`, `social_data`, `market_data`, `youtube_data`.
- `state.py:28`: `rules_with_defects=max(standing["drifted"], gone)`, `gone = len(named - recipients)`.

## Spec coverage

Testy Pythona są w `modules/workbench/tests/`, testy TypeScript w `modules/terminal/src/`.

| Requirement / Scenario | Proven by |
|---|---|
| `alerts-api` · Kontrakt REST · Terminal czyta katalog | `alerts/test_rules_api.py::test_the_catalogue_offers_only_what_reads_and_says_which_fields_are_numbers`, `::test_the_catalogue_offers_the_pairs_the_archive_follows_and_the_values_an_attribute_has_had` |
| `alerts-api` · Wołający · Nieznana aplikacja | `alerts/test_caller_access.py::test_no_identity_and_a_stranger_are_refused` |
| `alerts-api` · Trasa stanu · Zegar stoi | `alerts/test_state_and_tools.py::test_a_clock_that_stopped_says_how_long_ago_and_is_told_apart_from_a_rule_that_never_fired`, `::test_a_clock_that_has_never_ticked_says_so_and_how_long_it_has_been` |
| `alerts-api` · Rozmowa widzi · Operator pyta, czemu nie dostał alertu | `alerts/test_state_and_tools.py::test_the_history_says_why_a_rule_was_quiet` |
| `alerts-conditions` · Wartość z narzędzia · Warunek na wskaźniku | `test_alert_tools.py::test_the_price_of_a_pair_is_offered_with_its_numbers`. Że to te same serwery co w rozmowie, widać w złożeniu (`workbench/app.py:106`), ale test o tym nie mówi |
| `alerts-conditions` · Zbocze · Cena utrzymuje się nad progiem | `alerts/test_conditions.py::test_a_yes_that_stays_yes_fires_once_not_every_look` |
| `alerts-conditions` · Zbocze · Reguła zapisana, gdy warunek już jest spełniony | `alerts/test_conditions.py::test_the_first_look_sets_the_baseline_even_when_the_value_is_already_over`, `alerts/test_clock.py::test_a_rule_written_when_the_price_is_already_over_waits_for_the_next_crossing` |
| `alerts-conditions` · Zbocze · Cena miga wokół progu | `alerts/test_clock.py::test_a_crossing_inside_the_cooldown_is_recorded_and_not_sent` |
| `alerts-conditions` · Trzeci stan · Archiwum rynku nie odpowiada | `alerts/test_clock.py::test_an_outage_is_one_line_and_never_a_crossing` |
| `alerts-conditions` · Trzeci stan · Powrót narzędzia przy spełnionym warunku | `alerts/test_conditions.py::test_a_look_that_learned_nothing_is_not_a_no_and_not_news` |
| `alerts-conditions` · Bez modelu · Tysiąc sprawdzeń bez odpalenia | `alerts/test_clock.py::test_a_thousand_looks_that_never_fire_cost_no_model_and_leave_no_usage` (pięćdziesiąt obrotów; zegar nie dostaje modelu, test pilnuje braku wiersza w `draft_usage`) |
| `alerts-conditions` · Dolna granica · Interwał poniżej granicy | `alerts/test_validation.py::test_a_value_rule_is_refused_for_each_reason_it_could_not_work` (przypadek `poll_interval_seconds=5`), `::test_an_interval_below_the_floor_names_the_floor` |
| `alerts-delivery` · Zapis przed wysyłką · Brama odmawia | `alerts/test_delivery.py::test_a_refusal_that_would_come_again_is_final_and_is_not_asked_twice` |
| `alerts-delivery` · Jedno na regułę · Restart w trakcie wysyłki | `alerts/test_delivery.py::test_a_fire_claimed_is_left_alone_until_its_lease_runs_out`, `alerts/test_schema.py::test_a_second_publication_of_the_same_event_is_refused` |
| `alerts-delivery` · Okno ponowień · Brama wraca po godzinie | `alerts/test_delivery.py::test_what_the_door_missed_for_an_hour_arrives_when_it_returns` |
| `alerts-delivery` · Okno ponowień · Brama wraca po dwóch dniach | `alerts/test_delivery.py::test_what_the_door_missed_for_longer_than_the_window_is_let_go_unsent` |
| `alerts-delivery` · Sufit · Zalew zdarzeń | `alerts/test_delivery.py::test_a_rule_that_tells_too_often_is_cut_at_its_cap_and_the_operator_is_told_once` |
| `alerts-delivery` · Brak bramy · Proces bez bramy | `alerts/test_delivery.py::test_no_door_in_the_process_is_a_state_of_the_fire_not_a_crash`, `alerts/test_state_and_tools.py::test_the_state_counts_rules_and_says_what_the_package_cannot_do` |
| `alerts-drafts` · Propozycja · Zdanie o cenie | `alerts/test_drafts.py::test_the_price_sentence_becomes_the_rule_it_describes`, `::test_a_sentence_returns_a_draft_stores_nothing_and_counts_its_tokens` |
| `alerts-drafts` · Ta sama walidacja · Zdanie o nieśledzonym instrumencie | `alerts/test_drafts.py::test_an_instrument_the_archive_does_not_follow_is_named_not_swapped_for_another` |
| `alerts-drafts` · Ta sama walidacja · Zdanie bez adresata | `alerts/test_drafts.py::test_a_sentence_that_names_nobody_gets_the_only_recipient_who_receives_and_says_so` |
| `alerts-drafts` · Bez klucza · Prośba o szkic bez klucza | `alerts/test_drafts.py::test_without_a_key_it_says_which_setting_and_the_rest_of_the_package_works` |
| `alerts-drafts` · Sufit kosztu · Sufit wyczerpany | `alerts/test_drafts.py::test_at_the_daily_ceiling_it_refuses_and_names_it`. Zawyżona pewność: zużycie przy odmowie modelu nie jest liczone (Findings, `drafts.py:53`) |
| `alerts-events` · Schemat · Producent ogłasza typ przy starcie | `alerts/test_producers.py::test_a_producer_announces_and_publishes_through_the_alerts_package_itself`, `youtube/test_alerts.py::test_nothing_is_handed_over_until_the_type_is_announced` |
| `alerts-events` · Schemat · Schemat traci atrybut użyty w regule | `alerts/test_rules_api.py::test_a_new_schema_that_loses_an_attribute_flags_the_rule_that_used_it_and_keeps_it` |
| `alerts-events` · Tylko z wnętrza · Publikacja z tokenem terminala | `alerts/test_events.py::…::test_nobody_from_outside_can_publish`, `alerts/test_caller_access.py::test_the_screen_reaches_the_contract_and_the_tool_caller_does_not` |
| `alerts-events` · Idempotentne · Ta sama publikacja dwa razy | `alerts/test_events.py::…::test_the_same_occurrence_published_twice_is_one_yes_and_one_alert` |
| `alerts-events` · Idempotentne · Atrybut o złym typie | `alerts/test_events.py::…::test_an_event_that_does_not_fit_its_type_or_has_none_is_refused` |
| `alerts-events` · Filtr · Film jednego kanału z oceną od 7 | `alerts/test_events.py::test_every_term_has_to_hold_and_no_terms_asks_for_everything` |
| `alerts-events` · Retencja · Zdarzenie po okresie retencji | `alerts/test_events.py::…::test_the_clock_forgets_events_after_their_retention_and_keeps_what_they_caused`, `alerts/test_schema.py::test_deleting_an_event_leaves_the_fire_it_caused` |
| `alerts-rules` · Skład reguły · Reguła ze źródłem stanu | `alerts/test_rules_api.py::test_a_rule_comes_back_as_it_was_written_with_the_defaults_of_its_kind` |
| `alerts-rules` · Skład reguły · Reguła z dwoma źródłami | `alerts/test_rules_api.py::test_a_rule_that_names_a_value_and_an_event_at_once_is_refused_for_both` (poprawka: wcześniej API cicho porzucało obce pola), `alerts/test_schema.py::test_a_rule_with_both_sources_is_refused` (poziom bazy) |
| `alerts-rules` · Odrzuca · Pole wyniku, które nie jest liczbą | `alerts/test_validation.py::test_a_value_rule_is_refused_for_each_reason_it_could_not_work` |
| `alerts-rules` · Odrzuca · Nieogłoszony typ zdarzenia | `alerts/test_validation.py::test_an_event_rule_is_refused_for_each_reason_it_could_not_match` |
| `alerts-rules` · Adresat · Adresat usunięty w zakładce Telegram | `alerts/test_rules_api.py::test_a_recipient_who_disappears_is_a_defect_on_the_list_and_not_a_deleted_rule`, `alerts/test_state_and_tools.py::test_a_recipient_who_is_gone_and_a_schema_that_moved_both_count_as_rules_with_problems`. Licznik w stanie zaniża (Findings, `state.py:28`) |
| `alerts-rules` · Tylko operator · Model szuka narzędzia zapisującego regułę | `alerts/test_state_and_tools.py::test_both_registries_see_the_same_two_tools_and_neither_writes` |
| `alerts-rules` · Jednorazowa · Alert cenowy jednorazowy | `alerts/test_delivery.py::test_a_one_time_rule_is_switched_off_when_its_one_message_is_delivered`. `alerts/test_delivery.py::test_a_one_time_rule_switched_on_again_may_tell_again`, `alerts/test_clock.py::test_a_one_time_rule_whose_first_alert_is_still_waiting_does_not_fire_again_on_the_next_crossing`, `alerts/test_conditions.py::test_a_one_time_rule_does_not_fire_a_second_time_while_the_first_is_still_on_its_way` |
| `social-data-alerts` · Bez odczytu · Model nieskonfigurowany | `social/test_alerts.py::test_a_post_no_model_has_read_is_not_handed_over` |
| `social-data-alerts` · Znacznik · Pakiet alertów nie przyjął zdarzenia | `social/test_alerts.py::test_a_failed_hand_over_leaves_no_marker_and_the_next_pass_retries` |
| `social-data-alerts` · Znacznik · Post już opublikowany | `social/test_alerts.py::test_a_post_is_handed_over_once_with_what_a_rule_filters_by` |
| `social-data-alerts` · Brak bramy · Pakiet alertów nieobecny | `social/test_alerts.py::…::test_collection_is_untouched_where_there_is_no_alerts_package` |
| `teams-runs` · Przebieg z harmonogramu kończy się błędem | `teams/test_run_announcer.py::test_a_run_that_started_from_a_schedule_or_a_trigger_says_which` |
| `teams-runs` · Pakiet alertów nieobecny | `teams/test_run_announcer.py::test_no_alerts_package_builds_no_announcer` (bez pakietu nie powstaje ogłaszacz, więc nic nie dotyka zakończenia przebiegu) |
| `telegram-gateway-delivery` · Nieznany adresat | `telegram/test_rest.py::…::test_an_unknown_name_is_refused_and_nothing_is_sent`, `telegram/test_sending.py::…::test_an_unknown_name_is_refused_without_a_request` |
| `telegram-gateway-delivery` · Wiadomość z celem | `telegram/test_rest.py::…::test_a_request_that_sends_a_purpose_is_refused_and_sends_nothing` |
| `telegram-gateway-bots`, `-destinations`, `-purposes` — REMOVED | wymaganie znika razem z kodem (nic nie czyta tabel); sama tabela zostaje do 11.5, więc `telegram/test_rest.py::test_a_destination_goes_with_the_assignments_nothing_reads_any_more` pilnuje, żeby nie blokowała usunięcia adresata |
| `terminal-alerts` · Lista · Reguła stanu, której narzędzie nie odpowiada | `alerts/present.test.ts` › „tells a working rule from a switched-off one, a wrong one and one that cannot read its value” |
| `terminal-alerts` · Kreator · Reguła na kanał YouTube | `alerts/alertsApi.test.ts` › „brings the attributes out of the schema and the values an attribute has had”, `alerts/present.test.ts` › „offers a number the ordering…”. `alerts/AlertsView.test.tsx` › „offers a channel outside the ones seen only by choosing inna wartość” |
| `terminal-alerts` · Kreator · Instrument spoza śledzonych | `alerts/present.test.ts` › „makes an instrument a choice among those the archive follows, and says which are required” |
| `terminal-alerts` · Podgląd · Szablon z atrybutem | `alerts/present.test.ts` › „uses the first value an attribute has had, and reaches into nothing” |
| `terminal-alerts` · Zdanie · Szkic z wadą | `alerts/AlertsView.test.tsx` › „opens a form to check from a sentence and saves nothing by itself”. `alerts/AlertsView.test.tsx` › „keeps saving out of reach of a draft with a flaw until the operator has changed something” (poprawka: wcześniej zapis był dostępny od razu) |
| `terminal-alerts` · Historia · Reguła zdławiona | `alerts/AlertsView.test.tsx` › „shows a fire the cap held back as held back, with the reason” |
| `terminal-telegram` · Brama bez niczego | `telegram/TelegramView.test.tsx` › „says where to begin on a door with nothing in it, instead of showing empty tables” |
| `terminal-telegram` · Brama nieosiągalna | `telegram/TelegramView.test.tsx` › „says the door does not answer, and does not show its lists as empty” |
| `terminal-telegram` · Usunięcie adresata | `telegram/TelegramView.test.tsx` › „warns, before a bot or a recipient is removed, that the rules pointing at it stop delivering” |
| `terminal-youtube` · Kanał nie istnieje | `youtube/YoutubeView.test.tsx` › „adds a channel from the tab, and keeps the module's reason in the dialog when it refuses” |
| `workbench-process` · Baza alertów nieskonfigurowana | `alerts/test_package.py::test_without_a_database_the_package_is_not_part_of_the_process`, `social/test_alerts.py::…::test_collection_is_untouched_where_there_is_no_alerts_package`, `youtube/test_alerts.py::test_no_alerts_package_is_a_working_configuration_and_says_nothing` |
| `workbench-process` · Baza skonfigurowana, ale nieosiągalna | `alerts/test_package.py::test_a_configured_database_that_does_not_answer_stops_the_start_and_names_the_alerts_database` (poprawka: wcześniej wyjątek był samym błędem gniazda, bez nazwy bazy) |
| `youtube-data-alerts` · Pakiet alertów odmawia | `youtube/test_alerts.py::test_a_film_is_handed_over_once_and_a_refused_one_is_tried_again` |
| `youtube-data-alerts` · Film bez odczytu | `youtube/test_alerts.py::test_a_film_no_model_has_read_is_published_as_nothing` |
| `youtube-data-alerts` · Film wskazany ręcznie | `youtube/test_alerts.py::test_a_film_named_by_hand_ends_quiet_because_whoever_asked_is_already_looking` |
| `youtube-data-alerts` · Długie streszczenie | `youtube/test_alerts.py::test_a_long_summary_is_cut_by_this_package_so_the_door_never_has_to_refuse_it` |
| `youtube-data-alerts` · Pakiet alertów nieobecny | `youtube/test_alerts.py::test_no_alerts_package_is_a_working_configuration_and_says_nothing` |
| `youtube-data-tools` · Lista narzędzi | `youtube/test_tools.py::test_the_expected_tools_and_no_others`, `::test_the_surface_adds_and_never_removes` |

## Gaps

- Otwarte znaleziska Niskie z tabeli wyżej.
- `alerts-conditions` „Warunek na wskaźniku”: że wartość pochodzi z tych samych serwerów co w rozmowie, wynika ze złożenia
  (`workbench/app.py`), a test sprawdza tylko ofertę narzędzi.
- Kolejność scalania #318 → wdrożenie → sprawdzenie `SELECT * FROM rules WHERE created_by = 'conversion'` → 11.5 jest dalej
  pilnowana przez człowieka, ale żadne wdrożenie nie kasuje już danych razem z kodem konwersji.
- Nie sprawdzono: stosu na prawdziwej bazie, wysyłki przez Telegram, `/security-review`.
- Brak sekretu `ALERTS_DB_PASSWORD` w środowisku `vps` zatrzyma deploy #311 (z raportu implementacji; nie sprawdzane tutaj).
- 11.4 (`deploy-watch` po każdym deployu) czeka na pierwsze scalenie.
