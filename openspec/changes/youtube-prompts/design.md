## Context

Pakiet `youtube_data` ma już połowę mechanizmu: kanał, temat i film niosą tekstowe pole `profile`, a `readings` mają
klucz `(video_id, profile)`. Jedyny profil to `market` w `analysis.py`, a odpowiedź modelu to ścisły schemat JSON
(`Reading`: tezy, instrumenty, prognozy, tematy, wpływ). Kolumna `readings.instruments` (GIN) karmi filtr `GET
/videos?instrument=`, narzędzie `instrument_sentiment` i atrybut zdarzenia `youtube.film.read`. Terminal ma już
`react-markdown` z `remark-gfm`. Pocket nie czyta YouTube.

## Goals / Non-Goals

**Goals:** prompt jako wiersz w bazie z wersjami; jeden kształt odczytu wszędzie; kolejny odczyt filmu bez ponownej
transkrypcji; granica „transkrypcja to dana obca” nietykalna dla treści promptu.

**Non-Goals:** szablony ze zmiennymi w treści promptu; wybór modelu per prompt (zostaje `YOUTUBE_ANALYSIS_MODEL`);
ponowne czytanie hurtem po edycji promptu.

## Decisions

**1. Dwie tabele: `prompts` i `prompt_versions`; odczyty i obserwacje wskazują `prompt_id`.**
`prompts (id, name, seeded, deleted_at)` z unikalnym indeksem częściowym na `name WHERE deleted_at IS NULL` i co
najwyżej jednym wierszem `seeded`; `prompt_versions (prompt_id, version, body, created_at)`, tylko dopisywane.
`channels`, `topics` i `videos` zamieniają `profile text` na `prompt_id` (FK), `readings` zmienia klucz na
`(video_id, prompt_id)` i dostaje `prompt_version`. Odczyt czyta treść z wersji, nie z bieżącego promptu, więc edycja
nie przepisuje historii.
*Alternatywa:* zostawić `profile` jako nazwę promptu — odrzucona, bo zmiana nazwy (którą spec dopuszcza) zerwałaby
każde powiązanie. *Alternatywa:* jedna tabela z treścią nadpisywaną — odrzucona, bo odczyt nie mówiłby, czym powstał.

**2. Zasiany prompt to kolumna `seeded`, nie umówione `id = 1`.**
Usunięcie sprawdza kolumnę; dopisanie kanału bez promptu bierze wiersz `seeded`. Treść zasiana migracją to nowy tekst
w stylu „ułóż tekst w sekcjach…”, nie dzisiejszy `_COMMON`, który prosi o pola, których już nie ma.

**3. Ramka w kodzie, treść operatora w środku, transkrypcja osobno.**
Wiadomość systemowa = stała preambuła (transkrypcja to dana obca, odpowiedz wyłącznie w schemacie) + treść wersji
promptu + stały opis pól. Transkrypcja idzie w wiadomości użytkownika, jak dziś. Schemat JSON `strict`:
`{summary_pl, text, impact_score}`; walidacja po naszej stronie zostaje. `text` ponad `MAX_TEXT_CHARS` (20 000) jest
przycinany, nie odrzucany — tak jak dziś listy ponad sufit. Treść promptu ma limit 8 000 znaków.
*Alternatywa:* tekst wolny bez JSON — odrzucona, bo ocena wpływu (alerty) musiałaby być wyciągana z prozy.

**4. Migracja przepisuje stare odczyty w miejscu.**
`0003` renderuje dawne `key_points`, `instruments`, `predictions` i `topics` do markdown w `text`, zachowuje
`summary_pl` i `impact_score`, ustawia prompt zasiany w wersji 1 i usuwa kolumnę `instruments` z indeksem. Bez kolumny
z dawnym JSON-em: tekst niesie całą treść, a drugi format czytany „na wszelki wypadek” to dwie ścieżki w każdym
czytelniku. Wycofanie = nocny zrzut bazy; `downgrade` odtwarza schemat, nie treść.

**5. Zamówiony odczyt to ta sama droga co film wskazany ręcznie.**
`POST /videos/{id}/readings {prompt_id}` sprawdza od razu transkrypcję i limit dnia (odmowa 409/429 z powodem),
odpowiada 202 i czyta w tle pod tym samym zamkiem co pętla (`youtube-named-film-at-once`). Terminal odświeża film.
Odczyt innym promptem niż prompt filmu nie zmienia stanu filmu, więc nie wchodzi w krok „tell”.

**6. Narzędzia: o jedno mniej, nic nowego.**
`instrument_sentiment` znika (9 → 8 narzędzi), zawężenie `instrument` z `recent_videos` też. Nazwy promptów niesie
`youtube_archive_status`, więc `follow_channel`, `add_topic` i `analyse_video` przyjmują `prompt` po nazwie bez
osobnego narzędzia listy. `read_video` niesie wszystkie odczyty, tekst każdego przycięty do 8 000 znaków z notą.

## Risks / Trade-offs

- [Reguła alertu filtruje `youtube.film.read` po `instruments`; po zmianie nigdy nie pasuje] → przed wdrożeniem
  odczytać reguły na produkcji; pakiet YouTube nie sięga do bazy alertów (osobny pakiet), więc ewentualną regułę
  poprawia operator w zakładce Alerts. Zadanie w `tasks.md`.
- [Dłuższa odpowiedź to więcej tokenów wyjścia na film] → mieści się w `DAILY_TOKEN_LIMIT`, który zatrzymuje krok
  odczytu, nie pętlę; `GET /state` pokazuje zużycie.
- [Operator pisze prompt, który każe modelowi zignorować ramkę] → ramka i schemat są poza jego treścią, odpowiedź
  spoza schematu nie jest zapisywana; test z promptem-intruzem w symulacji.
- [Utrata danych przy przepisaniu odczytów] → migracja testowana na danych z każdym dawnym polem (`-m db`);
  nocny zrzut z dnia wdrożenia.

## Migration Plan

Jedna migracja `0003` w łańcuchu `youtube`, stosowana przez proces przy starcie pod zamkiem `8110` — bez kroku
operatora. Kolejność wdrożenia: sprawdzić reguły alertów → merge → `deploy-watch`. Wycofanie obrazu przez `deploy.sh`
nie cofa schematu: stary obraz na nowym schemacie nie wystartuje (sprawdzenie schematu), więc wycofanie oznacza
`alembic downgrade` i odtworzenie odczytów ze zrzutu.
