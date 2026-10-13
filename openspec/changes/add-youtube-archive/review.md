## Verdict

Pakiet `youtube_data` stoi w całości: lista obserwacji, pętla odkryj → transkrybuj → odczytaj → powiadom,
trzej dostawcy za interfejsami z symulacją, REST z trasą stanu, dziesięć narzędzi, alerty przez `/telegram`
w procesie i zakładka terminala. Montaż warunkowy robi to, co obiecuje `design.md` (decyzja 2): bez
`YOUTUBE_DATABASE_URL` nie ma trasy, narzędzi, pętli ani bazy, więc gałąź może wejść do `main` bez
wpływu na produkcję.

Przegląd diffu znalazł **dziewięć rzeczy poważnych** i kilkanaście drobnych. Wszystkie poważne są
naprawione w commicie kończącym przegląd, każda z testem. Żadna nie leżała w SQL ani w migracji. Leżały na
granicach: co pętla robi, gdy dostawca rzuca zamiast odpowiedzieć, co model dostaje w poleceniu, a co
walidacja potem odrzuca, i czyj zegar stempluje odczyt. Kilka rzeczy zostaje otwartych celowo i jest
nazwanych w „Deferred” — to decyzje, które należą do zmiany produkcyjnej albo do operatora, a nie
przeoczenia.

Zadania 9.1 (README pakietu, wiersz w `modules/workbench/README.md`) i 9.2 (przebieg ręczny na stacku)
**nie są częścią tego przeglądu** i zostają niezaznaczone. Przebieg ręczny wymaga uruchomionego stacku,
a stack jest operatora.

## Verified

Uruchomione na tej gałęzi, nie deklarowane:

| Co | Wynik |
|---|---|
| `modules/workbench`: `ruff check .` · `pyright` · `pytest -m "not live"` (unit + `-m db` na testcontainers), przed poprawkami | czysto · 0 błędów · **2784 passed** |
| to samo po poprawkach | czysto · 0 błędów · **2797 passed** (w tym 207 w `tests/youtube`, 13 nowych) |
| `modules/terminal`: `pnpm test` · `typecheck` · `lint` · `contract:check` | **836 passed** · czysto · czysto · „Every contract is up to date” |
| `modules/terminal` po poprawkach: `vitest run src/youtube src/data` · `lint` · `typecheck` | **137 passed** · czysto · czysto |
| `scripts`: `uv run pytest -q`, przed i po poprawkach | **177 passed, 2 skipped** |
| `openspec validate add-youtube-archive --strict` | valid |

Testy `live` nie były uruchamiane. Poprawki nie zmieniają kształtu żadnej odpowiedzi REST, więc kontrakt
terminala się nie zmienia.

## Findings

Przegląd prowadziły cztery niezależne przejścia po diffie: pętla i magazyn, dostawcy i symulacja,
powierzchnie i montaż, terminal. Każde znalezisko poniżej potwierdziłem, czytając ścieżkę kodu do końca.

