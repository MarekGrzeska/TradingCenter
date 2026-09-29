## Context

`social_data` to pakiet workbencha pod `/social`, z bazą `social` i jedną pętlą. Pętla co 300 s pyta
dostawcę Truth Social o każdą datę UTC z okna 24 h, zapisuje nowe posty jednym `INSERT … unnest …
ON CONFLICT DO NOTHING`, a potem odpala wzbogacanie i alerty.

Protokół dostawcy (`PostSource.fetch(day)`) adresuje historię datą, a RSS nie ma daty w adresie:
zawsze oddaje ostatnie N pozycji. Newsy nie pasują więc do istniejącego protokołu ani do tabeli
`posts`, której kolumny odczytu modelu i znacznik alertu są dla nich puste z założenia. Motywacja:
`proposal.md`. Zmierzone feedy i ich zachowanie: `docs/zrodla-newsow.html`.

Wszystkie źródła z listy startowej odpowiedziały 29 września **200 na własny User-Agent pakietu**
(`tradingcenter-social-data/0.1`), a nie tylko na udawaną przeglądarkę. Dziewięć z czternastu adresów
podaje `ETag` albo `Last-Modified`.

## Goals / Non-Goals

**Goals:**

- Zbiór rusza przy pierwszym wdrożeniu po merge, bez żadnej czynności operatora.
- Opóźnienie mierzone uczciwie: z granicą, która oddziela spóźnienie źródła od rytmu pętli.
- Dołożenie feedu to jeden wpis w liście.

**Non-Goals:**

- Relacje na żywo. JSON-LD Guardiana i CNN to drugi rodzaj dostawcy, w osobnej zmianie.
- Grupowanie tego samego newsa z kilku źródeł. Porównanie szybkości źródeł daje już ich rachunek
  opóźnień; łączenie należy do zmiany z modelem.

## Decisions

### 1. Osobne tabele w `social_data`, nie nowy pakiet i nie tabela `posts`

To decyzja operatora (proposal). Dwie odrzucone drogi, dla porządku:

- **Nowy pakiet `news_data` z bazą `news`.** Kosztowałby `infra/database.tf` z `apply`,
  `grant-schema-ownership.sql` z `GRANT CONNECT`, nowy klucz locka i miejsce w budżecie
  30 połączeń. Zbiór ruszyłby dopiero po krokach operatora.
- **Newsy jako posty w tabeli `posts`.** Wzbogacanie i alerty wzięłyby je od razu, czyli dokładnie
  to, czego ta zmiana ma nie robić. Brakuje też kolumn na wydawcę, lead i momenty pomiaru.

Nowe tabele w migracji łańcucha `social`:

- **`news_items`**: `source`, `external_id`, `publisher`, `title`, `summary`, `url`,
  `published_at` (nullable), `first_seen_at`, `previous_fetch_at` (nullable), `kept_at` (nullable).
  Klucz unikalny `(source, external_id)`.
  Indeksy: `(published_at DESC)`, `(source, first_seen_at)` i częściowy `(kept_at) WHERE kept_at IS NOT NULL`.
- **`news_sources`**: jeden wiersz na zadeklarowane źródło, z polami `last_success_at`,
  `last_attempt_at`, `last_failure_at`, `last_failure`, `newest_published_at`.

„Zastany” to nie osobna kolumna, tylko `previous_fetch_at IS NULL`. News jest zastany dokładnie
wtedy, gdy źródło nie miało wcześniej udanego pobrania.

### 2. Źródła jako lista danych w kodzie pakietu

Lista to krotka rekordów w `social_data/news_sources.py`, z polami `id`, `publisher`, `url`
i `interval_seconds`. Odrzucone alternatywy:

- **Tabela edytowana z ekranu.** Wymaga tras piszących w kontrakcie, który z zasady tylko czyta.
- **JSON w ustawieniu.** Nieczytelny w Terraform i niewidoczny w review.

Lista w kodzie oznacza, że dopisanie feedu przechodzi review i CI jak każda zmiana, i to jest
dokładnie ta deterministyczność, o którą chodzi.

Lista startowa (identyfikator → adres):

| id | adres |
|---|---|
| `aljazeera` | `aljazeera.com/xml/rss/all.xml` |
| `google-news-iran` | `news.google.com/rss/search?q=Iran+when:1h&hl=en-US&gl=US&ceid=US:en` |
| `google-news-hormuz` | to samo z `q=(Hormuz OR IRGC OR "Iran talks") when:1h` |
| `tehrantimes` | `tehrantimes.com/rss` |
| `irna` | `en.irna.ir/rss` |
| `timesofisrael` | `timesofisrael.com/feed/` |
| `middleeasteye` | `middleeasteye.net/rss` |
| `guardian-iran` | `theguardian.com/world/iran/rss` |
| `guardian-middleeast` | `theguardian.com/world/middleeast/rss` |
| `iranintl` | `iranintl.com/en/feed` |
| `nyt-world` | `rss.nytimes.com/…/World.xml` |
| `nyt-middleeast` | `rss.nytimes.com/…/MiddleEast.xml` |
| `axios` | `api.axios.com/feed/` |
| `bbc-middleeast` | `feeds.bbci.co.uk/news/world/middle_east/rss.xml` |
| `bbc-world` | `feeds.bbci.co.uk/news/world/rss.xml` |

