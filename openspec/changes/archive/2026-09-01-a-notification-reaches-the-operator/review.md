## Verdict

Brama stoi na produkcji i odpowiada, a obaj wywołujący, którzy zbierają i decydują, mają czym
powiedzieć. Grupy 1–14 weszły w całości; z grupy 15 zrobione są trzy kroki operatora z czterech.
**15.4 — wycofanie — zostaje niezaznaczone celowo**: sprawdzenie go wymaga wyczyszczenia
`TELEGRAM_ALERT_DESTINATION` u wywołującego, `apply`, obserwacji, że dalej zbiera i decyduje, i
drugiego `apply` z powrotem. To dwa applye i chwila ciszy w kanale, który dopiero co zaczął mówić —
odroczone, nie odhaczone. Rollback jest opisany w `design.md` („Migration Plan") i przechodzą przez
niego testy obu wywołujących, ale nie był wykonany na produkcji i ten dokument tego nie udaje.

Trzy rzeczy, których późniejszy czytelnik nie powinien wziąć za przeoczenie.

**Wyciek tokenu przez `httpx` znalazł test, nie produkcja.** Zadanie 3.5 było napisane jako
potwierdzenie reguły („adres żądania nie trafia do logu w żadnej ścieżce błędu") i znalazło realny
wyciek: Telegram wkłada token w ścieżkę żądania, więc URL **jest** poświadczeniem, a `httpx` loguje
każde żądanie na INFO razem z adresem. Oczyszczanie własnych komunikatów modułu było więc
niewystarczające — sekret wychodził przez zależność robiącą coś zupełnie rozsądnego. Stąd
`redaction.py`, i trzy jego własności znalezione przez patrzenie, jak filtr nie działa: renderuje
rekord przed dopasowaniem (bo `httpx` podaje URL jako `httpx.URL`, nie jako string), siedzi na
loggerze `httpx`, a nie tylko na uchwytach roota, i nie ma `\b` przed cyframi wzorca, bo w URL-u
token poprzedza `/bot`, a `t`→`1` nie jest granicą słowa.

**Na produkcji znalazła się jedna usterka i była to usterka wywołującego, nie bramy.** Godzinę po
pierwszym prawdziwym powiadomieniu post z oceną 10 przyszedł na telefon po angielsku, choć wiersz za
nim trzymał polskie tłumaczenie, za które ten moduł już zapłacił modelowi. `message()` budował
wyimek z `post.content` i nigdy nie zaglądał do `translated_content`. Powiadomienie jest jedynym
miejscem, gdzie ten odczyt jest używany bez niczego, na co można się przełączyć — terminal ma oba i
przełącznik, telefon ma to, co mówi wiadomość. Naprawione w #229, cztery testy, dwa czerwienieją
przeciw poprzedniemu `message()`.

**Znacznik `notified_at` w `strategy` jest zapisywany i przez nic nieczytany**, więc obiecane
ponowienie tam nie istnieje. To jedyne poważne ustalenie tego przeglądu — szczegóły w Findings.
Otwarte w chwili, gdy ten dokument powstawał; naprawione zaraz potem, przez
`a-refused-alert-is-tried-again`, bo naprawa musiała ruszyć normatywne zdanie wymagania i nie
mieściła się w zmianie, która już była zarchiwizowana.

## Verified

Uruchomione na tej gałęzi, nie deklarowane:

| Co | Wynik |
|---|---|
| `modules/telegram-gateway`: `uv run pytest -q` | **126 passed**, z czego **80 przeciw prawdziwemu PostgreSQL** (`-m db`, testcontainers) |
| `modules/telegram-gateway`: `ruff check .` · `pyright` | All checks passed · 0 errors, 0 warnings |
| `modules/social-data`: `pytest -q` · `ruff` · `pyright` | **100 passed** · czysto · 0 errors |
| `modules/strategy`: `pytest -q` · `ruff` · `pyright` | **317 passed** · czysto · 0 errors |
| `modules/workbench`: `pytest -q -m "not db"` | **458 passed** |
| `scripts`: `uv run pytest -q` | **154 passed, 3 skipped** — w tym `test_guide_ceiling`, `test_dev`, `test_deploy_workflows` |
| `infra`: `terraform fmt -check -recursive` · `init -backend=false` · `validate` | bez zmian · ok · „Success! The configuration is valid." |
| `openspec validate a-notification-reaches-the-operator --strict` | valid |

Testy `live` nie były uruchamiane. Ten moduł nie ma zestawu `live` w ogóle: obie powierzchnie
Telegrama stoją za poświadczeniami, których CI nie dostanie, i dlatego obie są za protokołem z
fake'iem — `design.md`, „MTProto za protokołem".

Przeciw produkcji, po wdrożeniu obrazu z merge'a:

```
GET https://app-tradingcenter-telegram-gateway.azurewebsites.net/
    200  {"service":"telegram-gateway","docs":"/docs"}
GET .../mcp     (bez tokenu)   401
GET .../state   (bez tokenu)   401
GET https://app-tradingcenter-social-data.azurewebsites.net/
    200  {"service":"social-data","docs":"/docs"}
```

`GET /` odpowiadające 200 jest tu, jak przy `polymarket-data`, najmocniejszym pojedynczym sygnałem:
moduł nie serwuje, dopóki nie doprowadzi bazy `telegram` do rewizji swojego obrazu pod własną blokadą
doradczą — więc 200 znaczy, że migracja przeszła własną tożsamością i że `grant-schema-ownership.sql`
z 15.1 zrobił swoje. **To jest dowód na 15.2**: ustawienia dojechały przed obrazem, bo obraz
egzekwujący `TOOL_CALLER_APPLICATION_IDS` i `REST_CALLER_APPLICATION_IDS` odmawia wszystkim, gdy
rekord jest pusty, a `/mcp` i `/state` odmawiają dokładnie tak, jak powinny, a nie 403 „nikt tu nie
wchodzi".

**15.3 jest raportem operatora, nie pomiarem tego przeglądu**: pierwszy bot to `@mgTradingCenterBot`,
adresat operatora jest w stanie `ready`, wysyłka potwierdzona odebraną wiadomością. Sprawdzić tego
stąd nie da się bez tokenu do `/state`, a token operatora jest jego.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **Poważne** | `strategy/alerts.py:107` (`is_new_setup`) i `strategy/store.py:407` | `notified_at` w `strategy` jest **kolumną tylko do zapisu**. O powiadomieniu decyduje wyłącznie `is_new_setup(decision, previous)`, które porównuje kierunek z **poprzednią zapisaną decyzją** i nigdy nie pyta, czy tamta rzeczywiście dojechała. Skutek: odmowa bramy dokładnie na tej świecy, na której setup powstał, nie jest ponawiana — następna świeca z tym samym kierunkiem to „nie zmiana", więc milczy, i setup stojący dziesięć świec nie zostaje zapowiedziany ani razu. To jest wprost przeciw `design.md` („nieudana wysyłka nie stawia znacznika, więc następny przebieg pętli próbuje jeszcze raz") i przeciw uzasadnieniu w `strategy-alerts` („brak znacznika jest jedynym mechanizmem ponowienia"). Asymetria widać w samych nazwach testów: `social-data` ma `test_a_failed_delivery_leaves_no_marker_and_the_next_pass_retries`, `strategy` ma `test_a_failed_delivery_leaves_the_decision_recorded_and_unmarked` — i na tym kończy. Normatywne zdania obu wymagań są spełnione (znacznik nie jest stawiany po porażce; ta sama decyzja nie powiadamia dwa razy), więc `--strict` przechodzi; nie spełniona jest obietnica, którą oba niosą w prozie. | **FIXED** w `a-refused-alert-is-tried-again` — `is_new_setup` czyta `previous.notified_at`; osobna zmiana, bo normatywne zdanie wymagania musiało się zmienić razem z kodem |
| Drobne | `social_data/ingest.py:104` | Ponowienie w `social-data` **ma termin ważności**: `since = now - COLLECT_WINDOW_HOURS` (domyślnie 24 h), więc post, którego brama odmawiała dłużej niż dobę, wypada z okna i nie zostanie zapowiedziany nigdy. Zachowanie jest spójne z resztą modułu — to samo okno ogranicza zbiórkę i wzbogacenie — ale żadne wymaganie tego nie mówi, a „ponawia w nieskończoność" jest naturalnym odczytaniem `social-data-alerts`. | **z projektu, zapisane tutaj** — 24 h ciszy bramy to i tak awaria, o której operator dowiaduje się inaczej |
| Drobne | `telegram_gateway/bots.py:82` | `destroy` woła `creator.guard(can_create=can_create, held=0, ceiling=1)` wyłącznie po to, żeby sprawdzić `can_create`. Argumenty są atrapą dobraną tak, by sufit nie zadziałał — czyta się jak sprawdzenie sufitu przy kasowaniu, którym nie jest. Zachowanie poprawne, nazwa myląca. | **FIXED** — `creator.require_session` jest osobną funkcją, a `destroy` woła ją zamiast `guard` z sufitem-atrapą |
| Poważne | `telegram_gateway/bot_api.py`, cały moduł | Token bota w ścieżce żądania wychodził do logu przez `httpx`, nie przez kod tego modułu. Znalezione przez test zadania 3.5. | **FIXED** w #226 — `redaction.py`, filtr na loggerze `httpx`/`httpcore` i na uchwytach roota, dopasowanie po kształcie tokenu, podstawienie zamiast usunięcia |
| Poważne | `social_data/alerts.py:114` (`message`) | Alert szedł po angielsku, choć moduł miał polskie tłumaczenie tego posta. Znalezione **na produkcji**, godzinę po pierwszym prawdziwym powiadomieniu. | **FIXED** w #229 — `translated_content` z odwrotem na oryginał i jedną linijką mówiącą, że to oryginał; wyimek cięty z tego tekstu, który naprawdę idzie |

Poza tym przegląd diffu nie dał nic, co przetrwałoby sprawdzenie. Odmowy w `caller_access.py` są
fail-closed w każdej gałęzi łącznie z „ustawień jeszcze nie ma" (503, nie przepuszczenie), token ma
jedną drogę wyjścia ze składu i ma to własny test, a `Watcher` nie trzyma połączenia z puli przez
30-sekundowy long poll — co przy puli czterech i sufcie dwudziestu botów było jedynym miejscem, gdzie
ten moduł mógł zagłodzić własną bazę.

## Spec coverage

Testy bramy w `modules/telegram-gateway/tests/`, wywołujących w `tests/test_alerts.py` każdego z nich.

### telegram-gateway-delivery

| Requirement / Scenario | Proven by |
|---|---|
| Wysłanie jest jednym aktem — Wiadomość dochodzi | `test_sending.py::TestSending::test_a_message_reaches_the_named_destination`, `test_rest.py::TestSending::test_a_message_answers_with_the_identifier_telegram_gave_it` |
| — Nie ma czego odczytać | `test_sending.py::TestSending::test_nothing_is_recorded_about_what_was_sent` |
| Odmowa Telegrama dociera w całości — Przekroczony limit | `test_sending.py::TestSending::test_a_rate_limit_carries_the_wait_telegram_asked_for`, `TestReadingTelegramsAnswer::test_a_rate_limit_becomes_its_own_refusal`, `test_rest.py::TestSending::test_a_rate_limit_reaches_the_caller_with_the_wait_telegram_asked_for` |
| — Adresat zablokował bota | `test_sending.py::TestSending::test_a_block_marks_the_destination_and_names_it`, `::test_a_blocked_destination_costs_no_further_requests`, `TestReadingTelegramsAnswer::test_a_block_is_told_apart_from_a_revoked_token`, `::test_another_403_stays_an_ordinary_refusal` |
| Wiadomość jest adresowana nazwą — Nieznany adresat | `test_sending.py::TestSending::test_an_unknown_name_is_refused_without_a_request`, `test_rest.py::TestSending::test_an_unknown_name_is_refused_and_nothing_is_sent` |
| Za długa treść jest odmową — Treść przekracza sufit | `test_sending.py::TestSending::test_too_long_is_refused_rather_than_shortened` |

### telegram-gateway-destinations

| Requirement / Scenario | Proven by |
|---|---|
| Adresat powstaje z tapnięcia — Operator prosi o adresata | `test_binding.py::TestTheOffer` (5 testów), `test_rest.py::TestDestinations::test_asking_for_a_destination_answers_with_a_link_to_tap` |
| — Tapnięcie wiąże | `test_binding.py::TestWhatComesBack::test_a_start_with_the_secret_binds_the_chat_that_sent_it`, `test_store.py::TestDestinations::test_the_secret_turns_the_intention_into_an_address` |
| — Sekret zużyty albo przeterminowany | `test_binding.py::TestWhatComesBack::test_the_same_secret_arriving_twice_binds_once`, `::test_an_expired_secret_binds_nothing`, `test_store.py::TestDestinations::test_a_secret_that_never_existed_is_told_apart_from_a_spent_one` |
| Adresat, który zablokował bota — Blokada | `test_sending.py::TestSending::test_a_blocked_destination_costs_no_further_requests`, `test_store.py::TestDestinations::test_blocking_keeps_the_destination`, `::test_binding_again_clears_a_block` |
| Usunięcie adresata nie rusza bota — Adresat usunięty | `test_store.py::TestDestinations::test_removing_a_destination_leaves_the_bot_and_its_siblings`, `test_rest.py::TestDestinations::test_removing_a_destination_leaves_the_bot_and_its_others_standing` |

### telegram-gateway-bots

| Requirement / Scenario | Proven by |
|---|---|
| Brak sesji konta jest wspierany — Wysyłka bez sesji | `test_config.py::TestTheAccountSession::test_all_three_absent_is_a_working_configuration` plus cały `test_sending.py`, który nie zna sesji |
| — Zakładanie bez sesji | `test_bots.py::TestWhatIsCheckedBeforeSpeaking::test_no_account_session_names_the_settings`, `TestCreating::test_without_a_session_nothing_is_said_to_telegram`, `test_rest.py::TestBots::test_creating_one_without_an_account_session_names_the_missing_setting` |
| Zakłada wyłącznie na żądanie — Start bez botów | `test_rest.py::TestState::test_a_gateway_with_nothing_in_it_says_so_rather_than_failing`, `test_tools_surface.py::test_an_empty_gateway_is_answered_rather_than_failed`, `test_sending.py::TestSending::test_an_unknown_name_is_refused_without_a_request`, `test_layering.py::test_nothing_creates_a_bot_on_its_own_initiative` |
| Sufit sprawdzany przed rozmową — Sufit osiągnięty | `test_bots.py::TestWhatIsCheckedBeforeSpeaking::test_the_ceiling_refuses_before_telegram_is_asked`, `::test_room_under_the_ceiling_passes`, `TestCreating::test_at_the_ceiling_nothing_is_said_to_telegram` |
| Odpowiedź bez tokenu jest odmową — Odpowiedź, której moduł nie rozumie | `test_bots.py::TestReadingTheCreatorBot` (3 testy), `TestCreating::test_an_unreadable_reply_stores_no_bot` |
| Token nie wychodzi z modułu — Odczyt bota | `test_store.py::TestTheTokenDoesNotLeak::test_no_read_a_response_is_built_from_carries_the_token`, `test_rest.py::TestBots::test_reading_the_bots_carries_no_token` |
| — Świeżo założony bot | `test_bots.py::TestCreating::test_the_token_is_kept_and_never_returned`, `::test_the_token_does_not_reach_the_log` |

### telegram-gateway-api

| Requirement / Scenario | Proven by |
|---|---|
| Kontrakt rozdziela wysyłanie od zarządzania — Wywołujący wysyła | `test_rest.py::TestSending` (3 testy) |
| Zakładanie, kasowanie i wiązanie tylko w REST — Model próbuje sięgnąć po zarządzanie | `test_tools_surface.py::test_the_surface_holds_no_way_to_create_a_bot_or_bind_a_destination`, `test_caller_access.py::test_the_tool_caller_does_not_reach_the_routes_that_manage_bots` |
| Moduł mówi, czego mu brakuje — Brama bez adresatów | `test_rest.py::TestState::test_a_gateway_with_nothing_in_it_says_so_rather_than_failing`, `::test_it_reports_the_account_session_when_there_is_one` |
| Trasa żywotności nie sięga do bazy — Wdrożenie sprawdza moduł | `test_meta.py::TestLiveness` (2 testy), potwierdzone `GET /` = 200 na produkcji |

### telegram-gateway-tools

| Requirement / Scenario | Proven by |
|---|---|
| Model wysyła, ale nie zakłada i nie wiąże — Powierzchnia narzędziowa | `test_tools_surface.py::test_the_expected_tools_and_no_others`, `::test_the_surface_holds_no_way_to_create_a_bot_or_bind_a_destination`, `::test_only_sending_is_announced_as_changing_anything` |
| Model widzi adresatów — Pierwsze powiadomienie w rozmowie | `test_tools_surface.py::test_a_model_can_learn_the_names_without_being_told_them`, `::test_sending_answers_with_the_identifier_telegram_gave_it` |
| Brak adresatów jest odpowiedzią — Brama pusta | `test_tools_surface.py::test_an_empty_gateway_is_answered_rather_than_failed`, `::test_a_mistyped_name_is_told_apart_from_an_empty_gateway` |

### telegram-gateway-caller-access

| Requirement / Scenario | Proven by |
|---|---|
| Moduł sprawdza wywołującego sam — Wywołujący spoza listy | `test_caller_access.py::test_a_stranger_is_refused_on_both_surfaces`, `::test_a_request_with_no_identity_is_refused`, `::test_an_empty_record_refuses_everyone`, `::test_the_person_signed_in_never_stands_in_for_the_application` |
| Rozłączne listy — Klient narzędziowy sięga po trasę REST | `test_caller_access.py::test_the_tool_caller_does_not_reach_the_routes_that_manage_bots`, `::test_the_rest_caller_does_not_reach_the_tool_surface`, `::test_the_recorded_rest_caller_reaches_the_contract` |
| Odmowa nie zależy od kolejności ładowania — Nowa trasa | `test_caller_access.py::test_a_path_nobody_recorded_belongs_to_no_surface`, `::test_every_published_rest_path_is_in_the_record`, `::test_the_probe_reaches_the_name_without_an_identity` |

### telegram-gateway-upstream-access

| Requirement / Scenario | Proven by |
|---|---|
| Wysyłka kanałem bota — Sesja konta jest skonfigurowana | `test_layering.py::test_the_sending_path_cannot_reach_the_account_session` (5 plików), `::test_mtproto_lives_in_one_file` |
| Sesja służy jednej rzeczy — Zakres użycia sesji | `test_layering.py::test_the_account_session_has_one_importer_besides_the_route`, `::test_the_conversation_reaches_no_peer_but_the_creator_bot`, `::test_the_creator_bot_is_a_constant_and_not_a_setting` |
| Sekret nie jest częścią adresu ani logu — Nieudane żądanie do Telegrama | `test_sending.py::TestTheTokenNeverReachesALog` (2 testy), cały `test_redaction.py` (9 testów) |
| Brak sesji nie blokuje startu — Start bez sesji | `test_config.py::TestTheAccountSession::test_all_three_absent_is_a_working_configuration`, `::test_a_partial_session_is_refused_at_startup` (3 przypadki), `::test_a_blank_line_reads_as_absent` |

### social-data-alerts

| Requirement / Scenario | Proven by |
|---|---|
| Powiadamia post powyżej progu — Post powyżej progu | `test_alerts.py::test_a_post_over_the_threshold_is_announced_once`, `TestTheMessageSpeaksPolish` (4 testy) |
| — Post poniżej progu | `test_alerts.py::test_a_post_under_the_threshold_is_not_announced` |
| Post bez odczytu nie powiadamia — Model nieskonfigurowany | `test_alerts.py::test_a_post_no_model_has_read_is_not_announced` |
| Znacznik po udanej wysyłce i jest ponowieniem — Wysyłka się nie udała | `test_alerts.py::test_a_failed_delivery_leaves_no_marker_and_the_next_pass_retries` (2 przypadki), `::test_one_post_failing_does_not_stop_the_rest` |
| — Post już zapowiedziany | `test_alerts.py::test_a_post_over_the_threshold_is_announced_once` |
| Brak bramy jest stanem wspieranym — Brama nieskonfigurowana | `test_alerts.py::TestBuild` (3 testy), `TestConfiguration` (4 testy) |

### strategy-alerts

| Requirement / Scenario | Proven by |
|---|---|
| Powiadamia wejście — Decyzja o zagraniu | `test_alerts.py::TestWhichDecisionIsWorthSaying::test_the_first_trade_for_a_pair_is_announced`, `TestThroughTheLoop::test_a_setup_is_announced_and_marked` |
| — Decyzja odmowna | `::test_a_refusal_is_never_announced`, `TestThroughTheLoop::test_a_refusal_says_nothing` |
| Ta sama decyzja nie powiadamia dwa razy — Wejście utrzymuje się | `::test_the_same_setup_standing_from_the_previous_bar_is_not_announced`, `::test_a_direction_that_flipped_is_a_new_setup`, `::test_a_trade_after_a_refusal_is_announced`, `TestThroughTheLoop::test_the_same_setup_on_the_next_bar_is_not_announced_again` |
| Znacznik po udanej wysyłce — Brama odmawia | `TestThroughTheLoop::test_a_failed_delivery_leaves_the_decision_recorded_and_unmarked` (2 przypadki) — **spełnione dosłownie, obietnica ponowienia nie**, patrz Findings |
| Brak bramy nie zatrzymuje oceniania — Brama nieskonfigurowana | `TestThroughTheLoop::test_no_gateway_leaves_the_decision_and_the_pass_untouched`, `tests/test_config.py` (partial forms) |

## Gaps

Trzy scenariusze nie były udowodnione testem w chwili tego przeglądu. Każdy jest tu wypisany, a nie
zagadany — dwa pierwsze zostały zamknięte zaraz po nim i mówią, czym.

- **`telegram-gateway-upstream-access`, oba pierwsze wymagania** — „wysyłka MUST iść tożsamością
  bota także wtedy, gdy sesja konta jest skonfigurowana" i „sesja MUST służyć wyłącznie rozmowie z
  botem-twórcą" trzymają się dziś **konstrukcją**: `sending.py` przyjmuje `BotApi` i o `CreatorBot`
  nic nie wie, a `creator.CREATOR_BOT` jest stałą, nie ustawieniem. Żaden test tego nie sprawdza, bo
  ten moduł nie ma `test_layering.py` — w odróżnieniu od `strategy` i `workbench`, które taki test
  mają. To jest ta klasa reguły, w której pudło jest ciche i **wychodzi poza system**: powiadomienie
  wysłane kontem operatora jest nieodróżnialne od tego, co operator napisał sam. Wart jednego testu
  czytającego importy, dokładnie tak jak `strategy/tests/test_layering.py`. **Zamknięte**:
  `modules/telegram-gateway/tests/test_layering.py` — sześć reguł, 36 przypadków, czytane z AST.
- **`telegram-gateway-bots`, „Start bez botów"** — połowa o działaniu bez botów jest pokryta
  (stan, narzędzia i wysyłka odmawiają zamiast się wywracać), połowa o „MUST NOT zakładać z własnej
  inicjatywy" nie ma asercji. Dziś prawdziwa z konstrukcji: jedyne wywołania `bots.create` są w
  trasie REST. **Zamknięte** tym samym testem importów —
  `test_nothing_creates_a_bot_on_its_own_initiative`.
- **„Nowa tabela jest od razu użyteczna"** — reguła o roli aplikacji będącej właścicielem schematu,
  ta sama co w każdym poprzednim module. Testy `db` chodzą jako superuser kontenera, więc nie mają
  jak jej zaobserwować; potwierdzeniem jest `grant-schema-ownership.sql` uruchomiony na bazie
  `telegram` w 15.1, z zerowym wynikiem zamykającego sprawdzenia i `has_schema_privilege(...)`
  odpowiadającym `true` dla `app-tradingcenter-telegram-gateway`.

Odroczone i będące pracą operatora, nie luką w kodzie:

- **15.4 — sprawdzenie wycofania.** Wymaga wyczyszczenia adresu bramy u wywołującego, `apply`,
  potwierdzenia, że `social-data` dalej zbiera i `strategy` dalej decyduje, i `apply` z powrotem.
  Dwa applye i przerwa w powiadomieniach. Kształt tego stanu przechodzą testy obu modułów
  (`TestBuild::test_collection_is_untouched_where_there_is_no_gateway`,
  `TestThroughTheLoop::test_no_gateway_leaves_the_decision_and_the_pass_untouched`), więc odroczone
  jest sprawdzenie na produkcji, nie sama zdolność.
- **Zakładanie botów jest wyłączone** — `telegram_account_session_configured = false`. Brama wysyła
  i odmawia zakładania, co jest stanem wspieranym i przetestowanym, nie długiem. Włączenie wymaga
  trzech sekretów z `my.telegram.org` i stringa sesji z interaktywnego logowania na numer operatora.