| Severity | Where | Finding | Status |
|---|---|---|---|
| Poważne | `youtube_data/ingest.py` `_read` | **Awaria dostawcy modelu zużywała próby filmu.** Każdy wyjątek z `analyser.read` liczył się jako porażka odczytu: zły klucz, `insufficient_quota`, 429 albo zerwane połączenie. Nic z tego nie mówi niczego o filmie. Półtorej godziny awarii przy `reading_max_failures=3` zostawiało wszystkie dotknięte filmy w stanie `transcribed` na zawsze, poza kolejką, bez drogi powrotu. | **FIXED** — tylko `ReadingUnusable` (odpowiedź o tym filmie) liczy się jako porażka, reszta zostawia film na następny przebieg; `test_ingest.py::test_a_model_that_cannot_be_reached_spends_none_of_a_films_attempts` |
| Poważne | `youtube_data/analysis.py`, `ingest.py` | **Tokeny odrzuconej odpowiedzi nie trafiały do dziennego limitu.** Licznik zapisywał zużycie tylko po udanym odczycie. Odpowiedź, którą dostawca już policzył, a schemat odrzucił, była niewidoczna dla `daily_token_limit`. Film mógł spalić trzy pełne wywołania poza rachunkiem. Odmowa modelu (`message.refusal`) wyglądała przy tym jak ucięty JSON. | **FIXED** — `ReadingUnusable` niesie `tokens`, pętla je zapisuje, odmowa ma własny komunikat; `test_analysis.py::test_an_answer_thrown_away_still_says_what_it_cost`, `test_ingest.py::test_an_answer_that_is_thrown_away_is_still_counted_against_the_days_tokens` |
| Poważne | `youtube_data/analysis.py` | **Sufity list były w walidacji, a nie w poleceniu.** Model słyszał „every tradable instrument” i nie znał limitu 12 instrumentów ani 10 prognoz. Przegląd rynku z trzynastoma instrumentami był odrzucany trzy razy i zostawał nieodczytany, a to są filmy najbardziej warte odczytu. To samo dotyczyło daty „Q4” w prognozie: psuła cały odczyt. | **FIXED** — sufity są w poleceniu, nadmiar jest ucinany zamiast odrzucany, a nieczytelna data to `null`; `test_analysis.py::test_a_long_answer_is_cut_to_what_a_reading_keeps_and_a_vague_date_is_no_date` |
| Poważne | `youtube_data/providers/direct.py` | **Błąd sieci nie był mapowany.** `youtube-transcript-api` 1.2.4 opakowuje tylko `HTTPError`. `ConnectionError`, `Timeout` i `SSLError` z `requests` wychodziły z `fetch` wyjątkiem. Wywracały cały krok transkrypcji i nie dochodziły do następnego dostawcy, wbrew „przejście dalej po blokadzie albo błędzie”. | **FIXED** — `OSError` (którym jest `RequestException`) to `Blocked`, a łańcuch traktuje każdy wyjątek dostawcy jak odmowę; `test_transcripts.py::test_a_way_in_that_breaks_is_blocked_and_counted_not_raised`, `::test_a_provider_that_raises_is_passed_over_like_one_that_refused` |
| Poważne | `youtube_data/providers/direct.py` | **Zawieszone połączenie zatrzymywało pętlę na zawsze.** Biblioteka nie ustawia timeoutu, a `asyncio.to_thread` nie da się anulować. Jedno półotwarte połączenie wstrzymywało odkrywanie, transkrypcję, odczyt i alerty. | **FIXED** — `wait_for` z 60 s, po czasie `Blocked`; ten sam test co wyżej, wariant `TimeoutError` |
| Poważne | `youtube_data/store.py` `save_reading` | **Przyspieszona symulacja po cichu wyłączała alerty.** `analysed_at` brał `now()` bazy, a okno alertu liczy się zegarem pętli. Przy `YOUTUBE_SIM_SPEED=24` po około dwóch godzinach każdy świeży odczyt wypadał z 48-godzinnego okna i przechodził w `quiet` przed wysyłką. Testy tego nie widziały, bo `ManualClock` stoi przed czasem rzeczywistym. | **FIXED** — odczyt stemplowany zegarem pętli; `test_ingest.py::test_a_reading_is_stamped_by_the_loops_clock_which_the_alert_window_is_measured_on` |
| Poważne (uśpione do produkcji) | `workbench/config.py` `for_youtube` | **Pocket dostawał zapis i wydatki.** `for_youtube` przekazywał procesową `REST_CALLER_APPLICATION_IDS`, na której w produkcji stoją terminal **i pocket**. Po włączeniu pakietu tożsamość pocketu przechodziłaby przez `DELETE /channels/{id}`, `POST /topics` i płatne `POST /videos`. To pierwszy pakiet z trasami zapisu na wspólnej liście; `/telegram` ma własną właśnie z tego powodu. | **FIXED** — pakiet czyta własne `YOUTUBE_REST_CALLER_APPLICATION_IDS`, puste = odmowa w produkcji; `test_mounting.py::test_the_browsers_that_read_the_other_archives_are_not_this_packages_callers` |
| Poważne | `modules/terminal/src/data/http.ts` | **Powód odmowy nie docierał do dialogu.** Pakiet odmawia kształtem `{"detail": {"detail": "…"}}` (`Problem` w `HTTPException`). `parseErrorDetail` znał tylko napis i listę, więc operator widział „HTTP 422” zamiast „lista ma 100 kanałów”, wbrew `terminal-youtube`. Test klienta miał dokładnie ten kształt, ale sprawdzał tylko `kind`. | **FIXED** — zagnieżdżony powód jest czytany (dotyczy też `/social` i `/telegram`); `youtubeApi.test.ts` „carries the module's reason when it refuses” sprawdza teraz treść |
| Poważne | `.github/workflows/deploy-terminal.yml` | **Produkcyjny build terminala nie miał adresu ani zakresu YouTube.** Bez `VITE_YOUTUBE_HTTP` zakładka pytała `/youtube-api` na Static Web Apps. To czwarta odsłona pułapki opisanej w tym samym pliku. | **FIXED** — oba ustawienia dopisane; zakładka słyszy 404 workbencha i mówi „archiwum nie jest częścią tego wdrożenia” |
| Drobne | `youtube_data/alerts.py` | Przycinane było tylko streszczenie. Tytuł, nazwa kanału i nazwy instrumentów pochodzą od obcych i nie mają limitu. Wiadomość powyżej 4096 znaków brama odrzuca co przebieg przez 48 h. | **FIXED** — linie przycięte do 300 znaków; `test_alerts.py::test_a_title_nobody_bounded_is_cut_too_and_the_message_stays_under_the_gateways_ceiling` |
| Drobne | `youtube_data/ingest.py`, `alerts.py` | Film z symulowanego źródła odczytany prawdziwym modelem szedł na Telegram bez `[SYMULACJA]`, bo znacznik brano tylko z odczytu. | **FIXED** — znacznik z filmu albo z odczytu; `test_alerts.py::test_a_simulated_film_read_by_a_real_model_is_still_announced_as_a_simulation` |
| Drobne | `youtube_data/providers/build.py` | Dowolny symulowany dostawca przestawiał całą pętlę na szybki zegar, także przy prawdziwym `data_api`. Dzienne sufity kwoty resetowały się wtedy co godzinę. | **FIXED** — szybki zegar tylko przy `video_source=sim`; `test_config.py::test_a_faster_clock_is_the_simulated_sources_alone` |
| Drobne | `youtube_data/ingest.py` `_transcribe` | Blokada po sukcesie w tym samym przebiegu nie była widoczna, bo oba stemple miały ten sam `now` z początku przebiegu, a `blocked` wymaga `>`. Tak właśnie YouTube odcina adres. | **FIXED** — każda odpowiedź stemplowana własną chwilą |
| Drobne | `youtube_data/ingest.py` | `skip_unwanted` szedł tylko na końcu odkrywania. Odkrywanie przerwane w połowie wysyłało pięciogodzinny film do dostawcy. | **FIXED** — pomijanie także na początku transkrypcji |
| Drobne | `providers/data_api.py`, `providers/rss.py` | Strona proxy jako 200, wyjątki `defusedxml` (DTD, encje) i nieczytelna data wpisu wychodziły poza `SourceError`. Jeden zły kanał przerywał odkrywanie dla wszystkich po nim. | **FIXED** — wszystkie trzy to `SourceUnavailable` albo pominięty wpis |
| Drobne | `ingest.py` `_discover` | Po `QuotaExceeded` w pętli kanałów pętla tematów i tak płaciła za wyszukiwanie. | **FIXED** — wyczerpana kwota zeruje resztę dnia |
| Drobne | `views.py`, `tools/films.py`, `tools/watch.py`, `store.py`, `watchlist.py` | Wejścia dające 500 zamiast odmowy: `since` bez strefy obok świadomego `now` (`TypeError`), `hours` bez sufitu w narzędziu (`OverflowError`), offset transkrypcji powyżej int4, `interval_minutes` bez górnej granicy, `"²".isdigit()`. | **FIXED** — strefa domyślnie UTC, sufity, walidacja; `test_api.py::test_a_window_that_ends_before_it_starts_is_refused_with_the_reason` ma przypadek bez strefy |
| Drobne | `terminal/src/youtube/dialogs.tsx`, `FilmCard.tsx` | Literówka w polu liczbowym (`NaN` → JSON `null`) po cichu brała wartość domyślną. Ten sam instrument z dwoma horyzontami dawał zdublowany klucz React. | **FIXED** |
| Drobne | `store.py` `count_by_state` | Martwe `count(*)` po całej tabeli, czyli dokładnie to, czego zadanie 6.1 zakazuje dla `/state`. | **FIXED** — usunięte |
| Nit | `workbench/app.py`, `alembic-youtube.ini` | Komentarz wskazywał nieistniejące `_announce_youtube`, a ini mówiło o `social_data`. | **FIXED** |

