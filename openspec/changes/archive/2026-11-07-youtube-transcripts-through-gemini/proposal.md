## Why

`add-youtube-archive` zostawiła jedno pytanie otwarte: skąd produkcja weźmie tekst filmu, skoro
YouTube blokuje adresy Azure w całości, a `direct` (`youtube-transcript-api`) działa tylko z domowego
IP. Zakładaliśmy płatnego pośrednika z zadaniami asynchronicznymi (Supadata) i pod niego zbudowaliśmy
`Pending`/`poll` oraz kolumny zadania w `videos`.

Skill `yt-transkrypcje` w `C:\Marek\Agents` pokazał prostszą drogę, opartą wyłącznie na Google:
YouTube Data API znajduje filmy i mówi, jak długi jest film i w jakim języku mówi, darmowe napisy idą
pierwsze, a gdy ich brak — **Gemini dostaje link do filmu i przepisuje go, słuchając**. To oficjalna
funkcja API Gemini, bez proxy i bez scrapingu, działa z chmury i na filmach bez napisów. Darmowy plan
daje 8 h filmu dziennie, płatny Flash to szacunkowo ~0,3 USD za godzinę filmu
(`docs/youtube-gemini-plan.html`).

Ta zmiana przenosi tę drogę do `youtube_data`, a przy okazji orze to, co stało tylko pod
niewybranego pośrednika albo pod źródło, które przestaje mieć sens.

## What Changes

- **Nowy dostawca transkrypcji `gemini`** (`providers/gemini.py`, zależność `google-genai`): link do
  filmu jako `file_data`, niska rozdzielczość obrazu, dosłowny zapis bez tłumaczenia, znaczniki
  `[MM:SS]`, filmy dłuższe niż próg cięte na kawałki z przesunięciem. Klucz
  `YOUTUBE_GEMINI_API_KEY`, model `YOUTUBE_GEMINI_MODEL`.
- **Łańcuch dostawców rozróżnia czytających i słuchających.** Brak napisów u dostawcy napisów
  przechodzi do następnego dostawcy, który słucha; między dostawcami napisów — jak dotąd — nie.
- **Cena przed wywołaniem, sufit per dostawca.** Dostawca podaje cenę filmu w swojej jednostce;
  Gemini płaci sekundami filmu (`YOUTUBE_GEMINI_DAILY_VIDEO_SECONDS`, domyślnie 8 h), a film, na który
  nie starcza doby, czeka do jutra. Tokeny Gemini są zapisywane obok — do rachunku, nie do sufitu.
- **Zablokowany dostawca odpoczywa** (`YOUTUBE_PROVIDER_COOLDOWN_MINUTES`): z Azure `direct` dostaje
  blokadę na każdym filmie, więc po pierwszej nie jest pytany przez kilka godzin, a łańcuch idzie
  od razu do `gemini`.
- **Napisy tylko w języku filmu**: `defaultAudioLanguage` z Data API trafia do filmu, a `direct`
  prosi wyłącznie o napisy w tym języku — tłumaczenie to nie oryginał. Gdy język nie jest znany,
  zostaje lista z ustawień.
- **Transkrypcja niesie czas i pochodzenie**: napisy sklejane w akapity co ~30 s ze znacznikiem
  `[MM:SS]`, Gemini pisze je sam; kolumna `transcripts.model` i pole `model` w kontrakcie mówią, który
  model przepisał film.
- **Symulacja**: dostawca `sim_gemini`, który słucha filmów ze scenariusza (pole `speech`), z blokadą
  i sufitem w sekundach filmu; domyślny łańcuch `sim,sim_gemini` ćwiczy kolejność produkcji.
- **Do zaorania**:
  - źródło **`rss`** — nie zna długości filmu (Gemini jej potrzebuje do ceny i kawałków), nie
    rozwiązuje `@uchwytu` i nie szuka; klucz Data API jest darmowy, więc jedynym prawdziwym
    źródłem zostaje `data_api`;
  - **zadania asynchroniczne** — `Pending`, `poll`, `videos.job_provider`/`job_id`, tryb `async`
    w scenariuszu; stały pod pośrednika, którego nie wybieramy, a Gemini odpowiada od razu;
  - **flagi możliwości źródła** (`supports_search`, `supports_handles`, `UnsupportedOperation`) —
    każde pozostałe źródło umie wszystko, więc gałęzie odmowy są martwe.

**Poza zakresem:** włączenie pakietu na produkcji (baza, Terraform, sekret w Key Vault) — pakiet
nadal montuje się tylko z `YOUTUBE_DATABASE_URL`, a produkcja go nie ma; Gemini jako analizator
odczytu (odczyt zostaje przy OpenAI); filtr AI dla kanałów z wieloma prowadzącymi z Agents.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `youtube-data-transcripts`: łańcuch z dostawcą słuchającym, cena przed wywołaniem i sufit per
  dostawca, odpoczynek zablokowanego, napisy w języku filmu, znaczniki czasu i model w transkrypcji.
- `youtube-data-simulation`: symulowany dostawca słuchający zamiast zadania asynchronicznego.

Obie zdolności powstają w `add-youtube-archive`, która nie jest jeszcze zarchiwizowana —
**ta zmiana MUST zostać zarchiwizowana po niej**, inaczej delty nie mają do czego się odnieść.

## Impact

- `modules/workbench/youtube_data`: `providers/gemini.py` (nowy), `providers/rss.py` (usunięty),
  `base.py`, `chain.py`, `direct.py`, `data_api.py`, `build.py`, `config.py`, `budget.py`,
  `ingest.py`, `store.py`, `models.py`, `contract.py`, `views.py`, `tools/`, `sim/`; migracja
  `0002` (usuwa kolumny zadania, dodaje `videos.audio_language` i `transcripts.model`).
- `modules/workbench/pyproject.toml`: `google-genai`.
- `modules/workbench/.env.example`, `youtube_data/README.md`: blok Gemini, bez `rss`.
- `modules/terminal`: wygenerowany kontrakt YouTube (pole `model`), karta filmu, dialog kanału
  bez wzmianki o `rss`.
- Produkcja: bez zmian — pakiet się nie montuje.
- Operator przed pierwszym prawdziwym kluczem: pomiar G0 (trzy filmy przez Gemini w `C:\Marek\Agents`)
  kalibruje rozmiar kawałka i scenariusz — `tasks.md`, grupa 8.
- `review.md`: tak — nowa zależność zewnętrzna, nowy sekret i zmiana reguły łańcucha.
