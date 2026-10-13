## Context

Wzór: `C:\Marek\Agents\.claude\skills\yt-transkrypcje` (`ytlib/youtube.py`, `transcripts.py`,
`sync.py`). Porównanie elementów i szacunek kosztu: `docs/youtube-gemini-plan.html`. Cennik Gemini:
`C:\Marek\Agents\doc\cennik-gemini.md` (stan 10.10.2026).

Ważne zastrzeżenie: w Agents ścieżka Gemini **nigdy się nie wykonała** — 10 z 10 filmów poszło przez
automatyczne napisy z domowego IP, licznik `gemini_video_seconds` stoi na zero. Kod jest przemyślany,
ale niezmierzony. Dlatego wartości domyślne (kawałek 30 min, niska rozdzielczość, model Flash) są
przeniesione z Agents, a pomiar G0 jest zadaniem operatora przed pierwszym prawdziwym kluczem.

Co z obecnej implementacji zostaje bez zmian: `data_api`, `refs.py`, lista obserwacji, pętla i stany
filmu, ponowienia, `usage`/`Meter`/`provider_state`, odczyt OpenAI, alerty, REST, dziesięć narzędzi,
zakładka terminala, symulacja (rozszerzona).

## Goals / Non-Goals

**Goals:**
- Film bez napisów — albo każdy film, gdy napisy są zablokowane — dostaje tekst od Gemini.
- Koszt Gemini jest znany przed wywołaniem i ma dzienny sufit w jednostce, w której liczy go Google.
- Kod, który stał pod niewybrane rozwiązania, znika.

**Non-Goals:**
- Produkcja (baza, Terraform, Key Vault) — osobna zmiana, która włączy pakiet.
- Gemini jako analizator odczytu, filtr AI kanałów, wykrywanie shortów przez `HEAD /shorts/ID`.

## Decisions

**1. Gemini przepisuje, nie czyta.** Gemini jest dostawcą transkrypcji, a odczyt zostaje przy
`OpenAIAnalyser`. Archiwum trzyma tekst niezależny od modelu, który go ocenia: zmiana modelu odczytu
nie wymaga ponownego słuchania filmu, a odczyt dalej ma jeden schemat i jeden limit tokenów. Agents
robi tak samo (Gemini przepisuje, streszczenie robi inny model). Alternatywa — jedno wywołanie
„posłuchaj i oceń" — byłaby tańsza o jedno wywołanie, ale wiązałaby archiwum z jednym dostawcą i
gubiła tekst, który narzędzia podają stronami.

**2. Dostawca deklaruje, czy słucha (`listens`).** `TranscriptChain` przechodzi dalej po `Blocked`
jak dotąd, a po `NoTranscript` — tylko do najbliższego dostawcy, który słucha, pomijając kolejnych
dostawców napisów. Brak napisów jest faktem o napisach, nie o filmie; dla dostawcy słuchającego
film bez napisów to zwykła praca. Brak tekstu od dostawcy słuchającego (film prywatny, odpowiedź
ucięta) jest ostateczną odpowiedzią łańcucha w tym przebiegu i idzie w zwykłe ponowienia.
Łańcuch zwraca też odpowiedzi, które minął (`passed`), żeby pętla zapisała blokadę `direct` także
wtedy, gdy `gemini` dał tekst — inaczej trasa stanu nigdy nie pokazałaby, że napisy są zablokowane.

Wynik łańcucha to `ChainAnswer(result, passed)`, a `result` ma czwartą postać: `Deferred(reason)`
(lokalną dla łańcucha, nie dla dostawców). Reguły końca, w tej kolejności:
- brak napisów, a potem dostawca słuchający odpowiedział blokadą → `Blocked` słuchającego (film
  zachowuje próby, przebieg staje — 429 nie może zjeść filmowi prób);
- brak napisów, a dostawca słuchający był pominięty przez `only` (odpoczywa albo nie stać go na film)
  → `Deferred`;
- brak napisów i żadnego dostawcy słuchającego → `NoTranscript` (stara reguła);
- same blokady → ostatnia `Blocked`;
- nikogo nie zapytano → `Deferred`.
Pętla na `Deferred` niczego nie zapisuje (film nie ma nowej wiedzy; data ponowienia sprawiłaby, że
kwadrans odpoczynku słuchającego trwałby godzinę) i przechodzi do następnego filmu, nie zatrzymując przebiegu.

**3. Cena przed wywołaniem.** Protokół dostawcy dostaje `price(request) -> int` w jego jednostce:
`direct` 1 zapytanie, `gemini` długość filmu w sekundach. Pętla pyta dostawcę tylko, gdy reszta jego
doby pokrywa cenę tego filmu; inaczej film zostaje na jutro bez zużycia próby. Sufity są per dostawca:
`DAILY_TRANSCRIPT_UNITS` zostaje dla dostawców napisów, `GEMINI_DAILY_VIDEO_SECONDS` (28 800 = darmowy
plan) dla Gemini. Gemini zapisuje sekundy każdego kawałka, na który odpowiedział, oraz tokeny jako
drugą jednostkę — pieniądze liczy się z tokenów, ale limit Google jest w godzinach filmu, więc sufit
też. Alternatywa — sufit w tokenach — wymagałaby zgadywania tokenów przed wywołaniem.