Domyślny odstęp to 120 s. Google News dostaje 180 s, bo nie jest oficjalnym API i nie podaje
znaczników wersji, więc każde pobranie jest pełne.

### 3. Jedna pętla z krótkim taktem, a nie pętla na źródło ani takt postów

Pętla `news` budzi się co 30 s (`SOCIAL_NEWS_TICK_SECONDS`) i pobiera źródła, którym minął odstęp,
równolegle, z semaforem 4 i timeoutem 20 s na źródło. Heartbeat `news` ma `expected_seconds`
równe taktowi. Istniejący alert `social_data.loop_passes_late` bierze maksimum po wymiarze `loop`,
więc stojąca pętla newsów go odpali, a Terraform zostaje bez zmian.

Odrzucone alternatywy:

- **Takt postów, czyli 300 s dla wszystkiego.** Dokładałby do 5 minut do górnej granicy każdego
  newsa, a więc do tego, co ta zmiana mierzy.
- **Zadanie asyncio na źródło.** Szesnaście heartbeatów i szesnaście wymiarów alertu dla jednej
  rzeczy, czyli „zbiór newsów stoi”.

Przebieg liczy się jako ukończony także wtedy, gdy część źródeł zawiodła. Porażka źródła to stan
źródła, a nie pętli. Heartbeat nie bije tylko wtedy, gdy przebieg rzucił wyjątek.

`ETag` i `Last-Modified` trzymane są w pamięci procesu. Restart kosztuje jedno pełne pobranie na
źródło i nic więcej, bo pomiar nie zależy od tych znaczników.

### 4. Opóźnienie liczone przy odczycie z surowych momentów

Przy insercie zapisywane są tylko fakty: `first_seen_at` (moment zakończenia pobrania)
i `previous_fetch_at`, czyli `last_success_at` źródła sprzed tego pobrania. Odpowiedź 304 też jest
udanym pobraniem: newsa wtedy w feedzie nie było.

Granice, powód braku i statystyki liczy SQL przy odczycie:

- percentyle przez `percentile_cont` po 24 h jednego źródła,
- tolerancja zegarów 120 s dla powodu „czas źródła w przyszłości”.

Odrzucona alternatywa to trzymanie wyliczonych granic i agregatów w tabeli stanu. Zmiana tolerancji
albo definicji wymagałaby przeliczania historii, a przy kilkuset wierszach na źródło i dobę odczyt
jest tani. Klasę kosztu potwierdza `db-cost-check` w zadaniach.

Po długiej awarii źródła górna granica jego pierwszych newsów rośnie. To prawda o tym, ile operator
czekał, a granica dolna dalej mówi uczciwie o samym feedzie.

### 5. Retencja: czyszczenie w pętli, znacznik jako moment

Znacznik zachowania to `kept_at` (moment postawienia), a nie boolean. Nic to nie kosztuje, a mówi,
kiedy operator uznał news za ważny. Retencja to `SOCIAL_NEWS_RETENTION_DAYS`, domyślnie 28.
Czyszczenie wykonuje ta sama pętla, raz na godzinę (pierwszy przebieg po starcie też czyści):

```sql
DELETE FROM news_items WHERE first_seen_at < now() - retention AND kept_at IS NULL
```

Chodzi po indeksie `(source, first_seen_at)` albo po skanie tabeli ograniczonej samą retencją.

Odrzucone alternatywy:

- **Partycje po dniu.** Mechanizm zbyt ciężki przy ~100 tys. wierszy.
- **Osobna tabela „zachowane” z kopią newsa.** Dwa miejsca tej samej treści; dziś jedno `UPDATE`
  robi to samo.

Moment zniknięcia w odpowiedzi to `first_seen_at + retencja`, pusty przy `kept_at`.

Trasa to `PUT /news/keep` z ciałem `{"source", "external_id", "keep"}`. Jest idempotentna
i zwraca `NewsItemOut`, a 404 z `Problem` dla nieznanej pary. Para jest w ciele, a nie w ścieżce:
identyfikator z feedu to zwykle URL, a rekord dostępu dopasowuje każdy segment ścieżki jako
`[^/]+`, więc news z ukośnikami w identyfikatorze dostałby 403 (wykryte przy implementacji).
`PUT` na stan, a nie `POST` i `DELETE`, bo klient wysyła to, co chce widzieć, a powtórzenie po
zerwanym połączeniu jest bezpieczne. To pierwsza trasa zapisująca w `/social`. Wyjątek jest opisany
w delcie `social-data-api`, a nie przemycony.

