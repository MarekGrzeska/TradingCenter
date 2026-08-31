## Verdict

Moduł `social-data` stoi w całości — zbiór, wzbogacenie, kontrakt REST, cztery narzędzia MCP, zapis
dostępu, obie zakładki, stack lokalny, CI i infrastruktura. **Wdrożenie jest jedyną rzeczą, której ta
gałąź nie robi i nie może zrobić**: `apply`, założenie principala i `grant-schema-ownership.sql` na
bazie `social` są czynnością operatora (`design.md` → Migration Plan), więc zadanie 11.4 zostaje
niezaznaczone celowo, a nie przez zapomnienie.

Dwie rzeczy, których późniejszy czytelnik nie powinien wziąć za przeoczenie. **Klucz modelu jest
współdzielony z rozmową** (`openai-api-key` w Key Vault) zamiast być trzecim sekretem — decyzja
operatora podjęta po napisaniu propozycji, więc koszt odczytów nie ma dziś własnej linii na
rachunku; rozdzielenie to jeden wpis i jedna edycja. I **`polymarket-data` jest tu punktem
odniesienia, nie wzorem do skopiowania**: tam narzędzia piszą, bo istnieje lista obserwacji, tutaj
nie ma czego dodawać, więc zestaw wyłącznie czyta — to inny wniosek z tej samej zasady, a nie
zaostrzenie reguły.

## Verified

Uruchomione na tej gałęzi, nie deklarowane:

| Co | Wynik |
|---|---|
| `modules/social-data`: `uv run ruff check .` · `uv run pyright` · `uv run pytest -q` | czysto · 0 błędów · **82 passed** (unit + `-m db` na kontenerze testcontainers) |
| `modules/workbench`: `uv run pytest -q -m "not db"` · `ruff` · `pyright` | **444 passed** · czysto · 0 błędów |
| `modules/terminal`: `pnpm test` · `typecheck` · `lint` · `contract:check` | **811 passed** · czysto · czysto · „Every contract is up to date" |
| `modules/pocket`: `pnpm test` · `typecheck` · `lint` · `contract:check` | **66 passed** · czysto · czysto · „The contract is up to date" |
| `scripts`: `uv run pytest -q` | **149 passed, 3 skipped** (w tym `test_guide_ceiling`, `test_dev`, `test_deploy_workflows`) |
| `infra`: `terraform init -backend=false` · `validate` · `fmt -check -recursive` | Success · Success · bez zmian |
| `openspec validate social-data-collects-the-posts --strict` | valid |

Testy `live` nie były uruchamiane — czytają cudzy feed przez sieć i zostają za `--run-live`.

**`terraform.yml` → `plan` na PR jest czerwony i to jest stan przewidziany, nie regresja.** Plan
kończy się na `Plan: 9 to add, 16 to change, 0 to destroy` i dopiero potem odmawia:

```
Error: Invalid for_each argument
azurerm_linux_web_app.social_data.possible_outbound_ip_address_list is a list of string,
known only after apply
```

Reguła firewalla per aplikacja robi `for_each` po adresach wychodzących App Service, których przed
`apply` nie ma — dokładnie to, co komentarz przy tej regule zapowiada („first convergence needs two
applies"). Każdy poprzedni nowy moduł przeszedł przez to samo: `add-trading-tools`,
`a-strategy-is-a-catalogue-entry`. Droga wyjścia jest ta z `database.tf`:
`terraform apply -target=azurerm_linux_web_app.social_data` raz, potem normalny apply — i od tego
momentu plan liczy się do końca. Nie ma tu nic do naprawienia w kodzie; jedyną alternatywą byłoby
skasowanie reguły nazwanej po aplikacji, a jej adresy pokrywają się z istniejącymi i cała jej
wartość to ślad, że taka aplikacja tu jest.

## Findings

Dwa z przeglądu diffu, oba naprawione przed napisaniem tego dokumentu.

| Severity | Where | Finding | Status |
|---|---|---|---|
| Poważne | `social_data/ingest.py:133` | Pass, w którym jedna z dwóch dat okna nie odpowiedziała, **zapisywał połowę, która dojechała**, i jednocześnie zapisywał porażkę. Komentarz obok mówił „half a window silently written is worse", a kod robił dokładnie to; specyfikacja (`social-data-ingest`, „Źródło nie odpowiada") mówi, że archiwum zostaje nietknięte. Ugryzłoby przy oknie przecinającym północ: pół doby wpisane, `last_success_at` nieruszone, a następny przebieg widzi te posty jako już zebrane i nigdy nie dociąga reszty. Poprzedni test przechodził trywialnie, bo źródło w nim wywracało się na pierwszej dacie. | **FIXED** — nic nie jest zapisywane, gdy pass się nie udał; test `test_a_window_half_answered_writes_nothing_at_all` |
| Drobne | `social_data/tools/posts.py:117` | `read_post` dla nieistniejącego posta zwracał `None`, co u klienta MCP jest **odpowiedzią bez treści strukturalnej** — nieodróżnialną od narzędzia, które się wywróciło. Model nie miał jak powiedzieć „tego posta tu nie ma". | **FIXED** — odmowa w kształcie, którego używa `polymarket-data` (`refused` + `do_first`); test `test_asking_for_a_post_that_is_not_there_is_an_answer_not_an_error` |