**4. Odpoczynek zablokowanego dostawcy.** Dostawca, którego ostatnia odpowiedź była blokadą młodszą
niż `PROVIDER_COOLDOWN_MINUTES` (domyślnie 360), nie jest pytany. Z Azure każdy film dostałby
najpierw blokadę `direct` (zapytanie i do 60 s czekania), a dopiero potem Gemini. Po odpoczynku
`direct` jest pytany znowu — blokada adresu bywa czasowa. Blokada, po której nie zostaje żaden
dostawca do zapytania, zatrzymuje przebieg jak dotąd.

**5. Napisy tylko w języku filmu.** `data_api` czyta `snippet.defaultAudioLanguage` (`VideoRef.
audio_language`, kolumna `videos.audio_language`). `direct` prosi wtedy wyłącznie o napisy w tym
języku (ręczne przed automatycznymi — kolejność biblioteki), a gdy język nie jest znany — o listę
`TRANSCRIPT_LANGUAGES`. Ręczne angielskie napisy polskiego filmu to tłumaczenie; odczyt rynkowy z
tłumaczenia gubi nazwy i liczby. Brak napisów w języku filmu kieruje film do Gemini (decyzja 2).

**6. Znaczniki czasu w treści, nie w tabeli.** `transcripts.content` zostaje tekstem, ale w liniach
`[MM:SS] …`: napisy sklejane w akapity co ~30 s, Gemini pisze znaczniki sam, a parser sprowadza je do
czasu od początku filmu. Odczyt i agent mogą wskazać moment (`&t=123s`), narzędzia dalej stronicują po
znakach. Osobna tabela segmentów odrzucona: nikt dziś nie czyta po czasie. Przy kawałkach Gemini
liczy czas raz od początku kawałka, raz od początku filmu — rozstrzyga pierwszy znacznik (bliżej zera:
dodaj przesunięcie), reguła przeniesiona z Agents.

**7. Pochodzenie: `provider`, `automatic`, `model`.** Tekst z Gemini to `provider="gemini"`,
`automatic=true`, `model=<id>`. Nowa kolumna `transcripts.model` (pusta dla napisów) i pole `model`
w kontrakcie strony transkrypcji; karta filmu pokazuje model. Prompt odczytu już mówi, że tekst to dane
obce — model może mylić nazwy własne i liczby jak ASR.

**8. Błędy Gemini.** 429, 5xx, przekroczony czas, błąd sieci, 401/403 (klucz) → `Blocked` — to fakt o
nas albo o Google, nie o filmie; przebieg przestaje pytać, kolejny spróbuje (bez usypiania pętli,
które robi Agents). 400/404 (film prywatny, usunięty, niedostępny) → `NoTranscript` bez opłaty.
Pusta odpowiedź, `MAX_TOKENS`, blokada treści → `NoTranscript` z opłatą (sekundy kawałka zostały
policzone). Wszystkie idą w zwykłe ponowienia i kończą się `gave_up`.

**9. Kawałki.** Film dłuższy niż 1,2 × `GEMINI_CHUNK_MINUTES` (domyślnie 30) jest przepisywany
kawałkami przez `video_metadata.start_offset/end_offset`, tekst sklejany w kolejności. Granica 1,2
z Agents: film 33-minutowy w jednym wywołaniu zamiast 30 + 3. Film bez znanej długości (nie powinien
dojść do transkrypcji, bo `data_api` ją zna, ale premiera może ją jeszcze mieć pustą) → `NoTranscript`
bez opłaty, ponowienie za godzinę.

**10. Klucz, transport i walidacja startu.** Pułapki SDK `google-genai` (2.29), sprawdzone:
- przy zainstalowanym `aiohttp` (jest w środowisku workbencha) klient asynchroniczny idzie przez
  `aiohttp`; dostawca podaje SDK **własny** `httpx.AsyncClient` przez
  `types.HttpOptions(timeout=<ms>, httpx_async_client=...)` — jeden transport, a test podstawia
  `httpx.MockTransport` i widzi prawdziwe żądanie (nagłówek `x-goog-api-key`, adres bez klucza);
- `client.aio.aclose()` **nie zamyka** podanego klienta httpx — `aclose()` dostawcy zamyka oba, a
  `Providers.aclose()` woła je przy zamykaniu `serving`;
- SDK domyślnie nie ponawia (jedno żądanie na 429/503) — ponawia pętla, nie SDK;
- ciało żądania ma klucze zagnieżdżone w snake_case (`fileData.file_uri`,
  `videoMetadata.start_offset`) — testy czytają je tak, jak idą;
