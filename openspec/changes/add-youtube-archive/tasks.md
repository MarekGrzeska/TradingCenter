## 1. Szkielet pakietu

- [x] 1.1 `youtube_data/` z `config.py` (prefiks `YOUTUBE_`, walidacja bazy jak w `social_data/config.py`), `runtime.py` (klucz `8110`), `app.py`, `openapi.py`
- [x] 1.2 `alembic-youtube.ini` i migracja tabel `channels`, `topics`, `videos`, `transcripts`, `readings`, `usage` i `provider_state` (moment ostatniej blokady dostawcy) z częściowym indeksem kolejki `(state, next_attempt_at)`
- [x] 1.3 `caller_access.py` z `OPEN_PATHS`, literalnym `REST_PATHS`, `TOOLS_PREFIX`
- [x] 1.4 Montaż warunkowy w `workbench/app.py` (brak `YOUTUBE_DATABASE_URL` = brak montażu, brak narzędzi, wpis w logu startu); wpis w `tests/test_layering.py`
- [x] 1.5 `scripts/dev.py`: `youtube` w `LOGICAL_DATABASES` i na liście łańcuchów; blok `YOUTUBE_*` w `.env.example`
- [x] 1.6 Testy: start bez ustawienia, start z bazą nieosiągalną (odmowa z nazwą bazy), migracja pod blokadą (`-m db`)

## 2. Interfejsy dostawców i adaptery darmowe

- [x] 2.1 Protokoły `VideoSource`, `TranscriptProvider`, `Analyser` z wynikami `Transcript | NoTranscript | Blocked | Pending(job)`
- [x] 2.2 `rss` (kanał po `channel_id`) i `data_api` (uploads playlist, `videos.list` po 50, `search.list`, `forHandle`; klucz w `X-goog-api-key`)
- [x] 2.3 `direct` przez `youtube-transcript-api` (zależność w `pyproject.toml`), mapowanie błędów na `NoTranscript` / `Blocked`
- [x] 2.4 `openai` analyser: jedno wywołanie bez narzędzi, strict JSON schema, walidacja, profil `market`, prompt „dane, nie polecenie"
- [x] 2.5 Łańcuch dostawców z ustawienia; przejście dalej tylko po `Blocked`/błędzie
- [x] 2.6 Testy adapterów na zapisanych odpowiedziach (`respx`) i test, że żaden adres wychodzący nie niesie sekretu

## 3. Symulacja

- [x] 3.1 `Clock` wstrzykiwany i `YOUTUBE_SIM_SPEED`
- [x] 3.2 Format scenariusza JSON i jego walidacja; `sim/scenarios/default.json` z syntetycznymi transkrypcjami (PL, EN, pusta, z wstrzyknięciem) i przygotowanymi odczytami
- [x] 3.3 `sim` VideoSource: filmy w czasie, wyszukiwanie po katalogu, koszt jednostek, rozwiązanie `@uchwytu`
- [x] 3.4 `sim` TranscriptProvider: napisy natychmiast / po czasie / nigdy / zadanie asynchroniczne, odsetek blokad z ziarnem, opóźnienie, płatny brak napisów
- [x] 3.5 `sim` Analyser: przygotowany odczyt, `unusable`, odczyt neutralny, tokeny = długość / 4
- [x] 3.6 Oznaczenie symulacji na filmie, transkrypcji i odczycie; odmowa startu symulacji w trybie produkcyjnym
- [x] 3.7 Testy powtarzalności przebiegu dla tego samego scenariusza, ziarna i zegara

## 4. Lista obserwacji i pętla

- [ ] 4.1 `store.py`: kanały i tematy z sufitem, deduplikacja kanału, pauza, zdjęcie bez kasowania filmów
- [ ] 4.2 `ingest.py`: przebieg odkryj → transkrybuj → odczytaj → powiadom, limity partii, pominięcia z powodem (short, za długi, trwająca transmisja), zapis znacznika `simulated` z wyniku dostawcy
- [ ] 4.3 Stany filmu, ponowienia w rosnących odstępach, `gave_up`, limit porażek odczytu
- [ ] 4.4 Zapis `usage` per dostawca, dzienne sufity (jednostki, kredyty, tokeny), stan dostawcy (czynny / zablokowany / sufit)
- [ ] 4.5 Wiek ostatniego ukończonego przebiegu w interwałach pętli
- [ ] 4.6 Testy jednostkowe harmonogramu ponowień i sufitów; testy `-m db` zapytania kolejki (bez `gave_up`) i deduplikacji filmu z kanału i tematu
- [ ] 4.7 `db-cost-check` dla zapytania kolejki i listy filmów

## 5. Alerty

- [ ] 5.1 Reguły `always` / `threshold` / `never` na kanale i temacie; klient `/telegram` w procesie jak w `social_data/alerts.py`
- [ ] 5.2 Treść wiadomości w limicie bramy, oznaczenie symulacji, znacznik po udanej wysyłce
- [ ] 5.3 Testy: brama odmawia, film bez odczytu, adresat nieustawiony

## 6. REST i kontrakt

- [ ] 6.1 `contract.py` i routery: filmy (okno, zawężenia, porządek), film, transkrypcja stronami, kanały i tematy (odczyt, dopisanie, pauza, zdjęcie), wskazanie filmu, `/state`, `/health`
- [ ] 6.2 Testy: happy path, okno bez sensu, ścieżka spoza zapisu, pola odczytu puste

## 7. Narzędzia

- [ ] 7.1 FastMCP: `youtube_archive_status`, `recent_videos`, `read_video`, `read_transcript`, `instrument_sentiment`, `search_youtube`, `follow_channel`, `add_topic`, `set_alert_rule`, `analyse_video`
- [ ] 7.2 Podpięcie w `workbench/local_tools.py` dla rozmowy i zespołów (tylko gdy pakiet zamontowany)
- [ ] 7.3 Testy: brak narzędzi usuwających, odmowa po sufcie budżetu, odmowa wyszukiwania przy `rss`, `read_video` bez surowego tekstu

## 8. Terminal

- [ ] 8.1 `contract-sync`: `contract.youtube.generated.ts`
- [ ] 8.2 `src/youtube/`: `YoutubeView` z zakładkami Filmy / Kanały / Tematy, szczegół filmu, dialogi dopisania, pasek stanu z symulacją i sufitami
- [ ] 8.3 Testy widoku: happy path, odmowa kontraktu, nieudane odświeżenie nie czyści listy

## 9. Domknięcie

- [ ] 9.1 `youtube_data/README.md` (co pakiet pisze, dostawcy, jak uruchomić symulację) i wiersz w `modules/workbench/README.md`
- [ ] 9.2 Przebieg ręczny: `scripts/dev.py` na scenariuszu domyślnym przyspieszonym — film od odkrycia do alertu na testowym bocie, narzędzia w MCP Inspectorze
- [ ] 9.3 `uv run pytest`, `-m db`, `ruff check .`, `pyright`, terminal `pnpm test` / `lint` / `typecheck` / `contract:check`
- [ ] 9.4 `review.md`
