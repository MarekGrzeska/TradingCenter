## Verdict

`market-data` stoi i archiwizuje: świeca zamknięta zapisywana raz i nadpisywana tylko wartością
autorytatywną, zakresy pokrycia odróżniające zamknięty rynek od dziury, rozdzielczości pochodne
liczone z serii minutowej na granicy **zmierzonej**, a nie założonej, ingest w dwóch trybach pod
jednym budżetem, i kontrakt, którego subskrypcja zaczyna się snapshotem — przez co szew między
historią a danymi na żywo zniknął z przeglądarki. Terminal czyta świece z archiwum, instrumenty
z gatewaya, a operator decyduje z panelu, co jest zbierane.

**Wszystkie jedenaście ustaleń tego przeglądu jest zamkniętych.** Dwa, które zostawiono początkowo
otwarte, bo zmieniały kształt kontraktu, zostały domknięte po decyzji: stan zbierania sięga teraz
po `marketStatus` z gatewaya, a postęp uzupełniania wychodzi z logu na listę par. Oba były
zaimplementowane od dawna i nie miały wyłącznie tego jednego miejsca, w którym się pokazują.

Czego czytelnik za rok nie powinien wziąć za przeoczenie: **siedem z jedenastu ustaleń tego
przeglądu wyszło z uruchomienia całości — w przeglądarce albo przeciw żywemu providerowi — a nie
z czytania kodu ani z suity.** Każde z nich
przechodziło swój test. To nie jest przypadek i nie jest argumentem przeciwko tym testom — jest
argumentem za tym, żeby zadanie „przejdź ręcznie ścieżkę" zostało w każdej następnej zmianie.

Drugi wniosek, tańszy do zignorowania i przez to warty zapisania: **dwa z ustaleń były najpierw
zdiagnozowane źle, oba dlatego, że pomiar wziął awarię za regułę.** Cisza na `BTCUSD` przez
godzinę w sobotę rano dała najpierw „krypto stoi w weekend", a potem — przez to samo skażone
odczytanie — „`tradeable` nie znaczy, że rynek jest otwarty". Jedno pytanie do providera osiem
godzin później obaliło oba. Kiedy pomiar zaskakuje, warto go powtórzyć, zanim się go zapisze.

## Verified

Uruchomione na `9f26566` plus poprawka z tego przeglądu, w każdym module osobno.

| Gdzie | Komenda | Wynik |
|---|---|---|
| capital-gateway | `uv run pytest -q` | 121 passed, 8 skipped, 1,9 s |
| capital-gateway | `uv run ruff check . && uv run ruff format --check .` | czysto, 30 plików |
| market-data | `uv run pytest -q` | **279 passed**, 7 skipped, 12,5 s |
| market-data | `uv run pytest -m db -q` | **172 passed**, 7 skipped, 107 deselected, 12,3 s |
| market-data | `uv run ruff check .` | czysto |
| terminal | `pnpm test` (`vitest run`) | **142 passed**, 13 plików, 5,8 s |
| terminal | `pnpm typecheck` (`tsc -b --noEmit`) | czysto, bez wyjścia |
| terminal | `pnpm lint` (`eslint .`) | czysto |
| terminal | `pnpm build` | `dist/` 421,46 kB (gzip 134,46 kB), 1,15 s |

Pominięcia są zamierzone: 8 w gatewayu i 7 w archiwum to testy za `--run-live`, a 107 odrzuconych
w `market-data` to zbiór `db`, którego domyślne uruchomienie nie wybiera. Testy `-m db` idą przeciw
jednorazowemu kontenerowi PostgreSQL i wymagają działającego Dockera.

Poza suitą — **przeciw pełnemu stosowi na koncie demo**, przez `scripts/dev.sh` i sterowany Chrome
(playwright-core), sobota 2026-08-08, 05:44–08:30 UTC:

- Dodanie `BTCUSD` `MINUTE` z panelu: `POST /pairs` → 201, a w logu gatewaya walidacja symbolu,
  uzupełnienie `?bars=54` i przyjęta subskrypcja w kilka sekund — **ingest podejmuje parę bez
  restartu**.
- Wykres narysował ~8 godzin świec minutowych z archiwum, z odczytem
  `O 64938.5 H 64943.85 L 64938.5 C 64942.25 V 147`.
- Restart modułu (06:03:13): każda para najpierw domknęła lukę — `BTCUSD MINUTE bars=65`,
  `US100 HOUR bars=11`, dokładnie tyle, ile minęło — a dopiero potem subskrybowała. Oba odczyty
  poszły po kolei na jednym połączeniu, zgodnie z `BACKFILL_CONCURRENCY=1`. Pokrycie przesunęło się
  `05:52:53 → 06:03:13` **scalone w ten sam wiersz**.
- Po poprawce z Finding 4, na żywym archiwum: `US100 HOUR` → 21 świec `derived=false`,
  `BTCUSD MINUTE` → 60 świec `derived=false`, `BTCUSD MINUTE_5` → 12 świec `derived=true`.
  Dwanaście pięciominutówek z sześćdziesięciu minut, czyli derywacja liczy to, co powinna.

Czego **nie** udało się sprawdzić, i dlaczego pierwsza diagnoza była zła. W oknie weryfikacji
`BTCUSD` nie oddawał nic po `04:59Z`, kwotowanie nie drgnęło przez 90 s, `US100` stał od piątku
20:00Z — odczytane jako weekend, bo była sobota. Dopytanie providera o godzinie **15:11 UTC tej
samej soboty** mówi co innego:

| Instrument | `marketStatus` | Ostatnia świeca minutowa |
|---|---|---|
| `BTCUSD`, `ETHUSD` | `TRADEABLE` | trwająca właśnie minuta |
| `US100`, `GOLD`, `EURUSD` | `CLOSED` | piątek ~21:00 UTC |

Czyli 23/5 dotyczy indeksów, forexu i towarów; **krypto handluje się także w weekend**. Poranna
cisza na `BTCUSD` była **ponadgodzinną awarią providera na instrumencie, który przez cały czas był
`TRADEABLE`** — nie kalendarzem. Zatrzymana seria nie dowodzi zamkniętego rynku, i to jest dokładnie
rozróżnienie, którego `collection_state` odmawia dziś zgadywać (Finding 5).