### Deferred

| Where | Co | Dlaczego nie tu |
|---|---|---|
| `scripts/tests/test_pool_budget.py` | Pakiet ma pulę 2, a istniejące pakiety zajmują 29 z budżetu 30. Po włączeniu pakietu byłoby 31. | Wpis dziś spowodowałby czerwony test przez pakiet, który w produkcji nie istnieje. Zmiana produkcyjna musi zmniejszyć czyjąś pulę albo zmierzyć i podnieść budżet. |
| `infra/app-service.tf` | Zmiana produkcyjna musi ustawić `YOUTUBE_REST_CALLER_APPLICATION_IDS` (terminal), bo pusta lista odmawia wszystkim. | Terraform jest poza zakresem tej zmiany (`proposal.md`). |
| `store.py` `upsert_films` | Reguła alertu i profil filmu pochodzą od pierwszego źródła, które go znalazło. Temat z `never` może uciszyć film kanału z `always`, a późniejsza zmiana reguły kanału nie sięga filmów już odkrytych. | Spec („Regułę alertu wybiera kanał i temat”) tego nie rozstrzyga. To decyzja operatora: reguła najbardziej głośna wygrywa albo reguła czytana w chwili alertu. |
| `tools/watch.py` `set_alert_rule` | Agent może ustawić `never` na kanale operatora. Skutek jest niemal taki jak zdjęcie z listy, którego agentowi odmówiono. | Spec na to pozwala. Jeśli tak ma zostać, `design.md` powinien to powiedzieć; jeśli nie, narzędzie powinno zostać zawężone do wierszy `added_by='agent'`. |
| `watchlist.follow_channel` | Rozwiązanie `@uchwytu` przez narzędzie kosztuje 1 jednostkę bez sprawdzenia sufitu. | Spec wymaga odmowy tylko dla wyszukiwania i `analyse_video`. Koszt jest jednostkowy, a sufit i tak zatrzyma pętlę. |
| `providers/chain.py` | Blokadę dostawcy, który nie jest ostatni w łańcuchu, łańcuch połyka; `/state` pokazuje tylko ostatniego. | Dziś jest jeden prawdziwy dostawca transkrypcji. Ma to znaczenie dopiero z płatnym drugim. |
| `ingest.py` | Zadanie `Pending` nie ma limitu czasu. Przebieg, w którym każdy kanał rzuca `SourceError` (odwołany klucz), liczy się jako udany. | Zadania ma tylko symulacja. Drugi przypadek widać w logu, a naprawa to zmiana znaczenia udanego przebiegu, nie poprawka. |
| `providers/rss.py` | Źródło RSS nie zna długości ani statusu transmisji, więc nie odfiltruje Shorts ani trwającego live. | Znany kompromis `rss`. `data_api` to robi. |
| `terminal` | Licznik „100 filmów” nie mówi, że lista jest ucięta. | Kosmetyka; backend nie zwraca znacznika ucięcia. |
| `CLAUDE.md` | Tabela mówi „eight packages, seven schemas”. | Należy do zadania 9.1 razem z README. |

