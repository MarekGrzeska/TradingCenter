## Verdict

Implementacja grup 1–7 stoi: Gemini jest dostawcą słuchającym za tym samym interfejsem co napisy,
łańcuch rozróżnia „brak napisów” od „nie wpuszcza”, każdy dostawca ma cenę przed wywołaniem i dzienny
sufit w swojej jednostce, a `rss`, zadania asynchroniczne i flagi możliwości źródła zniknęły razem z polem
kontraktu `search_supported`. Pakiet nadal montuje się wyłącznie z `YOUTUBE_DATABASE_URL`, więc produkcji
ta zmiana nie dotyka.

Zadania 8.1 (pomiar G0 w `C:\Marek\Agents`) i 8.2 (przebieg ręczny z prawdziwym kluczem) **nie są częścią
tego przeglądu** i zostają niezaznaczone: wymagają klucza Gemini i uruchomionego stacku, a stack jest
operatora. Do czasu G0 wartości domyślne (kawałek 30 minut, niska rozdzielczość, model Flash) są
przeniesione z Agents, gdzie ścieżka Gemini **nigdy się nie wykonała** — niezmierzone.

## Verified

| Co | Wynik |
|---|---|
| `modules/workbench`: `ruff check .` · `pyright` | czysto · 0 błędów |
| `modules/workbench`: `pytest -m "not live"` (z `-m db` na testcontainers) | **2819 passed**, 11 odznaczonych (`live`) |
| `tests/youtube` osobno | **229 passed** |
| `modules/terminal`: `pnpm typecheck` · `lint` · `test` · `contract:check` | czysto · czysto · **836 passed** · „Every contract is up to date” |
| `scripts`: `uv run pytest` | **177 passed, 2 skipped** |

Żądanie do Gemini sprawdzone przez prawdziwe SDK (`google-genai` 2.29) nad `httpx.MockTransport`, nie
nad podstawionym klientem: nagłówek `x-goog-api-key`, adres bez klucza, `file_data.file_uri`,
`video_metadata.start_offset/end_offset`, jedno żądanie na odmowę (SDK nie ponawia za plecami pętli).

## Findings

Przy pisaniu wyszły trzy rzeczy, które test napisany „z głowy” przepuściłby; każda ma test.

1. **Zły klucz to 400, nie 401.** Gemini odpowiada na nieważny klucz kodem 400 `INVALID_ARGUMENT`, a na
   nieznany model 404. Czytane jako „film niedostępny” (`NoTranscript`), każdy film w archiwum zostałby
   porzucony po czterech próbach z powodu literówki w `.env`. Rozstrzyga treść komunikatu (`api key`,
   `model`) → `Blocked`. Test: `test_a_refusal_about_us_is_blocked_and_one_about_the_film_is_no_transcript`.
2. **429 po „brak napisów” nie może zjeść filmowi prób.** Pierwsza wersja łańcucha oddawała w tym
   miejscu `NoTranscript` dostawcy napisów. Teraz odpowiedzią jest blokada słuchającego, film zachowuje
   próby. Test: `test_a_listener_that_refuses_after_no_captions_is_a_refusal_not_a_miss` i po stronie
   pętli `test_a_listener_that_is_rate_limited_leaves_the_film_its_attempts_and_stops_the_pass`.
3. **Blokada napisów zapisana także wtedy, gdy film przeczytał Gemini.** Bez listy `passed` odmowa
   `direct` z Azure nigdy nie trafiłaby do `provider_state` (każdy film kończy się sukcesem Gemini), więc
   `/state` milczałby o tym, że napisy są odcięte, a odpoczynek by nie działał. Test:
   `test_captions_refused_send_every_film_to_the_listener_and_the_refusing_provider_rests` — drugi film
   idzie prosto do słuchającego, po sześciu godzinach `direct` jest pytany znowu.

Mniejsze: `client.aio.aclose()` SDK nie zamyka podanego klienta httpx (dostawca zamyka oba);
`Providers.aclose()` jest wołane przy zamykaniu `serving`.

## Deferred

- **Odpoczynek jest jeden dla wszystkich dostawców.** Chwilowe 429 u Gemini odsuwa go o
  `PROVIDER_COOLDOWN_MINUTES` (360), choć limit minutowy mija w minutę. Przy darmowym planie to
  zwykle bez znaczenia, przy płatnym — strata kilku godzin transkrypcji. Rozstrzygnie pomiar G0
  (jak często 429 w praktyce); wtedy osobny, krótszy odpoczynek dla słuchającego.
- **Film bez znanej długości** (premiera, która nie ruszyła) dostaje od Gemini `NoTranscript` bez opłaty,
  ale zużywa próbę. `due_for_transcription` wyklucza `live`/`upcoming`, więc w praktyce nie dochodzi do
  dostawcy; jeśli G0 pokaże film bez długości w stanie `none`, trzeba go odkładać jak `Deferred`.
- **Darmowy plan Gemini pozwala Google używać treści** do ulepszania produktów. Dopuszczalne lokalnie;
  płatny klucz jest warunkiem zmiany produkcyjnej.
- **Retencja** surowych transkrypcji (30 dni dla danych z Data API) — bez zmian, rozstrzygnie zmiana
  produkcyjna.
- **Klucz w Key Vault, ustawienia App Service, pomiar z Azure**, że `direct` jest blokowany, a `gemini`
  przechodzi — zmiana, która włączy pakiet na produkcji.