**Domknięte po południu, na parze krypto.** Start modułu o 15:31:59 dociągnął i **zapisał**:
`BTCUSD MINUTE: asked for 3 candles, wrote 3` oraz `US100 HOUR: asked for 20, wrote 20`. Świece
płynęły na żywo od 15:32 do 15:49, stan zbierania po raz pierwszy pokazał `market_closed` dla
zamkniętego indeksu i `collecting` dla krypto — a w chwili realnego zerwania strumienia `stalled`,
prawdziwie. Dnia handlowego wymaga już tylko część indeksowa testów `--run-live`, której sprawdzenie
gęstości mierzy świece względem zegara i na weekendzie wywróciłoby się, mówiąc prawdę o serii,
z którą wszystko jest w porządku.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Wysoka | `market_data/app.py:215` | Odczyt zakresu czytał `derived_candles` dla **każdej** rozdzielczości pochodnej, także gdy para była zbierana wprost. Para śledzona na `HOUR` trzymała 5000 świec i dostawała w odpowiedzi zero — przy `uncovered: []`, czyli „rynek był zamknięty przez cały dzień". | FIXED (ten przegląd) |
| Wysoka | `modules/terminal/vite.config.ts:76`, `src/data/config.ts:61` | Prefiks archiwum `/archive` jest zarazem ścieżką zakładki Archive. Każde żądanie docierające do serwera — przeładowanie, zakładka w przeglądarce, link z `dev.sh` — dostawało JSON usługi zamiast aplikacji. | FIXED `9f26566` |
| Wysoka | `src/chart/Chart.tsx:356` | `Veil` na domyślnym poziomie stosu, canvasy lightweight-charts na `z-index` 1 i 2 w kontenerze bez własnego kontekstu. Każdy komunikat wykresu renderował się, przechodził test i był zamalowywany pustym płótnem. | FIXED `9f26566` |
| Średnia | `src/data/socketHub.ts:146` | Para, której nikt nie zbiera, wyglądała jak zerwane połączenie i była ponawiana bez końca (20 prób w 12 s). Odmowa przed handshake'em jest niewidoczna dla przeglądarki. | FIXED `9f26566` |
| Średnia | `market_data/app.py:266` | `read_status(conn)` nigdy nie dostawał `market_open`, więc `STALLED` i `MARKET_CLOSED` były przez kontrakt **nieosiągalne** — każda opóźniona para to `UNKNOWN`. Panel nigdy nie wyróżniłby pary, dla której zbieranie ustało. | FIXED (ten przegląd) |
| Niska | `market_data/ingest/supervisor.py:70` | `Ingest.last_fill()` nie miał **żadnego wywołania** poza jednym testem. Postęp i przyczyny porażek zostawały w logu, czego spec zabrania wprost. | FIXED (ten przegląd) |
| Niska | `tests/test_app.py:21` | Dwa testy pisały świece wokół stałej `NOW` i czytały je **bez podania okna**, a `/candles` domyśla się ostatniej doby z zegara. Zdały każdy przebieg aż do 2026-08-08 12:00 UTC — doby po `NOW` — i wtedy zaczęły padać bez związku z kodem. | FIXED (ten przegląd) |
| Wysoka | `market_data/ingest/live.py:130` | Zerwanie połączenia **gatewaya z providerem** nie zamyka gniazda do nas, więc pętla nasłuchu nie kończy się i domknięcie luki nigdy nie przychodzi. `keepalive ping timeout` kosztował dwie świece, które provider nadal miał, i zostałyby do restartu. | FIXED (ten przegląd) |
| Średnia | `market_data/tracking.py:33` | Próg „zbieranie ustało" liczył dwa okresy i nie zostawiał miejsca na dostarczenie świecy, które trwa 52–169 s. Zdrowa para migała między `collecting` a `stalled` z odczytu na odczyt. | FIXED (ten przegląd) |
| Niska | `market_data/app.py` | Pytanie o stan rynku szło do gatewaya przy każdym odczycie `/pairs`, a zamknięty rynek jest trwale spóźniony: 74 zapytania o jeden instrument w kwadrans. | FIXED (ten przegląd) |
| Niska | `tests/test_live.py:45`, `design.md`, `README.md` | Kalendarze instrumentów były zapisane jako fakt i nigdy nie zmierzone — najpierw „`BTCUSD` to rynek ciągły", potem, po pierwszej korekcie, „wszystko chodzi 23/5". Obie wersje błędne: indeksy stoją w weekend, krypto nie. Zmierzone i zapisane z datą pomiaru. | FIXED (ten przegląd) |

**Finding 5 — źródło sygnału istnieje, brakuje decyzji o koszcie.** Pierwsza wersja tego akapitu
odradzała `tradeable` z katalogu gatewaya jako dwuznaczny, na podstawie `BTCUSD` raportowanego
w sobotę jako `tradeable: false` przy żywym kwotowaniu. **Ten pomiar był skażony** — trafił
w ponadgodzinną awarię providera. Powtórzony o 15:11 UTC daje odpowiedź czystą: `marketStatus` to
`TRADEABLE` dla krypto i `CLOSED` dla zamkniętego indeksu, a gateway już to publikuje jako
`Instrument.tradeable`. **Kontraktu gatewaya nie trzeba ruszać.**