## Spec coverage

Ścieżki testów skrócone: `yt/` = `modules/workbench/tests/youtube/`, `t/` = `modules/terminal/src/`.
„(db)” oznacza test wymagający Dockera.

### youtube-data-watchlist

| Requirement / Scenario | Proven by |
|---|---|
| Obserwacja jest jawną decyzją → Dopisanie kanału uchwytem | `yt/test_watchlist.py::test_a_channel_is_followed_by_its_handle_…` (db), `yt/test_refs.py::test_a_channel_is_reduced_to_an_id_or_a_handle`, **częściowo** (tytuł nie jest sprawdzany) |
| → Ten sam kanał dopisany drugi raz | `yt/test_store.py::test_following_a_channel_twice_keeps_what_the_operator_set`, `yt/test_api.py::test_a_channel_is_followed_paused_and_taken_off`, `yt/test_tools.py::test_the_agent_follows_a_channel_once_…` (db) |
| → Kanał nie istnieje | `yt/test_watchlist.py::test_a_reference_that_names_no_channel_is_refused_and_writes_nothing`, `yt/test_api.py::test_a_channel_that_does_not_exist_and_a_list_that_is_full_…` (db) |
| Temat niesie własne granice kosztu → Dopisanie tematu bez granic | `yt/test_watchlist.py::test_a_topic_added_by_phrase_alone_gets_the_settings_limits_and_says_so`, `::test_a_topic_without_sensible_limits_is_refused`, `yt/test_api.py::test_a_topic_says_which_of_its_limits_came_from_the_settings` (db) |
| Lista ma znany sufit → Agent uderza w sufit | `yt/test_tools.py::test_the_agent_meets_the_same_ceiling_the_screen_does_and_is_sent_to_the_operator`, `yt/test_watchlist.py::test_the_ceiling_refuses_…` (db) |
| Zdjęcie wyłącznie drogą operatora → Operator zdejmuje kanał | `yt/test_api.py::test_a_channel_is_followed_paused_and_taken_off`, `yt/test_store_schema.py::test_removing_a_channel_leaves_its_films` (db), **częściowo** (odczyt filmów przez trasę po zdjęciu nie jest sprawdzany) |
| → Agent szuka drogi do zdjęcia kanału | `yt/test_tools.py::test_the_surface_adds_and_never_removes`, `::test_the_expected_tools_and_no_others`, `yt/test_local_tools.py::test_both_registries_see_the_same_ten_tools_and_know_which_of_them_write` (db) |