Oba w commicie kończącym przegląd. Poza nimi diff nie dał nic, co przetrwałoby sprawdzenie.

## Spec coverage

Ścieżki testów skrócone: `sd/` = `modules/social-data/tests/`, `t/` = `modules/terminal/src/`.

### social-data-ingest

| Requirement / Scenario | Proven by |
|---|---|
| Zbiór jest czynnością własną modułu → Odczyt nie dokłada danych | `sd/test_ingest.py::test_a_read_never_adds_to_the_archive` |
| → Pętla pracuje bez pytania | `sd/test_ingest.py::test_the_loop_collects_without_anybody_asking` |
| Okno obejmuje każdą datę → Okno przecina północ | `sd/test_ingest.py::test_a_pass_asks_the_source_for_both_dates_a_window_crosses`, `::test_a_post_published_before_midnight_is_collected` |
| Zbiór zaczyna się w dniu wdrożenia → Pierwsze uruchomienie | `sd/test_ingest.py::test_nothing_earlier_than_the_window_is_ever_asked_for` |
| → Pytanie o okres sprzed zbioru | `sd/test_api.py::test_the_state_says_since_when_it_collects_and_whether_a_model_is_configured` (pole `collecting_since` w odpowiedzi) |
| Milczące źródło → Źródło nie odpowiada | `sd/test_ingest.py::test_a_source_that_will_not_answer_leaves_the_archive_and_the_moment_alone`, `::test_a_window_half_answered_writes_nothing_at_all` |
| → Dzień bez postów | `sd/test_ingest.py::test_a_quiet_day_still_moves_the_moment_of_the_last_collection` |
| Źródło jest wymienne → Dołożenie źródła | **luka** — patrz Gaps |
| → Ten sam identyfikator w dwóch źródłach | `sd/test_store.py::test_two_sources_may_number_their_posts_the_same_way` |

### social-data-store

| Requirement / Scenario | Proven by |
|---|---|
| Tożsamość to para → Post wraca w kolejnym przebiegu | `sd/test_store.py::test_the_same_post_collected_twice_is_stored_once`, `sd/test_ingest.py::test_a_second_pass_over_the_same_posts_inserts_nothing` |
| → Kolizja identyfikatorów między źródłami | `sd/test_store.py::test_two_sources_may_number_their_posts_the_same_way` |
| Treść jako tekst → Post ze znacznikami i encjami | `sd/test_truth_social.py::test_the_text_arrives_without_tags_and_with_entities_resolved`, `::test_cleaning_removes_tags_before_resolving_entities` |
| Odczyt stoi obok posta → Post bez odczytu | `sd/test_store.py::test_posts_awaiting_a_reading_are_the_unread_ones_inside_the_window`, `sd/test_api.py::test_a_post_without_a_reading_carries_the_fields_anyway` |
| Rachunek przy poście → Ponowne wzbogacenie tego samego posta | `sd/test_store.py::test_the_bill_survives_the_reading_it_paid_for` |
| Zebrany post nie znika → Archiwum starzeje się | `sd/test_store.py::test_a_window_answers_newest_first_and_excludes_what_falls_outside` (odczyt po dacie bez granicy wieku) — **częściowo**, patrz Gaps |
| → Prośba o skasowanie | `sd/test_api.py::test_the_contract_publishes_no_route_that_writes`, `sd/test_tools_surface.py::test_no_tool_on_this_surface_changes_anything` |

### social-data-enrichment