**Zrobione wariantem 2.** Poniżej rozważane opcje, bo powód wyboru jest wart zapisania: to nie była
decyzja o poprawności, tylko o koszcie. `GET /pairs` musiałby
poznać stan rynku dla każdej pary na liście, a katalog gatewaya odpowiada na instrument, nie na
listę — czyli do dwudziestu żądań przez tę samą bramkę dziesięciu na sekundę, przy każdym odświeżeniu
panelu. Trzy wyjścia, w kolejności, w jakiej bym je rozważał:

1. **Pytać z cache'em o krótkim terminie ważności** (rzędu minuty) w `market-data`. Stan sesji zmienia
   się dwa razy na dobę, więc minuta świeżości jest hojna, a panel odpytywany co kilka sekund
   kosztuje wtedy jedno żądanie na parę na minutę. Najmniejsza zmiana, żadnego nowego kontraktu.
2. **Pytać tylko o pary, które i tak wyglądają na spóźnione.** Świeże pary nie potrzebują odpowiedzi
   — `COLLECTING` nie zależy od `market_open` — więc koszt ponosi się wyłącznie tam, gdzie ma
   rozstrzygnąć `STALLED` od `MARKET_CLOSED`. Zwykle to zero żądań.
3. **Poprosić gateway o odczyt zbiorczy.** Najczystsze i najdroższe: zmiana w drugim module.

Wybrane **2**: pytanie idzie tylko o pary z `UNKNOWN`, raz na symbol, a niedostępny gateway zostawia
`UNKNOWN` zamiast wywracać odczyt listy. Na zdrowym archiwum kosztuje to zero żądań. Wariant 1 —
cache o minutowej ważności — zostaje w zanadrzu, gdyby spóźnionych par bywało wiele naraz.

**Finding 6 — zrobione polem `last_fill` w wierszu `GET /pairs`.** To ta sama tabela, w którą
operator już patrzy, więc nie doszedł żaden nowy zasób. Wiersz niesie, o ile poproszono, ile
archiwum wzięło, ile to kosztowało u providera i nazwaną przyczynę porażki — plus `summary`, czyli
dokładnie to jedno zdanie, które moduł i tak zapisuje do logu. `null` znaczy, że dla tej pary żadne
uzupełnienie nie biegło od startu modułu: rekord żyje w pamięci i restart go czyści.

**Rozstrzygnięcia, które wyglądają jak usterki i nimi nie są** — żeby nikt ich „nie naprawił":

- `ingest/backfill.py:160` — pusta odpowiedź providera **nie** zapisuje pokrycia, więc okno, dla
  którego provider nic nie ma, jest odpytywane po każdym restarcie. Świadome: `write_candles`
  niczego nie potwierdziło, a zapisanie pokrycia z pustki byłoby twierdzeniem bez podstawy.
  Pilnuje tego `test_ingest.py::test_an_empty_answer_verifies_nothing`.
- `hub.py:156` — `Room` nie znika, dopóki trzyma świecę w budowie, a `publish` tworzy pokój dla
  każdej śledzonej pary niezależnie od subskrybentów. Rośnie to o jeden pokój na parę kiedykolwiek
  zbieraną w tym procesie, więc przy cyklu dodaj/zdejmij powtarzanym miesiącami rośnie bez granicy —
  ale pokój to zbiór, zamek i jedna świeca, i restart to zeruje. Odnotowane, nie ścigane.
- `app.py:370` — komentarz przy odmowie subskrypcji twierdzi, że przyjęcie handshake'u i zamknięcie
  „wyglądałoby jak feed, który padł, zamiast jak para, której nikt nie zbiera". Pomiar mówi
  odwrotnie: odmowa **przed** handshake'em nie daje przeglądarce żadnego powodu — goły 403, którego
  `WebSocket` nie pokazuje — i to jest właśnie powód, dla którego terminal musiał dostać drugie
  pytanie (Finding 4). Samo zachowanie zostaje: jest zgodne z gatewayem i nie oddaje gniazda, które
  zaraz umrze. Nieprawdziwe jest uzasadnienie w komentarzu.