### youtube-data-ingest

| Requirement / Scenario | Proven by |
|---|---|
| Odkrywanie jest czynnością pętli → Odczyt nie woła dostawcy | **luka** — patrz Gaps |
| Stan filmu jest zapisany i ma koniec → Napisy pojawiają się po czasie | `yt/test_ingest.py::test_captions_that_arrive_late_are_asked_for_at_growing_intervals_and_each_ask_is_counted` (db) |
| → Napisów nie ma nigdy | `yt/test_ingest.py::test_a_film_that_never_has_captions_is_asked_about_four_times_and_then_never` (db) |
| Każdy krok ma limit partii → Kanał wrzuca naraz dwadzieścia filmów | `yt/test_ingest.py::test_a_pass_does_no_more_of_a_step_than_its_limit_and_the_rest_waits` (db), **częściowo** (sprawdzony tylko limit transkrypcji) |
| Pomijane jawnie → Transmisja na żywo | `yt/test_ingest.py::test_films_that_are_not_worth_a_transcript_are_skipped_…_and_a_stream_waits`, `::test_a_stream_is_read_once_it_has_ended`, `yt/test_store.py::test_the_queue_holds_what_is_due_and_not_what_is_live_or_finished` (db) |
| → Film ponad limit długości | `yt/test_ingest.py::test_films_that_are_not_worth_a_transcript_…`, `yt/test_store.py::test_only_films_whose_length_is_known_and_out_of_bounds_are_skipped` (db) |
| Film jest jeden → Film z kanału trafia też do tematu | `yt/test_ingest.py::test_a_film_that_a_channel_and_a_topic_both_find_is_read_once`, `yt/test_store.py::test_a_film_that_arrives_by_a_second_door_is_one_film_with_both`, `yt/test_store_schema.py::test_a_film_is_one_row_however_it_arrived` (db) |

