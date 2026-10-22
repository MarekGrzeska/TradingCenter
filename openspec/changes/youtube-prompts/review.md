## Verdict

Prompty są danymi: tabele `prompts` i `prompt_versions`, zasiany prompt `Rynkowy` bez usuwania, jeden kształt odczytu
(`summary_pl`, `text`, `impact_score`), kolejny odczyt filmu wybranym promptem, sekcja Prompty w zakładce YouTube i wybór promptu w dialogach.
Wiedza o instrumentach zniknęła wszędzie (filtr, `instrument_sentiment`, atrybut zdarzenia, linia w wiadomości). Świadomie
niedokończone: wdrożenie (zadanie 5.2) i poprawa reguł alertów po wdrożeniu — na produkcji jest jedna reguła `youtube.film.read`
z pustym filtrem i szablonem `{text}`, więc nic nie wymaga poprawy (sprawdzone 22 października 2026).

## Verified

- `uv run pytest` w `modules/workbench`: 2928 passed, 11 skipped przed poprawkami z review; po nich `tests/youtube` 242 passed (pełny zestaw, z testami `db` na PostgreSQL 17 w kontenerze).
- `uv run ruff check .` i `uv run pyright`: bez uwag, 0 błędów.
- `pnpm typecheck`, `pnpm lint`, `pnpm test` w `modules/terminal`: 948 passed (+1 po review) (80 plików); `pnpm contract:check`: aktualny.
- `contract-sync`: zmienił się tylko `contract.youtube.generated.ts`; pocket i snapshot trading-mcp bez zmian.
- `openspec validate youtube-prompts --strict`: poprawna.
- Migracja `0003` przeszła na bazie z odczytem w starym kształcie (wszystkie pola) oraz w dół i w górę (`test_migration.py`).
  Na produkcji: 28 odczytów, 1 kanał — nie sprawdzano na kopii produkcyjnej.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| medium | `ingest.py` `_read_with` | Odczyt zamówiony ręcznie i odrzucony przez model zwiększał `reading_failures` filmu, a ten licznik zatrzymuje pętlę po `READING_MAX_FAILURES`: film mógł zostać bez odczytu własnym promptem, choć ten nie zawiódł. | FIXED — zamówiony odczyt nie liczy się do prób (`counts=False`), test `…is_not_one_of_the_films_attempts` |