## Spec coverage

### `market-data-store`

| Requirement / Scenario | Proven by |
|---|---|
| Świecę identyfikuje symbol, rozdzielczość i początek okresu → Ta sama świeca przychodzi dwa razy | `test_store.py::test_writing_the_same_triple_twice_overwrites_rather_than_duplicates`, `test_schema.py::test_a_second_row_for_the_same_triple_is_refused` |
| → Odczyt zachowuje porządek | `test_store.py::test_a_range_read_comes_back_oldest_first`, `::test_a_range_read_excludes_its_end_so_two_reads_join_cleanly` |
| Zapisywana jest wyłącznie świeca zamknięta → Strumień niesie świecę w budowie | `test_store.py::test_a_forming_candle_is_refused`, `::test_one_forming_candle_rejects_the_whole_batch` |
| → Okres się zamyka | `test_store.py::test_a_closed_candle_replaces_nothing_a_forming_one_left_behind` |
| Wartość od providera jest autorytatywna → Uzupełnianie trafia na świecę ze strumienia | `test_store.py::test_a_backfill_replaces_what_the_stream_left` |
| → Strumień trafia na świecę z uzupełniania | `test_store.py::test_the_stream_does_not_displace_a_backfilled_value`, `::test_a_declined_write_is_not_counted_as_written` |
| Jedna strona ceny → Odczyt nazywa stronę ceny | `test_store.py::test_a_candle_is_stored_on_the_bid_side_unless_told_otherwise`, `test_app.py::test_the_answer_names_the_side_of_the_spread` |
| Archiwum wie, co pokrywa → Brak świecy wewnątrz pokrycia | `test_coverage.py::test_a_missing_candle_inside_coverage_means_the_market_was_shut` |
| → Brak świecy poza pokryciem | `test_coverage.py::test_a_missing_candle_outside_coverage_means_nobody_looked`, `::test_the_two_absences_are_told_apart` |
| → Historia instrumentu się skończyła | `test_coverage.py::test_the_end_of_provider_history_is_remembered`, `::test_the_boundary_survives_a_later_merge` |
| Rozdzielczości pochodne są wyliczane → Odczyt rozdzielczości pochodnej | `test_rollups.py::test_a_derived_candle_opens_first_closes_last_and_spans_all`, `test_app.py::test_a_derived_resolution_is_served_from_the_derivation`, `::test_a_pair_collected_at_a_derivable_resolution_is_served_its_own_candles` |
| → Rozdzielczość dzienna albo tygodniowa | `test_rollups.py::test_day_and_week_are_not_derivable` |
| → Okres niepełny | `test_rollups.py::test_a_period_built_from_part_of_itself_says_so`, `::test_a_full_period_says_it_is_complete` |

### `market-data-tracking`

| Requirement / Scenario | Proven by |
|---|---|
| Śledzona para jest decyzją operatora → Zapytanie o nieśledzoną parę | `test_app.py::test_subscribing_to_a_pair_nobody_collects_is_refused` |
| → Operator dodaje parę | `test_tracking.py::test_a_pair_the_gateway_can_serve_is_taken_on`, `test_app.py::test_taking_a_pair_on_starts_collecting_it_without_a_restart` |
| Konfiguracja przeżywa restart → Restart modułu | `test_tracking.py::test_the_configuration_survives_a_restart`, `test_ingest.py::test_every_tracked_pair_is_collected_from_a_cold_start` |
| Usunięcie zatrzymuje zbieranie → Operator usuwa parę | `test_tracking.py::test_untracking_stops_collection`, `::test_untracking_keeps_every_candle`, `test_ingest.py::test_an_untracked_pair_stops_being_collected` |
| → Ponowne dodanie wcześniej usuniętej pary | `test_tracking.py::test_tracking_a_stopped_pair_again_resumes_the_same_decision`, `::test_a_stopped_pair_is_still_on_the_record` |
| Śledzone pary są wyliczalne wraz ze stanem → Odczyt listy | `test_tracking.py::test_the_status_carries_the_newest_candle`, `test_app.py::test_the_list_carries_how_collection_is_going` |
| → Zbieranie ustało po cichu | `test_tracking.py::test_more_than_two_periods_behind_with_the_market_open_has_stalled`, `test_app.py::test_a_late_pair_with_the_market_open_is_reported_stalled`, `::test_the_same_lateness_with_the_market_shut_is_not_a_fault`, `::test_a_gateway_that_cannot_say_leaves_the_pair_unknown` |
| Liczba par ma sufit → Próba przekroczenia limitu | `test_tracking.py::test_going_over_the_ceiling_is_refused_with_the_reason`, `::test_additions_racing_each_other_cannot_overrun_the_ceiling`, `test_app.py::test_going_over_the_ceiling_is_refused_with_the_reason` |