### youtube-data-transcripts

| Requirement / Scenario | Proven by |
|---|---|
| Dostawca jest ustawieniem → Pierwszy dostawca zablokowany | `yt/test_transcripts.py::test_the_next_provider_is_tried_when_the_one_before_did_not_let_us_in`, `::test_a_provider_that_raises_is_passed_over_like_one_that_refused`, `::test_a_way_in_that_breaks_is_blocked_and_counted_not_raised` |
| → Brak napisów u pierwszego dostawcy | `yt/test_transcripts.py::test_a_film_with_no_captions_is_not_asked_about_twice` |
| Blokada i brak napisów to dwa stany → Każde zapytanie kończy się blokadą | `yt/test_ingest.py::test_a_provider_that_will_not_let_us_in_is_not_a_film_without_captions` (db), `yt/test_transcripts.py::test_being_refused_is_blocked_and_never_no_transcript` |
| Zużycie i dzienny sufit → Sufit osiągnięty w środku przebiegu | `yt/test_ingest.py::test_the_transcript_providers_day_ends_the_transcribing_and_tomorrow_resumes_it` (db), **częściowo** (`exhausted=True` na drucie niesprawdzone) |
| Sekret nie trafia do adresu → Żądanie z kluczem | `yt/test_data_api.py::test_the_key_is_in_a_header_and_in_no_address` |

### youtube-data-enrichment

| Requirement / Scenario | Proven by |
|---|---|
| Stały kształt i stempel → Ocena spoza zakresu | `yt/test_analysis.py::test_an_answer_that_breaks_the_schema_is_not_stored`, `yt/test_ingest.py::test_a_model_that_answers_badly_for_one_film_…` (db) |
| Transkrypcja jest daną obcą → Transkrypcja zawiera polecenie | `yt/test_analysis.py::test_the_call_has_no_tools_no_history_and_a_strict_schema`, `::test_the_instruction_says_the_transcript_is_data_and_the_message_marks_it_untrusted` |
| Brak modelu → Wdrożenie bez klucza | `yt/test_ingest.py::test_without_a_model_films_are_transcribed_and_wait_unread` (db), `yt/test_config.py::test_a_missing_model_key_is_a_supported_state_…`, **częściowo** (`model_configured=False` na drucie niesprawdzone) |
| Dzienny limit tokenów → Limit osiągnięty | `yt/test_ingest.py::test_the_days_tokens_stop_the_readings_and_not_the_transcripts`, `::test_an_answer_that_is_thrown_away_is_still_counted_against_the_days_tokens` (db), `yt/test_analysis.py::test_an_answer_thrown_away_still_says_what_it_cost` |
| Nieudany odczyt nie zatrzymuje serii → Model odmawia przy jednym filmie | `yt/test_ingest.py::test_a_model_that_answers_badly_for_one_film_…`, `::test_a_model_that_cannot_be_reached_spends_none_of_a_films_attempts` (db) |

### youtube-data-simulation