| Requirement / Scenario | Proven by |
|---|---|
| Cudzy osąd, ostemplowany → Odpowiedź niesie stempel | `sd/test_enrichment.py::test_a_reading_is_written_with_the_model_that_produced_it`, `sd/test_api.py::test_a_reading_reaches_the_wire_with_the_model_that_produced_it` |
| → Model zwraca coś spoza zakresu | `sd/test_enrichment.py::test_an_answer_this_module_will_not_store_is_refused`, `sd/test_store.py::test_a_score_outside_one_to_ten_is_refused_by_the_schema` |
| Ocena przy zbiorze → Pytanie o posty o wysokim wpływie | `sd/test_tools_surface.py::test_narrowing_by_score_reads_a_stored_reading`, `sd/test_store.py::test_a_window_narrows_by_source_score_and_topic` |
| Nadpisywanie → Post oceniony ponownie | `sd/test_store.py::test_a_reading_is_saved_with_its_stamp_and_overwritten_whole` |
| Brak modelu jest wspierany → Wdrożenie bez klucza | `sd/test_enrichment.py::test_without_a_key_there_is_no_enrichment_and_that_is_not_a_refusal`, `sd/test_api.py::test_the_state_says_since_when_it_collects_and_whether_a_model_is_configured` |
| Nieudane wzbogacenie → Model odmawia w środku serii | `sd/test_enrichment.py::test_one_posts_failure_costs_that_post_only`, `::test_a_model_failure_does_not_stop_the_collection_pass` |
| Wzbogacane jest okno → Tysiąc postów sprzed okna | `sd/test_enrichment.py::test_posts_older_than_the_window_are_never_read`, `::test_a_pass_stops_at_the_ceiling_on_what_it_may_spend` |

### social-data-api

| Requirement / Scenario | Proven by |
|---|---|
| Kontrakt wyłącznie czyta → Klient szuka drogi do wymuszenia zbioru | `sd/test_api.py::test_the_contract_publishes_no_route_that_writes` |
| Okno jawne → Pytanie o okno z zawężeniem | `sd/test_api.py::test_a_window_answers_with_its_own_edges_and_the_posts_in_it` |
| → Okno bez sensu | `sd/test_api.py::test_a_window_that_ends_before_it_starts_is_refused_with_a_reason` |
| Puste pole zamiast braku pola → Post niewzbogacony | `sd/test_api.py::test_a_post_without_a_reading_carries_the_fields_anyway`, `sd/test_openapi.py::test_a_response_model_declares_every_field_it_always_sends` |
| Moduł mówi, w jakim jest stanie → Archiwum stoi | `sd/test_api.py::test_an_archive_that_has_not_collected_for_a_long_time_says_so` |
| → Wdrożenie bez modelu | `sd/test_api.py::test_the_state_says_since_when_it_collects_and_whether_a_model_is_configured` |
| Kontrakt jest źródłem typów → Zmiana kształtu odpowiedzi | `sd/test_openapi.py::test_the_document_describes_every_shape_the_screens_read` + `pnpm contract:check` w obu front-endach (CI: joby `terminal` i `pocket` odpalane przez `social_data/contract.py`) |

### social-data-caller-access

| Requirement / Scenario | Proven by |
|---|---|
| Żądanie niesie tożsamość → Żądanie bez tożsamości | `sd/test_caller_access.py::test_a_request_with_no_identity_is_refused` |
| Tożsamość rozstrzyga powierzchnię → Wołający narzędzi sięga po REST | `sd/test_caller_access.py::test_the_tool_caller_does_not_reach_the_contract`, `::test_the_screens_reach_the_contract` |
| → Ścieżka spoza zapisu | `sd/test_caller_access.py::test_a_path_nobody_recorded_belongs_to_no_surface`, `::test_every_published_rest_path_is_in_the_record` |
| Aplikacja, nie osoba → Token delegowany operatora | `sd/test_caller_access.py::test_the_person_signed_in_never_stands_in_for_the_application` |
| Pusty zapis odmawia → Wdrożenie przed konfiguracją | `sd/test_caller_access.py::test_an_empty_record_refuses_everyone` |
| Zdrowie bez tożsamości → Sonda po wdrożeniu | `sd/test_caller_access.py::test_the_probe_reaches_health_and_the_name_without_an_identity`, `::test_the_open_paths_are_exactly_two_and_carry_no_data` |

### social-data-tools

