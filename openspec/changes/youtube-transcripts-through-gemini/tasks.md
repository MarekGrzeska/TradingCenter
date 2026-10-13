## 1. Do zaorania

- [x] 1.1 Usunąć `providers/rss.py`, `tests/youtube/test_rss.py` i budowę feedu w `tests/youtube/builders.py`; `KNOWN_VIDEO_SOURCES = ("data_api", "sim")`; odmowa `rss` z podpowiedzią
- [x] 1.2 Usunąć `Pending`, `poll`, `TranscriptChain.poll`, `store.record_job`/`clear_job`, pola `job_provider`/`job_id` w `Video`, tryb `async` w `SimCaptions` i `World.jobs`
- [x] 1.3 Usunąć `supports_search`, `supports_handles`, `UnsupportedOperation` i gałęzie, które ich używały (pętla, `watchlist.py`, narzędzie `search_youtube`); pole `search_supported` z `TopicsOut`, `StateOut` i `tools/briefs.py`
- [x] 1.4 Migracja `0002`: `DROP COLUMN job_provider, job_id`; `ADD COLUMN videos.audio_language`, `transcripts.model`; `downgrade` odwrotnie

## 2. Interfejs i łańcuch

- [x] 2.1 `TranscriptRequest(video_id, duration_seconds, languages, audio_language)`; `fetch(request)`, `price(request)`, `listens` w protokole; `Transcript.model`
- [x] 2.2 `TranscriptChain.fetch` → `ChainAnswer(result, passed)` z regułą słuchającego i wynikiem `Deferred` (reguły końca: `design.md`, decyzja 2); pętla zapisuje stan każdego minionego dostawcy, a na `Deferred` woła `store.postpone` bez zmiany `attempts`
- [x] 2.3 Cena przed wywołaniem i sufit per dostawca (`budget.transcript_ceiling`: słuchający → `GEMINI_DAILY_VIDEO_SECONDS`, reszta → `DAILY_TRANSCRIPT_UNITS`); odpoczynek zablokowanego (`PROVIDER_COOLDOWN_MINUTES`, z `store.provider_states`); brak dostawcy z czymkolwiek do zapytania zatrzymuje krok
- [x] 2.4 Testy jednostkowe łańcucha: blokada → dalej (i w `passed`), brak napisów → słuchający z pominięciem kolejnych dostawców napisów, brak napisów bez słuchającego → koniec, słuchający bez tekstu → koniec, słuchający zablokowany po braku napisów → `Blocked`, słuchający pominięty → `Deferred`

## 3. Napisy

- [x] 3.1 `data_api`: `defaultAudioLanguage` → `VideoRef.audio_language`; `store.upsert_films`/`refresh_film` zapisują język
- [x] 3.2 `direct`: prośba wyłącznie o język filmu, gdy znany; akapity co ~30 s ze znacznikiem `[MM:SS]`
- [x] 3.3 Testy: polski film z angielskimi napisami → brak napisów; akapity i znaczniki

## 4. Gemini

- [x] 4.1 `providers/gemini.py`: link jako `file_data`, `MEDIA_RESOLUTION_LOW`, temperatura 0,2, prompt dosłownego zapisu, kawałki przez `video_metadata`, parser znaczników z regułą przesunięcia
- [x] 4.2 Mapowanie błędów (429/5xx/czas/sieć/401/403 → `Blocked`; 400/404 → `NoTranscript` bez opłaty, chyba że komunikat mówi o kluczu albo modelu — wtedy `Blocked`; pusta/ucięta/zablokowana treść → z opłatą); licznik sekund kawałków i tokenów; bez usypiania pętli
- [x] 4.3 Ustawienia `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_CHUNK_MINUTES`, `GEMINI_DAILY_VIDEO_SECONDS`, `GEMINI_TIMEOUT_SECONDS`, `PROVIDER_COOLDOWN_MINUTES`; odmowa startu bez klucza i przy źródle innym niż `data_api`; `google-genai` w `pyproject.toml`
- [x] 4.4 Testy przez prawdziwe SDK nad `httpx.MockTransport` (`design.md`, decyzja 10): kawałki i przesunięcia, każde mapowanie błędu (w tym 400 „API key not valid" i 404 modelu → blokada), jedno żądanie na odmowę, zużycie, klucz w nagłówku i poza adresem

## 5. Symulacja

- [x] 5.1 `sim_gemini`: `speech` w `SimVideo`, blok `listening` w scenariuszu, cena = długość filmu, blokada z ziarnem
- [x] 5.2 Scenariusz domyślny: film bez napisów z mową, bez trybu `async`; domyślne `TRANSCRIPT_PROVIDERS=sim,sim_gemini`
- [x] 5.3 Testy symulacji i pętli na nowym łańcuchu (`tests/youtube/harness.py`: `Rig(..., listener=True)` dokłada `SimListener`): film bez napisów słyszany w tym samym przebiegu, napisy zablokowane → wszystko przez słuchającego i odpoczynek, film droższy niż reszta doby czeka bez próby, słuchający z 429 zostawia próby

## 6. Kontrakt i ekran

- [x] 6.1 `model` w stronie transkrypcji (REST i narzędzie `read_transcript`); `contract-sync`
- [x] 6.2 Terminal: model na karcie filmu (`FilmCard.tsx`), dialog kanału bez wzmianki o `rss` (`dialogs.tsx`), bez `searchSupported` (`WatchPanels.tsx`, `youtubeApi.ts`, testy)

## 7. Dokumentacja i weryfikacja

- [x] 7.1 `youtube_data/README.md`, `.env.example`: blok Gemini, łańcuch, odpoczynek; bez `rss`
- [x] 7.2 `ruff check .` · `pyright` · `pytest` (z `-m db`) w workbenchu; `pnpm test` · `lint` · `typecheck` · `contract:check` w terminalu; testy `scripts`
- [x] 7.3 `review.md`

## 8. Operator

- [ ] 8.1 G0: w `C:\Marek\Agents` `transcription.method: gemini`, `sync --limit 3` na filmach z napisami (PL 20 min, PL 40 min, EN); zapisać tokeny na minutę, czas odpowiedzi, jakość nazw i liczb, znaczniki w kawałkach; skalibrować `GEMINI_CHUNK_MINUTES` i scenariusz
- [ ] 8.2 Przebieg ręczny na stacku z `TRANSCRIPT_PROVIDERS=direct,gemini` i prawdziwym kluczem: film z napisami przez `direct`, film bez napisów przez `gemini`