### `market-data-ingest`

| Requirement / Scenario | Proven by |
|---|---|
| Nasłuch na żywo → Świeca się zamyka | `test_ingest.py::test_a_closed_candle_from_the_feed_is_stored`, `::test_a_forming_candle_from_the_feed_is_not_stored` |
| → Połączenie ze strumieniem pada | `test_ingest.py::test_a_dropped_feed_is_resumed_while_the_pair_is_tracked`, `::test_the_wait_stops_growing_at_the_cap`, `::test_a_feed_that_produced_something_starts_over_from_the_first_delay` |
| Uzupełnianie wstecz → Nowo dodana para | `test_ingest.py::test_a_first_fill_reaches_back_the_configured_depth`, `::test_a_fill_is_one_request_however_deep` |
| → Provider nie ma starszych danych | `test_ingest.py::test_the_end_of_provider_history_is_recorded_as_a_boundary` |
| Restart domyka lukę → Start po przerwie | `test_ingest.py::test_a_start_after_a_break_fetches_the_missing_stretch`, `::test_a_resumed_subscription_closes_the_gap_it_left` |
| → Start bez przerwy | `test_ingest.py::test_a_start_without_a_break_sends_no_request`, `::test_a_pair_one_period_behind_asks_for_nothing` |
| Ruch ma budżet → Kilka par wymaga uzupełnienia naraz | `test_ingest.py::test_fills_do_not_run_more_at_once_than_the_budget_allows`, `::test_a_larger_budget_lets_more_run` |
| → Uzupełnianie w toku, a operator prosi o dane | `test_ingest.py::test_deciding_not_to_fetch_never_waits_for_the_budget` — **połowicznie**: odczyt operatora idzie do bazy i nigdy nie bierze limitera, więc jest to prawda z konstrukcji, nie z testu |
| Ingest raportuje postęp → Uzupełnianie się kończy | `test_ingest.py::test_a_fill_records_what_it_verified`, `::test_the_supervisor_reports_what_each_fill_did`, `test_app.py::test_the_list_says_what_the_last_fill_did` |
| → Uzupełnianie zawodzi | `test_ingest.py::test_a_failed_fill_names_its_reason_and_does_not_raise`, `::test_an_unreachable_gateway_is_reported_not_raised`, `test_app.py::test_a_failed_fill_reaches_the_list_with_its_reason` |

### `market-data-api`