| Requirement / Scenario | Proven by |
|---|---|
| Zestaw wyłącznie czyta → Lista narzędzi nie zawiera zapisu | `sd/test_tools_surface.py::test_no_tool_on_this_surface_changes_anything`, `::test_the_expected_tools_and_no_others` |
| → Narzędzie sięga po zapis | **luka** — patrz Gaps |
| Domyka drogę od pytania do treści → Pytanie o dzień wstecz | `sd/test_tools_surface.py::test_a_window_names_its_own_edges`, `::test_narrowing_by_score_reads_a_stored_reading`, `::test_asking_for_a_post_that_is_not_there_is_an_answer_not_an_error` |
| Skrót vs pełna treść → Doba postów w jednym wywołaniu | `sd/test_tools_surface.py::test_a_list_carries_an_excerpt_and_says_there_is_more`, `::test_the_whole_text_is_a_separate_call` |
| Oryginał domyślnie → Domyślne wywołanie | `sd/test_tools_surface.py::test_a_model_gets_the_original_unless_it_asks_for_the_translation` |
| Status odróżnia ciszę → Archiwum stoi, a model pytany | `sd/test_tools_surface.py::test_the_status_tool_tells_a_stalled_archive_from_a_quiet_day` |

Budżet powierzchni: `::test_the_surface_stays_within_what_a_conversation_pays_for_it` — zmierzone
7 771 znaków dla czterech narzędzi przy suficie 9 000.

### terminal-social

| Requirement / Scenario | Proven by |
|---|---|
| Zakładka pokazuje dobę → Otwarcie zakładki | `t/social/SocialView.test.tsx::shows a scored post without a click and folds the rest away` (lista + nazwane okno) |
| Wysoki wpływ bez klikania → Doba z jednym ważnym postem | ten sam test + `t/social/impact.test.ts::puts what a model scored at or above the threshold in front` |
| → Doba bez ważnych postów | `t/social/SocialView.test.tsx::says a day held nothing scored rather than looking empty` |
| Polski tekst, gdy jest → Post bez tłumaczenia | `t/social/SocialView.test.tsx::shows the Polish reading when there is one and the original when there is not` |
| → Post bez oceny | `t/social/SocialView.test.tsx::shows no score at all on a post no model has read`, `t/social/impact.test.ts::separates unread from every score` |
| Ekran mówi, gdy stoi → Zbiór stanął | `t/social/SocialView.test.tsx::names a stalled archive instead of letting an empty list speak for it` |
| → Wdrożenie bez modelu | `t/social/SocialView.test.tsx::says the readings are off rather than showing unscored posts unexplained` |
| Lista odświeża się sama → Odświeżenie nie dochodzi | `t/social/SocialView.test.tsx::keeps the posts on screen when a refresh fails, and says the read failed` |

Pocket nie ma zdolności w `openspec/specs/` (proposal mówi dlaczego), ale jego ekran ma testy tego
samego kształtu: `modules/pocket/src/social/PostsScreen.test.tsx` — pięć, w tym stan zatrzymanego
archiwum i brak modelu.

## Gaps

1. **`social-data-ingest` → „Dołożenie źródła"** nie ma testu wprost. Najbliżej jest
   `sd/fakes.py::FakeSource` — druga, niezależna implementacja protokołu, używana w całym
   `test_ingest.py` bez dotykania `providers/truth_social.py`; to pokazuje, że pętla nie zna swojego
   źródła, ale nie że dołożenie drugiego niczego nie rusza. Test wart napisania dopiero z drugim
   prawdziwym źródłem — dziś sprawdzałby atrapę przeciwko atrapie.
2. **`social-data-tools` → „Narzędzie sięga po zapis"** nie ma testu i **zostaje luką świadomie**.
   Sprawdzenie, że kod narzędzia nie woła funkcji zapisującej, wymaga czytania źródła albo importów,
   czego reguła 3 z `CLAUDE.md` („żadnych testów implementacji") zabrania. Co jest sprawdzane:
   deklaracje (`readOnlyHint`) i to, że kontrakt REST nie publikuje żadnej trasy piszącej. Ta sama
   luka istnieje w `polymarket-data-tools` i z tego samego powodu.
3. **`social-data-store` → „Archiwum starzeje się"** jest pokryte częściowo: żaden test nie trzyma
   posta przez tydzień. Twarda część — że nie ma czym skasować — jest pokryta dwoma testami
   wymienionymi wyżej, a kasowania po wieku nie ma w kodzie w ogóle.
4. **Zadanie 11.4 (kolejność wdrożenia) nie zostało wykonane** i nie jest luką w testach, tylko
   czynnością operatora: `apply`, `pgaadauth_create_principal_with_oid` i
   `scripts/grant-schema-ownership.sql` na bazie `social`, w tej kolejności, **przed** pierwszym
   deployem obrazu. Bez tego moduł wstaje, nie może założyć tabel i sonda wdrożenia to mówi.