| medium | `routers/videos.py`, `prompts.order_reading` | `POST /videos/{id}/readings` odpowiadał 202 bez skonfigurowanego modelu i nic się nie działo. | FIXED — odmowa „no model is configured”, test `…no_model_is_configured` |
| medium | `ingest.py` `read_with` | Dzienny limit tokenów sprawdzany tylko przy zamówieniu, nie przy wykonaniu; kilka kliknięć tego samego odczytu mnożyło koszt. | FIXED — sprawdzenie przy wykonaniu i brak duplikatów (`_ordered`), test `…does_not_run_after_it` |
| medium | `terminal/agent/MessageBody.tsx` | Tekst odczytu to Markdown napisany przez model po obcej transkrypcji; obrazek `![](https://…?d=…)` byłby pobrany przez przeglądarkę. | FIXED — `img` nie ładuje nic, pokazuje alt; test w `MessageBody.test.tsx` (dotyczy też czatu agenta) |
| low | `store.py` `update_prompt`, `prompts.update` | Dwa równoległe zapisy tego samego promptu brały ten sam numer wersji; błąd klucza głównego raportowany jako „nazwa zajęta” z `None`. | FIXED — blokada wiersza promptu na czas zapisu; komunikat rozróżnia przypadki |
| low | `prompts.delete` | Sprawdzenie przypisań i usunięcie w osobnych zapytaniach: kanał przypisany w międzyczasie zostawał z usuniętym promptem. | FIXED w oknie sprawdzenia — usunięcie jednym zapytaniem z `NOT EXISTS`; test `…took_a_moment_ago…`. Pozostaje mikrookno przy równoległym PATCH kanału (jeden operator) |
| low | `terminal/WatchPanels.tsx` | Wybór „domyślny” przy niewczytanych promptach wysyłał pusty PATCH bez błędu. | FIXED — lista wyboru wyłączona, dopóki prompty się nie wczytają |
| low | `store.py` `analysed_for_alert` | Zapytanie czytało pełny tekst odczytu (do 20 kB) dla każdego ogłaszanego filmu. | FIXED — `result - 'text'` |
| low | `prompts.create` | Limit liczony przez wczytanie wszystkich promptów z treścią. | FIXED — `count(*)`; kontrola i wstawienie nadal nie są atomowe (limit miękki) |
| low | komentarze | Nowe docstringi dłuższe niż dwie linie, wbrew CLAUDE.md. | FIXED w `prompts.py`, `analysis.py`, `store.py` |
| low | `migrations/youtube/versions/0003` `downgrade` | Zdejmuje schemat, nie treść; stary obraz na nowym schemacie nie wystartuje. Opisane w `design.md`. | accepted |
| low | `store.py` `prompt_to_read_with` | Film zakolejkowany z promptem usuniętym potem przez operatora jest czytany jego ostatnią wersją. | accepted |
| info | `analysis.py` | Model może zignorować ramkę i odpowiedzieć poza schematem — odpowiedź nie zostanie zapisana, tokeny pójdą. | accepted |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| youtube-data-prompts: Prompt jest daną operatora i ma wersje / Edycja promptu z odczytami | `test_prompts.py::test_a_reading_names_the_version_it_was_made_by_after_the_words_change`, `test_new_words_make_a_new_version_and_a_new_name_or_the_same_words_make_none` |
| … / Nazwa już zajęta | `test_prompts.py::test_a_name_in_use_is_refused_in_any_case_and_is_free_again_once_deleted`, `test_api.py::test_the_operator_writes_edits_and_deletes_prompts_and_the_wire_says_why_not` |
| Zawsze istnieje co najmniej jeden prompt / Próba usunięcia zasianego | `test_prompts.py::test_the_seeded_prompt_is_edited_like_any_other_and_cannot_be_deleted`, `test_api.py::…wire_says_why_not` |
| … / Edycja zasianego promptu | `test_prompts.py::test_the_seeded_prompt_is_edited_like_any_other_and_cannot_be_deleted` |
| (wszystko z profilem `market` wskazuje zasiany) | `test_migration.py::test_a_reading_in_the_old_shape_keeps_everything_it_said_and_everything_points_at_the_seeded_prompt` |
| Usunięcie promptu nie gubi odczytów / Prompt przypisany do kanału | `test_prompts.py::test_a_prompt_a_channel_reads_by_cannot_be_deleted_and_the_refusal_names_it`, `test_api.py::test_a_prompt_says_which_channels_read_by_it_and_cannot_be_deleted_while_one_does` |
| … / Prompt z odczytami usunięty | `test_prompts.py::test_a_deleted_prompt_leaves_the_offer_but_not_the_readings_it_made` |
| Kanał i temat czytają nowe filmy swoim promptem / Zmiana promptu kanału | `test_prompts.py::test_a_film_is_read_by_the_prompt_its_channel_held_when_it_was_noticed` |
| … / Prompt usunięty z wyboru | `test_prompts.py::test_a_deleted_prompt_leaves_the_offer_but_not_the_readings_it_made`, `test_api.py::test_a_channel_and_a_topic_change_their_prompt_and_an_unknown_one_is_refused` |
| Film może mieć kilka odczytów / Drugi prompt na odczytanym filmie | `test_prompts.py::test_another_prompt_reads_a_film_again_without_asking_for_its_words_or_moving_it`, `test_store.py::test_a_list_carries_no_text_and_one_film_carries_every_reading_the_films_own_first` |
| … / Film bez transkrypcji | `test_prompts.py::test_a_reading_by_another_prompt_is_refused_for_a_film_without_words_or_when_the_days_tokens_are_spent` |
| Prompt zmienia polecenie, nie granice / Prompt prosi o inny kształt | `test_analysis.py::test_the_operators_words_sit_inside_a_frame_that_says_the_transcript_is_data`, `…::test_an_answer_that_breaks_the_schema_is_not_stored` |
| youtube-data-enrichment: Odczyt ma stały kształt i stempel / Model zwraca ocenę spoza zakresu | `test_analysis.py::test_an_answer_that_breaks_the_schema_is_not_stored` |
| … / Odczyt sprzed zmiany | `test_migration.py::test_a_reading_in_the_old_shape_keeps_everything_it_said_…` |
| youtube-data-api: Kontrakt czyta archiwum i zarządza listą / Okno bez sensu | `test_api.py::test_a_window_that_ends_before_it_starts_is_refused_with_the_reason` |
| … / Lista filmów | `test_api.py::test_a_list_carries_no_text_and_one_film_carries_every_reading_by_its_prompt` |
| Pola odczytu są zawsze obecne / Film nieodczytany | `test_api.py::test_a_read_film_reaches_the_wire_with_its_reading_and_an_unread_one_with_the_field_empty` |
| youtube-data-tools: Zestaw dopisuje, ale nie usuwa / Lista narzędzi | `test_tools.py::test_the_surface_adds_and_never_removes` (z `prompt` wśród zakazanych słów w nazwach) |
| Zestaw domyka drogę od pytania do odczytu / Pytanie o to, co kanały mówią o złocie | `test_tools.py::test_a_list_carries_an_excerpt_…`, `test_a_film_is_read_whole_…` (droga `recent_videos` → `read_video`; brak testu rozmowy z modelem) |
| youtube-data-alerts: Znacznik po udanej wysyłce (4 scenariusze) | `test_alerts.py` (istniejące) oraz `test_a_reading_ordered_by_another_prompt_is_never_the_one_handed_over` |
| Wiadomość prowadzi do filmu / Długie streszczenie | `test_alerts.py::test_a_long_summary_is_cut_by_this_package_so_the_door_never_has_to_refuse_it` |
| terminal-youtube: Zakładka pokazuje filmy z odczytem / Film bez odczytu, Film z dwoma odczytami | `YoutubeView.test.tsx` (film bez odczytu; odczyt pod nazwą promptu), `youtubeApi.test.ts::maps a film's readings…` |
| Operator edytuje listę obserwacji / Kanał nie istnieje | `YoutubeView.test.tsx::adds a channel from the tab, and keeps the module's reason…`, `…follows a channel by the prompt chosen in the dialog` |
| Sekcja Prompty zarządza promptami / Usunięcie przypisanego, Zasiany prompt | `PromptsPanel.test.tsx` (trzy testy) |

## Gaps

- **Dwa odczyty jednego filmu na ekranie** (`terminal-youtube`, „Film z dwoma odczytami”): test sprawdza kontrakt (`youtubeApi.test.ts`)
  i zamawianie odczytu, ale nie render dwóch sekcji obok siebie z kolejnością „prompt filmu pierwszy” — kolejność jest testowana po
  stronie modułu (`test_store.py`).
- **Odpowiedź modelu na pytanie o złoto** — brak testu z prawdziwym modelem; narzędzia, którymi odpowie, są pokryte.
- **Migracja na kopii produkcyjnej** — nie wykonano; przed merge warto zrobić zrzut bazy `youtube` i przejść `0003` na nim.