| Requirement / Scenario | Proven by |
|---|---|
| Zachowania prawdziwych dostawców → Napisy po dwóch godzinach | `yt/test_sim.py::test_captions_that_arrive_hours_late_are_absent_and_charged_until_they_do` |
| → Blokada co dziesiąte zapytanie | `yt/test_sim.py::test_the_same_seed_refuses_the_same_requests_and_about_the_share_asked_for`, **częściowo** (sprawdzone na 50%) |
| → Wyszukiwanie tematu | `yt/test_sim.py::test_a_search_finds_by_phrase_and_costs_what_the_scenario_says` |
| Czas jest sterowalny → Doba w kwadrans | `yt/test_sim.py::test_a_faster_clock_runs_faster`, `yt/test_ingest.py::test_a_reading_is_stamped_by_the_loops_clock_…` (db), **częściowo** (prędkość i przełom doby nie złożone w jednym teście) |
| Oznaczone wszędzie → Agent czyta symulowany film | `yt/test_tools.py::test_a_list_carries_an_excerpt_…`, `::test_the_words_come_a_page_at_a_time_…` (db), `yt/test_alerts.py::test_a_simulated_film_read_by_a_real_model_is_still_announced_as_a_simulation`, **częściowo** (`read_video` bez asercji `simulated`) |
| Nie rusza w produkcji → Symulacja w ustawieniach produkcji | `yt/test_sim.py::test_a_simulated_provider_is_refused_where_the_database_is_a_deployments` |
| Treści syntetyczne → Przegląd scenariusza | `yt/test_sim.py::test_the_scenario_that_ships_holds_every_kind_of_transcript_the_loop_must_survive`; „nie skopiowane z YouTube” to przegląd człowieka |

### youtube-data-alerts

| Requirement / Scenario | Proven by |
|---|---|
| Regułę wybiera kanał i temat → Kanał z regułą „zawsze” | `yt/test_alerts.py::test_what_a_channel_asked_for_decides_whether_a_film_is_announced` (db) |
| → Film bez odczytu | **luka** — patrz Gaps |
| Znacznik po udanej wysyłce → Brama odmawia | `yt/test_alerts.py::test_a_film_is_announced_once_and_a_failed_delivery_is_tried_again`, `::test_a_gateway_that_says_no_costs_the_film_its_turn_and_nothing_else` (db) |
| Wiadomość prowadzi do filmu → Długie streszczenie | `yt/test_alerts.py::test_a_long_summary_is_cut_by_this_package_…`, `::test_a_title_nobody_bounded_is_cut_too_…` |
| Brak adresata → Adresat nieustawiony | `yt/test_alerts.py::test_no_destination_is_a_working_configuration_and_says_nothing`, `yt/test_api.py::test_the_state_says_…` (db) |

### youtube-data-tools

| Requirement / Scenario | Proven by |
|---|---|
| Dopisuje, nie usuwa → Lista narzędzi | `yt/test_tools.py::test_the_expected_tools_and_no_others`, `::test_the_surface_adds_and_never_removes` (db) |
| Domyka drogę do odczytu → Sentyment złota | `yt/test_tools.py::test_what_channels_say_of_an_instrument_is_weighted_by_how_sure_they_sounded`, `::test_a_film_is_read_whole_without_its_words_…` (db) |
| Surowy tekst osobno → Model prosi o film | `yt/test_tools.py::test_a_film_is_read_whole_without_its_words_…`, `::test_the_words_come_a_page_at_a_time_and_are_marked_as_a_strangers` (db) |
| Kosztuje i mówi o tym → Wyszukiwanie po wyczerpaniu budżetu | `yt/test_tools.py::test_a_search_is_refused_where_the_source_cannot_and_where_the_day_is_spent` (db) |
| → Źródło nie umie wyszukiwać | ten sam test |

### youtube-data-api