| Requirement / Scenario | Proven by |
|---|---|
| Odczyt świec po zakresie → Odczyt zakresu | `test_app.py::test_a_range_read_answers_with_candles`, `::test_a_range_read_honours_its_bounds` |
| → Przedział wychodzi poza pokrycie | `test_app.py::test_a_range_read_marks_what_was_never_collected`, `::test_a_fully_covered_range_marks_nothing`, `::test_a_pair_never_collected_is_uncovered_end_to_end` |
| Subskrypcja zaczyna się od snapshotu → Konsument subskrybuje | `test_app.py::test_a_subscriber_is_handed_the_settled_series_first`, `::test_the_snapshot_carries_the_period_still_being_built` |
| → Świeca zamyka się w trakcie subskrypcji | `test_app.py::test_a_period_never_arrives_both_in_the_snapshot_and_after_it`, `::test_no_period_falls_between_the_snapshot_and_the_changes` |
| → Subskrypcja nieśledzonej pary | `test_app.py::test_subscribing_to_a_pair_nobody_collects_is_refused` |
| Świeca w budowie jest oznaczona → Odbiorca rozróżnia świece | `test_app.py::test_changes_after_the_snapshot_say_whether_a_candle_has_closed`, `::test_a_closed_candle_clears_the_forming_one` |
| Pokrycie jest odczytywalne → Odczyt pokrycia | `test_app.py::test_coverage_reads_back_over_the_contract`, `::test_a_pair_with_no_coverage_says_so_without_failing` |
| Pary zarządzalne przez kontrakt → Dodanie pary | `test_app.py::test_a_pair_can_be_taken_on_over_the_contract` |
| → Dodanie pary nieznanej providerowi | `test_app.py::test_a_symbol_the_gateway_will_not_serve_is_refused_with_the_reason`, `test_tracking.py::test_a_symbol_with_no_series_at_that_resolution_is_refused` |
| → Usunięcie pary | `test_app.py::test_a_pair_can_be_let_go_over_the_contract`, `::test_letting_go_of_a_pair_that_was_not_collected_is_a_404` |
| Odpowiedzi nazywają porażki → Baza nieosiągalna | `test_app.py::test_a_failure_never_carries_a_raw_database_error`, `::test_a_gateway_that_is_down_is_reported_as_upstream` |
| → **Nieobsługiwana rozdzielczość** | Egzekwowane przez `Resolution` jako enum FastAPI (422 automatyczne) i pokryte na WebSockecie przez `test_app.py::test_a_subscription_with_an_unknown_resolution_is_refused` — **na trasie HTTP bez testu** |

### `terminal-market-data`

| Requirement / Scenario | Proven by |
|---|---|
| Źródło wymienne → Dołożenie kolejnego źródła | `marketData.test.ts::"sends candles to the archive and instruments to the gateway"` (strukturalnie: widoki nie zmieniły się przy dołożeniu archiwum) |
| → Jedna instancja na całą aplikację | `GridView.test.tsx::"shares one connection between two slots on the same pair, and frees it with the last"`, `::"opens at most one connection per pair for a full 3x2 of distinct pairs"` |
| → Świece i instrumenty idą z różnych miejsc | `marketData.test.ts::"sends candles to the archive and instruments to the gateway"` |
| → Jedno ze źródeł nie odpowiada | `marketData.test.ts::"keeps the instrument search working while the archive is unreachable"`, `::"names both back ends, and what each one's absence costs"` |
| Zerwane połączenie wraca samo → Wykres pary, której nikt nie archiwizuje | `socketHub.test.ts::"stops retrying and says why, when the answer is a reason"`, `archive.test.ts::"names the pair and where to fix it, when nobody is collecting it"`, `Chart.test.tsx::"puts what it has to say above the chart library's canvases"` |
| → Archiwum nie odpowiada również na pytanie o powód | `socketHub.test.ts::"goes on retrying when the question itself fails"`, `::"goes on retrying when there is no reason to stop"` |
| → Połączenie pada | `socketHub.test.ts::"reconnects on an unexpected drop with growing backoff, and reopens the socket"`, `Chart.test.tsx::"marks the data stale when the stream drops, instead of showing a frozen candle silently"` |
| → Połączenie wraca | `Chart.test.tsx::"fills the outage from the reconnect's snapshot rather than a gap request"`, `::"never asks for a history of its own — the subscription brings it"`, `socketHub.test.ts::"asks for nothing after a reconnect beyond reopening the socket"` |
| → Snapshot styka się z posiadaną serią | `merge.test.ts::"folds a reconnect gap-fill into the existing series in one call"`, `::"never produces two bars with the same timestamp"` |

