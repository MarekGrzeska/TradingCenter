## Context

Workbench składa osiem pakietów, z których żaden nie importuje sąsiada; `workbench/app.py` montuje
każdy pod prefiksem, a `workbench/local_tools.py` podaje ich FastMCP rozmowie i zespołom jako
funkcje. Najbliższe wzory: `social_data` (pętla, odczyt modelu, alerty przez `/telegram`
w procesie) i `polymarket_data` (lista obserwacji edytowana przez operatora i agenta). Research
i koszty: `docs/youtube-archiwum-projekt.html`, `docs/supadata-koszty.html`.

## Goals / Non-Goals

**Goals:** cała droga filmu działa lokalnie za zero na symulacji albo na darmowych źródłach;
wymiana dostawcy transkrypcji na produkcyjnego to jedna klasa i jedno ustawienie.

**Non-Goals:** odtwarzanie HTTP YouTube w symulacji; skalowanie ponad jednego operatora.

## Decisions

**1. Osobny pakiet, nie drugie źródło w `social_data`.** `social_data` ma regułę „zestaw wyłącznie
czyta" i jeden stały strumień krótkich postów. Tu jest lista obserwacji edytowana narzędziami,
teksty po kilkadziesiąt KB, cykl życia z ponowieniami i budżety dostawców. Doklejenie zmieniłoby
regułę zapisu `social` — a granica pakietu to granica tego, co wolno pisać. Alternatywa
(osobny proces) odrzucona: nie ma nowej granicy bezpieczeństwa.

**2. Montaż warunkowy zamiast długiej gałęzi.** Brak `YOUTUBE_DATABASE_URL` = pakiet
niezamontowany, tak jak brak `TRADING_MCP_URL` = brak narzędzi rachunku. Pozwala wnosić zmianę do
`main` małymi PR-ami bez wpływu na produkcję. Alternatywa — gałąź do czasu infrastruktury — kupuje
prostotę dziś za konflikty z każdym PR-em workbencha. Wymóg „wszystko albo nic" zostaje dla
skonfigurowanej bazy (delta `workbench-process`). `tests/test_route_collisions.py` i test warstw
muszą widzieć pakiet zawsze — montaż warunkowy dotyczy aplikacji, nie listy pakietów.

**3. Symulacja na poziomie interfejsu, nagrania HTTP tylko dla adapterów.** Symulowani dostawcy
implementują te same trzy protokoły co prawdziwi (`VideoSource`, `TranscriptProvider`,
`Analyser`) i są wybierani ustawieniem. Alternatywa — fałszywy serwer HTTP udający YouTube i
Supadatę — dałaby wierność formatu, ale każdy nowy dostawca wymagałby nowego fałszywego serwera,
a scenariusze czasowe (napisy po 2 h) i tak trzeba by pisać osobno. Format odpowiedzi prawdziwych
adapterów (`rss`, `data_api`, `direct`) sprawdzają zamiast tego testy na zapisanych odpowiedziach
(`respx`), bez sieci.

**4. Scenariusz jako plik JSON z czasem względnym, ziarnem i zegarem.** `youtube_data/sim/
scenarios/default.json`: kanały, filmy z `published_after_start`, zachowanie napisów per film
(`immediate` / `after_minutes` / `never` / `async_polls`), odsetek blokad, opóźnienia, koszt
wywołań w jednostkach, dzienne sufity, katalog do wyszukiwania i przygotowane odczyty. Zegar jest
wstrzykiwany (`Clock`), a `YOUTUBE_SIM_SPEED` go przyspiesza; losowanie z ziarnem ze scenariusza,
więc przebieg jest powtarzalny. Alternatywa — losowe fake'i generowane w kodzie — nie dałaby się
powtórzyć ani przeczytać.

**5. Odczyt symulowany z przygotowanych odpowiedzi, nie z heurystyki.** Film w scenariuszu niesie
gotowy odczyt (albo znacznik `unusable`, który daje odpowiedź niezgodną ze schematem); film bez
przygotowanego odczytu dostaje odczyt neutralny. Tokeny liczone jako długość tekstu / 4. Heurystyka
słów kluczowych odrzucona: udaje inteligencję, której nie ma, i myli przy ocenie ekranu.

**6. Kanał po `@uchwycie` wymaga źródła, które umie go rozwiązać.** RSS przyjmuje tylko
`channel_id`; rozwiązanie `@uchwytu` robi `data_api` (`channels.list forHandle`, 1 jednostka) albo
symulacja. Bez klucza API `rss` przyjmuje adres `/channel/UC…` lub identyfikator, a `@uchwyt`
dostaje odmowę z powodem. Alternatywa — parsowanie strony kanału — odrzucona: krucha i z chmury
blokowana.

**7. Transkrypcja w osobnej tabeli.** `videos` trzyma stan i metadane, `transcripts` tekst.
Zapytania listy i kolejki nie dotykają TOAST-u; indeks `(state, next_attempt_at)` obsługuje
kolejkę. Koszt zapytań pętli i ekranu wyceni `db-cost-check` przed merge.

**8. Klucz blokady migracji `8110`.** Pierwszy klucz, który nigdy nie był portem — kolejny po
`8100`, spoza listy portów stałych.

## Risks / Trade-offs

- [Symulacja rozjedzie się z rzeczywistością] → wartości scenariusza domyślnego wzięte z researchu
  (koszty jednostek, 206 płatne, 202 dla długich filmów); przy wejściu dostawcy produkcyjnego
  scenariusz dostaje jego zmierzone zachowania.
- [Dziesięć narzędzi powiększa powierzchnię rozmowy] → opisy krótkie; jeśli istnieje sufit
  powierzchni narzędzi, zmiana go podnosi jawnie albo mieści się w nim.
- [`direct` z domowego IP przestanie działać przy częstym odpytywaniu] → w dev domyślnie `sim`;
  `direct` z małym limitem partii.
- [Montaż warunkowy ukryje zapomnianą konfigurację produkcji] → log startu nazywa brak pakietu;
  włączenie produkcji to osobna zmiana z własną sondą.

## Migration Plan

Produkcja: nic — ustawienie nie istnieje, pakiet się nie montuje. Dev: `scripts/dev.py` tworzy bazę
`youtube` i rolę jak pozostałe; wycofanie to usunięcie `YOUTUBE_DATABASE_URL` z `.env`.

## Open Questions

- Retencja surowych transkrypcji (ToS: 30 dni dla danych z API) — rozstrzygnie zmiana produkcyjna.
- Czy scenariusz domyślny ma odtwarzać polskie kanały z ubogimi auto-napisami — do skalibrowania po
  pomiarze F0 na prawdziwych filmach.