| Requirement / Scenario | Proven by |
|---|---|
| Czyta archiwum i zarządza listą → Okno bez sensu | `yt/test_api.py::test_a_window_that_ends_before_it_starts_is_refused_with_the_reason` (db), z przypadkiem bez strefy |
| Pola odczytu zawsze obecne → Film nieodczytany | `yt/test_api.py::test_a_read_film_reaches_the_wire_…`, `yt/test_openapi.py::test_a_response_model_declares_every_field_it_always_sends` |
| Trasa stanu → Pętla stanęła | `yt/test_api.py::test_a_loop_that_has_stopped_is_called_stale_and_a_failed_pass_is_not_a_pass`, `yt/test_ingest.py::test_the_loop_reports_a_pass_only_when_it_completed_one` (db) |
| Dostęp rozstrzyga zapis → Ścieżka spoza zapisu | `yt/test_caller_access.py::test_every_published_rest_path_is_in_the_record`, `::test_a_path_nobody_recorded_belongs_to_no_surface`, `yt/test_mounting.py::test_the_browsers_that_read_the_other_archives_are_not_this_packages_callers`; odmowa 403 dla ścieżki spoza zapisu w `packages/tc-runtime` |
| Kontrakt jest źródłem typów → Zmiana kształtu | `pnpm contract:check` (wpis `youtube-data` w `t/../scripts/contract.mjs`) |

### terminal-youtube

| Requirement / Scenario | Proven by |
|---|---|
| Filmy z odczytem → Film bez odczytu | `t/youtube/YoutubeView.test.tsx` „shows no score at all on a film no model has read…” |
| Edycja listy → Kanał nie istnieje | `t/youtube/YoutubeView.test.tsx` „adds a channel … keeps the module's reason in the dialog”, `t/youtube/youtubeApi.test.ts` „carries the module's reason when it refuses” |
| Pasek stanu → Praca na symulacji | `t/youtube/YoutubeView.test.tsx` „says, for as long as it is true, that the films come from a simulation” |
| Nieudane odświeżenie → Odświeżenie nie dochodzi | `t/youtube/YoutubeView.test.tsx` „keeps the films on screen when a refresh fails” |

### workbench-process

| Requirement / Scenario | Proven by |
|---|---|
| Obecne z konfiguracji albo nieobecne → Baza nieskonfigurowana | `yt/test_mounting.py` (przełącznik), `scripts/tests/test_dev.py::TestTheOptionalYoutubeChain`, **częściowo** (brak trasy i narzędzi po stronie aplikacji niesprawdzony testem) |
| → Baza skonfigurowana, ale nieosiągalna | **luka** — patrz Gaps |

## Gaps

- **Odczyt nie woła dostawcy (ingest)**: żaden test nie liczy wywołań dostawcy ani `usage` wokół odczytu REST
  czy narzędzia. Ukryte wywołanie w trasie odczytu wydawałoby budżet po cichu. Tani test: odczyt, potem
  `meter.drain() == {}`.
- **Film bez odczytu (alerts)**: ogłaszający nie był puszczony na film `transcribed`. Strażnikiem jest jeden
  `JOIN` w `analysed_for_alert`.
- **Baza skonfigurowana, ale nieosiągalna (workbench-process)**: odmowa startu całego procesu z nazwą bazy
  YouTube nie ma testu. Ten sam mechanizm (`tc_runtime`) mają pozostałe pakiety, ale ten pakiet jest
  pierwszym warunkowym.
- **Testy powierzchni narzędzi tylko z Dockerem**: `test_the_expected_tools_and_no_others` i
  `test_the_surface_adds_and_never_removes` budują pulę przez fixture, więc bez Dockera gwarancja „nigdy nie
  usuwa” jest pomijana po cichu. To samo dotyczy czystych testów formatu wiadomości w `test_alerts.py`
  (znacznik `db` na całym module). CI je uruchamia, ale reguła 6 w `CLAUDE.md` mówi, że nie powinny go
  potrzebować.
- Drobniejsze częściowości z tabel (tytuł kanału, `exhausted` i `model_configured=False` na drucie,
  `read_video.simulated`, odsetek blokad 10%) to kosmetyka albo informacja dla operatora, nie ryzyko
  danych ani kosztu.