- `errors.ClientError`/`ServerError` (podklasy `errors.APIError`) mają `code`, `status`, `message`.
  Zły klucz to **400** `INVALID_ARGUMENT` „API key not valid", nieznany model to **404** — 400/404
  jest brakiem tekstu o filmie tylko wtedy, gdy komunikat nie mówi o kluczu ani modelu
  (`"api key"`, `"api_key"`, `"model"`); inaczej blokada. Do potwierdzenia w G0: co dokładnie Google
  odpowiada na film prywatny.

`YOUTUBE_GEMINI_API_KEY`; `gemini` w `TRANSCRIPT_PROVIDERS` bez
klucza albo przy źródle innym niż `data_api` to odmowa startu z nazwą ustawienia (symulowane filmy nie
istnieją na YouTube, więc prawdziwy Gemini nie ma czego słuchać). SDK wysyła klucz nagłówkiem
`x-goog-api-key`; moduł nie loguje odpowiedzi błędów w całości, tylko kod i status. Darmowy plan Gemini
pozwala Google używać treści do ulepszania produktów — dopuszczalne lokalnie, na produkcji płatny plan
(do zmiany produkcyjnej).

**11. Do zaorania, z powodem:**
- `rss`: nie zna długości (decyzje 3 i 9), nie rozwiązuje `@uchwytu`, nie szuka. Z nim zostałaby
  kombinacja ustawień, w której Gemini nie działa. `data_api` jest darmowe; brak klucza w dev to `sim`.
- `Pending`/`poll`/`job_provider`/`job_id`/tryb `async`: zbudowane pod Supadatę (zadanie dla długich
  filmów). Gemini odpowiada synchronicznie; dostawca z zadaniami wróci z własną zmianą, jeśli kiedyś
  będzie potrzebny. Migracja `0002` usuwa kolumny — pakiet nie działa nigdzie poza dev.
- `supports_search`/`supports_handles`/`UnsupportedOperation`: po odejściu `rss` każde źródło umie
  wszystko. Razem z nimi znika pole kontraktu `search_supported` (w `TopicsOut` i `StateOut`,
  w `tools/briefs.py` i w terminalu: baner w `WatchPanels.tsx`, mapery w `youtubeApi.ts`, testy) —
  byłoby zawsze `true`.
- `rss` w `.env` po tej zmianie to odmowa startu nazywająca `data_api` i `sim`.

**12. Symulacja.** `sim_gemini` (`listens=True`, jednostka `sim_video_seconds`, cena = długość
filmu) słucha filmu ze scenariusza: zwraca `speech`, a gdy go brak — tekst napisów; film bez
jednego i drugiego to `NoTranscript` z opłatą. Zachowanie z bloku `listening` scenariusza: odsetek
blokad, opóźnienie, dzienny sufit. Domyślny łańcuch w ustawieniach: `sim,sim_gemini`; scenariusz
domyślny ma film bez napisów, który dostaje tekst od `sim_gemini`, i film z napisami po czasie.

## Risks / Trade-offs

- [Link YouTube w Gemini to funkcja w preview; forum zgłasza niestabilne błędy] → błędy to `Blocked`
  albo `NoTranscript` z ponowieniami; dostawca jest klasą w łańcuchu, więc zapasowy (płatny
  pośrednik) to kolejna klasa.
- [Tekst modelu myli nazwy spółek, tickery, liczby] → `model` w transkrypcji i na ekranie; G0 porówna
  z napisami na tych samych filmach.
- [Koszt rośnie od 2027 (Flash ×2)] → sufit w sekundach filmu i model w ustawieniu.
- [Usunięcie `rss` zabiera tryb „prawdziwe filmy bez klucza"] → klucz Data API jest darmowy; bez
  niego dev ma `sim`.
- [Zmiana sygnatury `fetch` dotyka wszystkich dostawców i testów] → jedna zmiana, teraz, zanim pakiet
  wejdzie do `main` i na produkcję.

## Migration Plan

Dev: `alembic -c alembic-youtube.ini upgrade head` (pętla robi to sama przy starcie). `.env` z
`YOUTUBE_VIDEO_SOURCE=rss` → odmowa startu z podpowiedzią. Produkcja: nic. Wycofanie: `downgrade` do
`0001` przywraca kolumny zadania (puste) i usuwa nowe.

## Open Questions

- Wynik G0: tokeny na minutę filmu przy niskiej rozdzielczości, jakość nazw własnych, zachowanie
  znaczników w kawałkach — może zmienić `GEMINI_CHUNK_MINUTES` i model domyślny.
- Czy na produkcji `direct` w ogóle zostaje w łańcuchu (oszczędność vs. jedno zapytanie co
  `PROVIDER_COOLDOWN_MINUTES`) — rozstrzygnie zmiana produkcyjna po pomiarze z Azure.