### `terminal-data-manager`

| Requirement / Scenario | Proven by |
|---|---|
| Panel jest zakładką → Operator otwiera panel | `App.test.tsx::"gives the archive panel its own address, and returns to it on a reload"`, `ArchiveView.test.tsx::"shows each pair with how collection is going and how fresh it is"` |
| → **Odświeżenie strony** | `App.test.tsx::"gives the archive panel its own address, and returns to it on a reload"` **plus** `config.test.ts::"gives no back end a relative prefix that a tab route already claims"`. Sam test w `App` scenariusza **nie dowodził**: w jsdom przeładowanie nigdy nie pyta serwera, i dokładnie tą szczeliną przeszła kolizja prefiksu |
| Operator dokłada parę → Dodanie pary | `ArchiveView.test.tsx::"adds the instrument picked from the search at the chosen resolution"` |
| → Para już archiwizowana | `ArchiveView.test.tsx::"says a pair is already archived instead of sending the request again"` |
| → Archiwum odmawia dodania | `ArchiveView.test.tsx::"shows the archive's reason when it refuses, not a generic failure"` |
| Panel pokazuje, czy zbieranie działa → Przegląd listy | `ArchiveView.test.tsx::"shows each pair with how collection is going and how fresh it is"` |
| → Zbieranie ustało | `ArchiveView.test.tsx::"marks a pair that stopped collecting out from the rest"` po stronie panelu, `test_app.py::test_a_late_pair_with_the_market_open_is_reported_stalled` po stronie archiwum — od poprawki z Finding 5 te dwa się spotykają |
| Panel pokazuje zasięg → Podgląd pokrycia pary | `ArchiveView.test.tsx::"shows how far the archive reaches, and whether that is as far as it can"`, `::"says nothing is verified rather than showing an empty range"` |
| Zdjęcie pary jest jawną decyzją → Operator zdejmuje parę | `ArchiveView.test.tsx::"asks first, promises the candles stay, and drops the row once confirmed"`, `::"leaves the pair collecting when the confirmation is dismissed"` |
| Panel mówi, gdy archiwum nie odpowiada → Archiwum nieosiągalne | `ArchiveView.test.tsx::"tells an unreachable archive apart from an empty one"`, `::"says nothing is archived rather than showing an empty table"` |

## Gaps

Wszystkie **zaakceptowane**, żadna nie blokuje archiwizacji zmiany. Dwie największe — `market_open`
bez producenta i postęp ingestu uwięziony w logu — **przestały być lukami**: zostały domknięte
w tym przeglądzie, a scenariusze, które wisiały przez nie w powietrzu, mają teraz test po obu
stronach.

1. **Odczyt operatora w trakcie uzupełniania** nie ma testu. Jest prawdą z konstrukcji — odczyt idzie
   do bazy, limiter obejmuje wyłącznie wywołanie do gatewaya — ale konstrukcja może się zmienić
   ciszej niż test.
2. **Nieobsługiwana rozdzielczość na trasie HTTP** opiera się na enumie FastAPI i nie ma własnego
   testu, w odróżnieniu od tej samej odmowy na WebSockecie.
3. **Domknięcie luki realnymi danymi** niesprawdzone na żywo — provider stał przez całe okno
   weryfikacji. Do powtórzenia przy otwartym rynku: zatrzymać moduł na kilka minut przy ruchu i
   potwierdzić, że restart dociąga to, co przeleciało.
4. **`--run-live`** (4 testy w `market-data`, 8 w gatewayu) nie idzie w domyślnym uruchomieniu.
   To zamierzone — wymaga klucza i sieci — ale znaczy, że granica `HOUR_4` jest zmierzona wtedy,
   gdy ktoś świadomie o to poprosi, a nie na każdym przebiegu.
