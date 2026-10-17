## Verdict

Wszystko z `tasks.md` jest zrobione w kodzie i w pięciu PR-ach (#295–#299), poza tym, co z natury jest ruchem operatora albo drugiego wdrożenia: konto Telegrama z numerem i 2FA, `api_id`/`api_hash`, `TELEGRAM_SESSION_KEY` w środowisku `vps`, pierwsze logowanie i pierwszy bot (5.5), weryfikacja po scaleniu (5.3) i wycofanie `ALERT_DESTINATION` w osobnym wdrożeniu (5.4, zgodnie z design.md). **Żaden krok rozmowy z prawdziwym Telegramem nie był wykonany** — Telethon jest za protokołem `AccountPlatform` i w testach udają go fałszywki; pierwszy prawdziwy test to pierwsze logowanie operatora. Nie należy brać za przeoczenie: migracja `0003` zamiast jednej (konto doszło z grupą 2), zasianie `*` przy starcie zamiast w migracji (migracja nie widzi ustawień procesu), `TELEGRAM_SESSION` zdjęte od razu (nie czekało na „drugie wdrożenie”, bo nic go nie czyta), i to, że kilka luk z przejścia po specyfikacjach zamknął commit w ostatnim PR, a nie w PR-ach swoich grup.

## Verified

| Co | Wynik |
|---|---|
| `uv run pytest` w `modules/workbench` (przed ostatnim PR, po każdej grupie) | 2977 → 3015 → 3021 passed, 11 skipped |
| `uv run pytest` w `modules/workbench` na szczycie stosu | patrz „Wynik końcowy” niżej |
| `pnpm test` w `modules/terminal` | 911 passed (76 plików) |
| `uv run pytest` w `scripts/` | 235 passed, 1 skipped |
| `ruff check .`, `pyright` (workbench), `ruff check` (scripts), `pnpm lint`, `pnpm typecheck`, `pnpm build` | czyste |
| `openspec validate telegram-bots-from-the-terminal --strict` | valid |
| `pnpm contract:generate` | zmienił tylko nowy `contract.telegram.generated.ts`; sześć pozostałych bez zmian |
| `contract:check` | tylko w CI (trwa kilka minut, uruchamia `uv` osiem razy) |

## Findings

Z przejścia po diffie, po weryfikacji; „FIXED” = naprawione w tej zmianie.

| Severity | Where | Finding | Status |
|---|---|---|---|
| Średnie | `telegram_gateway/account.py` `TelethonLoginClient` | Błąd sieci (`OSError`, timeout) przy `connect`/`sign_in` nie był `RPCError`, więc wychodził jako nieobsłużony wyjątek — 500 bez słów, w środku logowania. | FIXED — mapowane na `LoginRefused("Telegram could not be reached…")`, logowanie zostaje otwarte (commit „closing the gaps…” w PR 5) |
| Niskie | `strategy` — brak testu na `GatewayUnassigned` | Zachowanie (decyzja zapisana, bez znacznika, następna zmiana ogłaszana) było w kodzie, ale nie pod testem. | FIXED — `test_a_purpose_nobody_hears_is_a_state_…` (PR 5) |
| Niskie | terminal — link startowy | Dialog pokazywał „ważne do HH:MM”, ale po wygaśnięciu nie mówił nic, a spec wymaga (scenariusz „Odnośnik wygasł”). | FIXED — „Odnośnik wygasł” + „Wydaj nowy link” jedną akcją (PR 5) |
| Niskie | terminal — pusta brama | Zakładka nie mówiła „od czego zacząć”, tylko pokazywała puste sekcje. | FIXED (PR 5) |
| Info | `routers/account.py` `code` | Gdy zapis sesji do bazy zawiedzie po udanym logowaniu w Telegramie, tożsamość jest już zrzucona (login zamknięty) i operator zaczyna od numeru. Kosztuje jedno logowanie, nie niczego nie zostawia w złym stanie. | Zostaje, świadomie |

## Spec coverage

`F` = plik w `modules/workbench/tests/telegram/`, `T` = `modules/terminal/src/telegram/`.

| Requirement / Scenario | Proven by |
|---|---|
| purposes · Producent adresuje celem, cel otwarty — Cel nigdy niewidziany | `F test_purposes.py::TestOnTheWire::test_a_purpose_reaches_the_wire_and_names_where_it_went` |
| purposes · … — Cel o niedozwolonym kształcie | `test_purposes.py::TestOnTheWire::test_exactly_one_address_in_a_valid_shape`, `::TestTheShapeOfAPurpose::test_anything_else_is_refused_naming_the_shape` |
| purposes · Brama pamięta cele — Pierwsza wiadomość z nowym celem | `test_purposes.py::TestSendingByPurpose::test_a_purpose_nobody_hears_is_noted_and_refused_apart_from_every_other_refusal` |
| purposes · … — Cel zgłoszony z góry | `test_purposes.py::TestOnTheWire::test_an_announced_purpose_is_listed_before_any_event`, `test_producers_pairing.py::test_a_producer_over_the_in_process_door_waits_until_the_purpose_is_assigned` |
| purposes · … — treść nie jest zapamiętana | `test_purposes.py::TestSendingByPurpose::test_the_message_text_is_never_kept` |
| purposes · Jeden cel, jeden adresat — Przepięcie celu | `test_purposes.py::TestTheStatementAgreesWithTheRule::test_assigning_a_key_again_moves_it` (nic nie jest cache'owane: każda wiadomość pyta bazę) |
| purposes · … — Przypisanie do adresata przed tapnięciem | `test_purposes.py::TestSendingByPurpose::test_a_recipient_that_has_not_tapped_yet_can_be_assigned_but_not_sent_to` |
| purposes · Najdłuższy przedrostek — łapie / dokładniejsze wygrywa / nie tnie segmentu | `test_purposes.py::TestWhichKeyDecides::*`, `::TestTheStatementAgreesWithTheRule::test_the_recipient_is_the_one_the_rule_names` |
| purposes · Cel bez adresata to odpowiedź — Brak przypisań | `test_purposes.py::TestOnTheWire::test_an_unheard_purpose_answers_409_with_its_own_code` |
| purposes · Przypisania zmienia tylko operator — Model szuka narzędzia | `test_tools_surface.py::test_the_surface_holds_no_way_to_create_a_bot_or_bind_a_destination` |
| account · Logowanie w krokach — Konto z hasłem / Zły kod / Przerwane restartem | `test_account.py::TestLoggingInOverTheWire::test_an_account_with_a_password_walks_one_more_step`, `::test_a_wrong_code_is_telegrams_refusal_and_the_login_stays_open`, `::TestTheLoginInMemory::test_a_code_with_no_login_is_a_refusal_about_the_login`, `::test_a_login_expires_after_ten_minutes` |
| account · Sesja zaszyfrowana — Zrzut bazy / Brak klucza | `test_account.py::TestWhatTheStoredAccountCanDo::test_a_login_is_stored_encrypted_and_usable`, `::TestLoggingInOverTheWire::test_without_the_key_nothing_is_asked_of_telegram` |
| account · Sesja, której nie da się użyć — Klucz zmieniony / Sesja zabita z telefonu | `test_account.py::TestWhatTheStoredAccountCanDo::test_a_changed_key_is_a_state_that_names_the_key`, `::TestTheOwnerAccountDrivesTheBots::test_a_session_ended_from_the_phone_is_refused_and_remembered` |
| account · Wylogowanie — Telegram nie odpowiada | `test_account.py::TestLoggingOut::test_an_unreachable_telegram_still_forgets_the_account` |
| account · Kod, hasło i sesja nie wychodzą — Odczyt stanu | `test_account.py::TestLoggingInOverTheWire::test_neither_the_code_nor_the_password_reaches_a_log`, `::test_the_state_says_whose_account_it_is_and_never_the_session` |
| delivery (MOD) · adresowana nazwą — Nieznany / Adresat i cel naraz / Wiadomość celem | `test_sending.py::TestSending::test_an_unknown_name_is_refused_without_a_request`, `test_purposes.py::TestOnTheWire::test_exactly_one_address_in_a_valid_shape`, `::test_a_purpose_reaches_the_wire_and_names_where_it_went` |
| bots (MOD) · Brak sesji — Wysyłka / Zakładanie bez sesji | `test_rest.py::TestBots::test_creating_one_with_no_account_logged_in_says_so`, `test_bots.py::TestCreating::test_without_a_session_nothing_is_said_to_telegram` |
| bots (MOD) · Rotacja zachowuje wiązania — przy związanym adresacie / odpowiedź bez tokenu | `test_account.py::TestRotatingAToken::test_the_new_token_replaces_the_old_and_the_destinations_survive`, `::test_a_reply_without_a_token_changes_nothing`, `::test_a_token_that_belongs_to_another_bot_is_not_taken` |
| bots (MOD) · Bot z przypisaniem nie znika | `test_purposes.py::TestOnTheWire::test_a_bot_with_a_heard_destination_is_refused_before_the_creator_bot_is_asked` |
| upstream-access (MOD) · Zakres użycia sesji / Nieudane logowanie | `test_layering.py::*` (sesja ma dwóch importerów, ścieżka wysyłki do niej nie sięga), `test_account.py::…::test_neither_the_code_nor_the_password_reaches_a_log` |
| destinations · Adresat z przypisaniem nie znika | `test_purposes.py::TestOnTheWire::test_a_destination_that_is_heard_cannot_be_removed_and_the_refusal_names_the_key`, `::TestRemovingWhatIsStillHeard::test_the_schema_holds_when_a_route_forgets` |
| api (MOD) · tylko w REST / trasa stanu — Model sięga po zarządzanie / Cele bez adresata | `test_tools_surface.py::*`, `test_purposes.py::TestSendingByPurpose::test_a_purpose_nobody_hears_is_noted_…` (`purposes_unheard`), `test_rest.py::TestState::*` |
| social-data-alerts (MOD) · Brama nieskonfigurowana | `tests/social/test_alerts.py::TestPurposes::test_a_purpose_nobody_hears_leaves_no_marker_and_is_said_by_the_state`, `::test_assigning_later_announces_what_waited_and_the_state_recovers` |
| strategy-alerts (MOD) · Brama nieskonfigurowana | `tests/strategy/test_alerts.py::TestThroughTheLoop::test_a_purpose_nobody_hears_is_a_state_the_decision_survives_and_the_next_change_announces` |
| youtube (producent, poza deltami tej zmiany) | `tests/youtube/test_alerts.py::test_a_purpose_nobody_hears_waits_without_a_marker_and_the_state_says_so` |
| terminal · Zakładka pokazuje — Brama bez niczego / Brama nieosiągalna | `T TelegramView.test.tsx::says where to begin on a door with nothing in it…`, `::says the door does not answer, and does not show its lists as empty` |
| terminal · Logowanie ostrzega — Logowanie z hasłem | `T TelegramView.test.tsx::logs the account in through Telegram's steps…` (ostrzeżenie o koncie dedykowanym i pole hasła w tym samym przebiegu), `::names the settings the server lacks…` |
| terminal · Bot powstaje i prowadzi do aktywacji — Tapnięcie / Odnośnik wygasł | `T TelegramView.test.tsx::shows a code for the start link and turns the address on when the tap arrives`, `::says a start link has expired and issues a new one in one action` |
| terminal · Przypisania na liście celów — Cel dziedziczy adresata | `T TelegramView.test.tsx::says first, and loudly, what nobody hears…`, `::assigns a purpose from its own row`, `T present.test.ts::originOf` |
| terminal · Nieodwracalne pytają, odmowa mówi dlaczego — Usunięcie bota z przypisaniem | `T TelegramView.test.tsx::keeps the door's reason in the dialog when it refuses to remove a bot that is still heard`, `T telegramApi.test.ts::reads a refusal to remove as a refusal…` |

## Gaps

- **Telethon nie był wykonany nigdy** (`TelethonLoginClient`, `TelethonPlatform.log_out`, `TelethonCreatorBot.revoke`). Pokrywa go tylko protokół i fałszywki; mapowanie wyjątków Telethona na słowa (`_telethon_words`) nie ma testu jednostkowego. Pierwsze prawdziwe logowanie operatora jest jego testem.
- **Start z zapisaną sesją, której klucz się zmienił** — scenariusz „brama MUST wstać” jest sprawdzony na poziomie `account.view` (stan `needs_login`), nie jako start całej aplikacji z takim wierszem w bazie.
- **Kolejność w tej samej sekundzie**: dwa równoległe `POST /messages` z nowym celem robią dwa upserty tego samego klucza głównego; wynik jest zgodny (ostatni `last_seen` wygrywa), ale nie jest testowany współbieżnie.
- **Przeglądarka**: zakładka nie była oglądana w przeglądarce z prawdziwą bramą; QR i wykrycie tapnięcia sprawdzone w jsdom z fałszywymi timerami.

## Wynik końcowy

Pełny `uv run pytest` w `modules/workbench` na szczycie stosu (16 października 2026, 12 min): **3022 passed, 11 skipped, 1 failed** — `tests/teams/test_scheduler_clock.py::test_a_revision_naming_a_model_outside_the_catalogue_is_skipped` (`assert 0 == 1`). To pakiet `teams`, którego ta zmiana nie dotyka, a test **przechodzi sam** (`tests/teams/test_scheduler_clock.py`: 14 passed) — wygląda na zależność od czasu pod obciążeniem maszyny podczas długiego przebiegu. Nie badałem go dalej; jeśli powtórzy się w CI, to osobna sprawa.