### 6. Parser: `defusedxml` i biblioteka standardowa, bez `feedparser`

Dostawca Truth Social już parsuje RSS przez `defusedxml`, które jest zależnością z powodu
bezpieczeństwa (bomba encji). Odrzucony `feedparser` to nowa zależność z własnym sanityzatorem
i własnym HTTP, z którego i tak byśmy nie korzystali.

Parser obsługuje RSS 2.0 i Atom, w tym:

- datę RFC 822 i ISO 8601,
- `<source>` Google News jako wydawcę,
- `guid`, a bez niego `link`, jako identyfikator.

Lead jest przycinany do 1 000 znaków po zdjęciu znaczników, bo Axios wydaje ~2 KB na pozycję.

### 7. Kontrakt w istniejącej aplikacji `/social`

Nowe trasy to `GET /news` (z `kept=true` dla samych zachowanych, bez okna), `GET /news/sources`
i `PUT /news/keep`, wszystkie w tym samym FastAPI. Wynika z tego:

- ten sam `contract.social.generated.ts` w terminalu i w pocket,
- ten sam scope Entra i ta sama trasa proxy,
- wpisy w `RECORD` z `caller_access.py`, na powierzchni REST.

Limit `GET /news` to domyślnie 300, maksimum 1 000, z polem `truncated`. Nie ma narzędzi MCP,
bo nie ma ich w zakresie.

### 8. Front: zakładka `news` w terminalu, czwarty ekran w pocket

Terminal dostaje wpis w `src/app/tabs.ts` i katalog `src/news/`. Przycisk zachowania zmienia
kartę od razu, a po odmowie wraca do stanu sprzed kliknięcia. Klient idzie przez istniejący
`socialIdentity` i `Endpoints.socialHttp`. Odpytywanie: newsy co 30 s, stan źródeł co 60 s.

Pocket dostaje czwarty wpis w `TABS` i `LABELS` z ikoną. Ekran ma listę i arkusz źródeł. Newsy są
odpytywane co 60 s, a ukryty ekran nie odpytuje wcale, jak `usePosts`.

## Risks / Trade-offs

- **[Regulamin Al Jazeery zakazuje automatycznego zbierania]** → Operator zdecydował świadomie:
  sam RSS, bez relacji, bez modelu, do użytku własnego. Wyłączenie to usunięcie jednego wpisu
  z listy i deploy.
- **[Google News jest nieoficjalny i może zmienić format albo odmówić]** → Porażka jest stanem
  źródła, widocznym w zestawieniu. Pozostałe źródła jej nie odczuwają.
- **[Czas publikacji w feedzie bywa czasem aktualizacji]** → Wtedy granica dolna wychodzi zbyt
  mała albo czas trafia „w przyszłość”. To drugie jest wyłączane ze statystyk z powodem, a pierwsze
  jest cechą źródła, którą mediana i tak pokaże.
- **[Rollback obrazu po migracji]** → `schema_version.verify` odmówi startu starszemu obrazowi
  nad nowszym schematem. Migracja jest tylko addytywna, więc drogą wycofania jest nowy commit
  (roll forward), a nie powrót do poprzedniego obrazu. Skill `deploy-watch` ma to wiedzieć przed
  cofnięciem.
- **[Operator zdejmuje znacznik ze starego newsa przez pomyłkę]** → Ekran mówi, że news zniknie
  przy najbliższym czyszczeniu. Czyszczenie idzie raz na godzinę, więc jest godzina na
  ponowne kliknięcie.
- **[Szum na liście: kilka tysięcy newsów na dobę]** → Domyślne okno zakładki to 6 h, do tego
  zawężenie po źródle i tekście. Filtrowanie tematyczne dojdzie ze zmianą z modelem.

## Migration Plan

1. Merge → `checks` → deploy workbencha. Migracja łańcucha `social` tworzy dwie tabele w
   `lifespan`, pod istniejącym lockiem 8090, rolą aplikacji. Własność schematu `social` jest
   ustawiona od `social-data-collects-the-posts`.
2. Pierwszy przebieg zapisuje pozycje zastane. Pomiar opóźnień zaczyna się od drugiego pobrania
   każdego źródła, czyli po ~2–3 minutach.
3. Sprawdzenie: `GET /social/news/sources` wymienia 15 źródeł z `last_success_at`, a `/health`
   pokazuje heartbeat `news`.

Wycofanie: patrz Risks. Wyłączenie jednego źródła to commit usuwający wpis. Jego wiersz w
`news_sources` przestaje być wydawany, a jego newsy zostają w archiwum.
