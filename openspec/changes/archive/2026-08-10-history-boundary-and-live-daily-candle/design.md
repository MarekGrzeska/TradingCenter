## Context

Motywacja: `proposal.md`, sekcja Why. Wymagania: cztery delty w `specs/`.

Stan, który kształtuje podejście — ustalony w kodzie, nie założony:

`earliest_reachable` jest dziś czytane w dokładnie dwóch miejscach: w `jobs/plan.py`, gdzie
przycina `requested_from`, i w `GET /coverage/{symbol}`, gdzie jest raportowane. Ścieżka
automatycznego uzupełniania (`ingest/backfill.py`) go **nie czyta** — opiera się na
`collect_from` pary. To znaczy, że przycięcie jest jedynym zachowaniem, jakie ta granica
dziś wywołuje poza obrębem jednego zlecenia, i że zdjęcie go nie odbiera ochrony żadnemu
automatowi.

W obrębie zlecenia granica ma wartość realną: `skip_chunks_beyond_history` domyka na jej
podstawie starsze kawałki hurtem, zamiast pozwolić każdemu wydać własne żądanie na odkrycie
tej samej krawędzi. Kawałki idą od najnowszego właśnie po to (`plan.py`,
`split_into_windows`). Ta część zostaje nietknięta.

Po stronie gatewaya `stream/` jest dziś świadomie bez wejścia/wyjścia — `forming.py` nie
zna transportu, `hub.py` dostaje wyłącznie fabrykę połączenia upstream. Zasiew granicy
okresu wymaga odczytu od providera, więc coś w tej warstwie musi zyskać dostęp do
`history.py`. To pierwszy taki dostęp i dlatego jest tu decyzją, a nie szczegółem.

## Goals / Non-Goals

**Goals:**

- Granica historii powstaje wyłącznie z pomiaru i leży tam, gdzie dane się skończyły.
- Prośba głębsza niż granica unieważnia ją, bez nowego endpointu i bez nowej rzeczy
  w interfejsie operatora.
- Wycena i wykonanie liczą ten sam zakres, mimo że tylko wykonanie zapisuje.
- `DAY` i `WEEK` mają świecę w budowie od pierwszego kwotowania, a świeca zamknięta nigdy
  nie jest rozciągana ceną z następnego okresu.
- Archiwum przestaje utrwalać okres, który jeszcze trwa — żadną z dróg, którymi świeca do
  niego dociera.
- US100 na produkcji odzyskuje się ponowną prośbą, bez kasowania pary i bez ręcznego SQL-a.

**Non-Goals:**

- Nowe pole na wire **`market-data`**. `ChunkOut` już niesie `chunk_start`, `chunk_end`
  i `state`, więc to, od kiedy zlecenie faktycznie zebrało, jest wyliczalne po stronie
  terminala — pięcioprzystankowa trasa z `CLAUDE.md` nie jest tu potrzebna i nie chcemy jej
  płacić. Pole przybywa wyłącznie w DTO gatewaya, którego terminal nie czyta.
- Zmiany w wykresie terminala. `useBarFeed.ts` i `Chart.tsx` obsługują świecę w budowie
  poprawnie; brakuje wyłącznie wiadomości od gatewaya.
- Naprawianie tego, że `bars_to_close_gap` liczy zaległość od najnowszej posiadanej świecy.
  Po odjęciu świecy bieżącej z archiwum ta arytmetyka jest znów poprawna, bo jej założenie
  („provider nie ma jeszcze bieżącego okresu") staje się prawdziwe — wymuszone, zamiast
  zakładanego.
- Wyliczanie granicy dnia z zegara — w jakiejkolwiek postaci, także jako „tymczasowe
  przybliżenie do czasu odczytu".
- Zmiana zachowania `ingest/backfill.py`. Nie czyta granicy i nie ma powodu, żeby zaczął.

## Decisions

### Granica jest zdejmowana przez ścieżkę zlecenia, nie przez planowanie

`plan_chunks` przestaje czytać `earliest_reachable` i przestaje przycinać: `effective_from`
staje się równe `requested_from`. Zdjęcie flagi robi `routers/pairs.py` przed planowaniem —
nowa funkcja w `coverage.py`, wołana tylko wtedy, gdy `requested_from` jest wcześniejsze niż
zapisana granica.

Dlaczego rozdzielone: `/jobs/estimate` deklaruje, że nic nie zapisuje, a jednocześnie musi
wyceniać dokładnie to, co wykona zlecenie — ta równość jest w `plan.py` nazwana jako powód
istnienia wspólnej arytmetyki. Gdyby zdejmowanie siedziało w `plan_chunks`, wycena albo by
zapisywała, albo liczyłaby inaczej niż wykonanie. Rozdzielenie daje jedno i drugie za darmo:
`plan_chunks` liczy tak, jakby granicy nie było, bo jej nie czyta, a zapisuje tylko ta
ścieżka, która i tak tworzy zlecenie.

Odrzucone: parametr `honour_boundary` w `plan_chunks`. Dwie ścieżki liczące różnie to
dokładnie ten kształt, którego moduł unika — a jedyna wartość, jaką parametr mógłby przyjąć
w wycenie, to i tak „nie honoruj".

Konsekwencja przyjęta świadomie: `PairEstimate.clipped` przestaje kiedykolwiek być prawdą,
bo przycięcie było jedynym jego źródłem. Pole zostaje w kontrakcie (terminal je renderuje,
usunięcie jest większą zmianą niż ten błąd), ale traci zastosowanie. Fakt „zebrano od
później, niż proszono" przenosi się tam, gdzie jest naprawdę znany — do wyniku zlecenia.

### To, od kiedy faktycznie zebrano, terminal wylicza z kawałków

Wymaganie `market-data-jobs` żąda, żeby zlecenie odnotowało datę faktycznie użytą;
implementacja wyrzuca `effective_from` do kosza. Zamiast dokładać pole na wire, terminal
bierze najstarszy `chunk_start` spośród kawałków w stanie `done` — ma je wszystkie
w `JobPairViewOut.chunks`. Wiersz „0 świec" przestaje być nie do odróżnienia od awarii:
widać, że kawałki poszły, ile ich zeszło i gdzie się zatrzymały.

Odrzucone: nowe pole `effective_from` w `JobPairViewOut`. Trasa z `CLAUDE.md` (contract.py →
`contract:generate` → `archive.ts` → `types.ts` → komponent) kosztuje pięć przystanków za
wartość, którą wywołujący już ma w ręku.

### Granica zapisywana z najstarszej odebranej świecy

`execute_chunk` przestaje przekazywać `chunk.chunk_start` jako punkt granicy. Gdy
`page.history_ended`, granicą jest `min(period_start)` z tego, co przyszło. Zakres pokrycia
nadal obejmuje całe okno kawałka — to jest zweryfikowane i ma zostać — ale flaga jedzie
z punktem, który provider faktycznie pokazał.

Kawałek, który wraca pusty, nie zapisuje granicy w ogóle. Nie ma czym jej umiejscowić,
a zapisanie jej na krawędzi żądania jest właśnie tym błędem, który wywołał tę zmianę.

### Koniec historii wymaga zebranej świecy

W `capital_gateway/history.py` `history_ended` MUST NOT paść, gdy pusta odpowiedź dotyczyła
okna, przed którym moduł nie zebrał jeszcze ani jednej świecy — czyli gdy `collected` jest
puste. Provider odpowiada `error.prices.not-found` nie tylko na końcu historii, a pierwsze
okno jest jedynym, którego nic nie potwierdza.

Odrzucone: powtórzenie żądania przed uznaniem końca. Kosztuje żądanie na każdą parę, która
naprawdę się skończyła, i nie odróżnia niczego, czego nie odróżnia warunek wyżej.

### Świeca w budowie na `DAY`/`WEEK`: granica z providera, przeładowywana na zdarzeniach

`Room` dostaje wstrzykniętą funkcję odczytu bieżącej świecy — tak samo jak dziś dostaje
fabrykę upstreamu, więc `stream/` nadal nie zna transportu i nadal daje się testować bez
gniazda. Odczyt to jedno żądanie o jedną świecę w tej rozdzielczości; niesie prawdziwą
granicę sesji, bo pochodzi od providera.

Przeładowanie granicy dzieje się na trzech zdarzeniach i **nie** przez odpytywanie w pętli:

1. otwarcie pokoju — inaczej pierwsze kwotowanie nie ma czego rozciągać, i to jest ten błąd,
2. pierwsze kwotowanie po zamknięciu świecy przez providera — zamknięcie **jest** sygnałem,
   że granica się przesunęła, więc kolejny kwot należy już do okresu, którego początku nie
   znamy,
3. ponowne połączenie po zerwaniu — okres mógł się przetoczyć, gdy nikt nie patrzył.

Koszt w normalnym biegu: jedno żądanie na pokój na dobę. Odrzucone: odpytywanie co N minut —
ta sama informacja za wielokrotność żądań, i tak spóźniona o cały interwał.

Punkt 2 opiera się na pomiarze zapisanym w `upstream.py`: `ohlc.event` pada wyłącznie przy
zamknięciu. Gdyby okazało się, że dla `DAY` pada także w trakcie okresu, zachowanie pozostaje
poprawne — po prostu przeładowań jest więcej.

### Czy REST zwraca bieżącą, niezamkniętą świecę dzienną — mierzone przed implementacją

Punkt 2 wyżej zakłada, że tuż po zamknięciu okresu odczyt jednej świecy `DAY` zwraca już
**nową**, rozpoczętą świecę, a nie tę właśnie zamkniętą. Tego nie wiemy z pewnością i jest to
założenie nośne, więc pierwsze zadanie w `tasks.md` to pomiar na demo, w duchu `test_live.py`
— tak samo jak zmierzono granicę kubełka dla rozdzielczości pochodnych.

Jeśli pomiar wyjdzie odwrotnie, projekt nie zmienia kształtu, zmienia degradację: dopóki
provider nie pokaże świecy nowego okresu, moduł nie publikuje dla niego nic i ponawia odczyt
przy kolejnych kwotowaniach, z odstępem. Milczenie jest tu poprawną odpowiedzią — scenariusz
„Provider nie odpowiada na pytanie o granicę" mówi dokładnie to. Zepsuta świeca, którą
naprawiamy, wzięła się z odwrotnego wyboru.

Ten sam pomiar odpowiada na drugie pytanie, bo dotyczy tej samej odpowiedzi providera: czy
najnowsza świeca odczytu należy do okresu, który jeszcze trwa. Tam jednak wynik nie jest
warunkiem — decyzja niżej jest poprawna w obie strony i nic nie traci, jeśli okaże się, że
provider bieżącego okresu nie oddaje.

**Zmierzone 10 sierpnia 2026, `uv run pytest -m live --run-live`, 8/8 zielonych.** Provider
**oddaje** bieżący, niedomknięty okres: najnowsza świeca `MINUTE_5` odczytu sięgającego
teraźniejszości pokrywa się z kubełkiem, w którym jesteśmy, a odczyt `DAY` przy otwartym
rynku zawiera dzisiejszą świecę. `marketStatus` zgadza się z tym, czy płyną kwotowania.

Czyli obie decyzje niżej chodzą **główną** gałęzią, nie degradacyjną: zasiew dostaje od
providera okres, który faktycznie trwa, a oznaczanie świecy w budowie ma co oznaczać.
Gałąź „provider nie otworzył jeszcze nowego okresu" zostaje jako zabezpieczenie i jest
pokryta testem, ale w normalnym biegu się nie uruchamia.

### Świeca w budowie jest oznaczana przez gateway, a rozstrzyga o tym stan rynku

`capital_gateway/dtos.py` — DTO `Candle` zyskuje pole mówiące, czy okres się domknął. To
zmiana kontraktu między modułami i dlatego jest w tej zmianie, a nie obok niej.

Wyznaczanie jest dwutorowe, bo dwie klasy rozdzielczości wiedzą o sobie różne rzeczy:

- **Stała długość okresu** (`MINUTE` … `HOUR_4`) — arytmetyka na `PERIOD_SECONDS`, które
  `history.py` już trzyma. Dokładna, bez żadnego zgadywania.
- **`DAY` i `WEEK`** — granicy sesji liczyć nie wolno, i to jest zasada powtórzona w tym
  repozytorium trzy razy (`rollups.py`, `stream/forming.py`, spec `market-data-store`).
  Rozstrzyga stan rynku: dopóki rynek instrumentu jest otwarty, jego najnowsza świeca należy
  do okresu, który trwa. Gateway już to wie — `mapping.py` mapuje `marketStatus ==
  "TRADEABLE"` na `tradeable` w szczegółach instrumentu. Żadnej nowej wiedzy, żadnego nowego
  źródła.

Odczyt zakotwiczony w przeszłości nie ma świecy w budowie w ogóle — jego najnowszy okres
zamknął się dawno. To zdejmuje pytanie ze wszystkich kawałków zlecenia poza najnowszym.

Odrzucone: arytmetyka na północy UTC dla `DAY`, choćby „tymczasowo". Dokładnie ten wybór
wyprodukował świecę, którą naprawia błąd drugi. Odrzucone też: zostawienie decyzji
`market-data`. Gateway jest jedynym modułem rozmawiającym z providerem, więc jedynym, który
zna stan rynku bez dokładania sobie żądania.

Po stronie `market-data` zmienia się jedna linia sensu: `gateway/history.py` przestaje
wpisywać „zamknięta" na sztywno i czyta pole. `store.write_candles` już odmawia świecy
w budowie — reguła istnieje i dotąd nie miała na czym zadziałać. `market_data/contract.py`
nie zmienia się wcale: `CandleOut` nadal nie niesie tego pola, bo odczyt zakresu nadal
zwraca wyłącznie świece zamknięte. Różnica jest taka, że jego komentarz przestaje być
życzeniem.

### Świeca w budowie ze strumienia, zamknięta z archiwum

Naprawy dwa i trzy są jedną decyzją architektoniczną i wolno je wdrożyć wyłącznie razem.
Dziś archiwum trzyma świecę bieżącą i zamkniętą, a strumień nie daje dla `DAY`/`WEEK` żadnej.
Samo odjęcie świecy bieżącej z archiwum zabrałoby ją z wykresu i nie dało nic w zamian —
operator zobaczyłby regres. Dopiero zasiew ze strumienia sprawia, że po tej zmianie bieżąca
świeca dalej jest na ekranie, tyle że pochodzi stamtąd, skąd powinna, i wreszcie się rusza.

## Risks / Trade-offs

**Wycena zaczyna obiecywać pełny zakres także tam, gdzie provider naprawdę jest płytki** →
Świadomy wybór: nikt w tym momencie nie wie, jak głęboko sięga provider, a udawanie, że
wiemy, jest tym błędem. Koszt sprawdzenia jest ograniczony — kawałki idą od najnowszego,
pierwszy trafiony na krawędź domyka resztę hurtem, więc wychodzi jedno do dwóch żądań na
parę. Wynik zlecenia pokazuje, dokąd faktycznie zeszło.

**Powtarzana prośba o tę samą, nieosiągalną głębokość sprawdza granicę za każdym razem** →
Ograniczone tym samym mechanizmem hurtowego pomijania. Merytorycznie właściwe: capital.com
pogłębia własną historię z czasem, więc odpowiedź sprzed tygodnia nie jest odpowiedzią na
dziś.

**Jedno dodatkowe żądanie REST na pokój strumienia** → Idzie przez tę samą bramkę
dziesięciu żądań na sekundę co odczyty operatora. Jedno na dobę na parę jest pomijalne,
ale bramka jest wspólna i warto to widzieć przy zmianie liczby śledzonych par.

**`stream/` zyskuje pierwszą zależność od odczytu historii** → Wstrzykiwana, nie
importowana, więc `forming.py` i `hub.py` nadal testują się bez gniazda i bez HTTP. To ta
sama sztuczka co `FetchPage` w `history.py`.

**Pomiar z punktu o zasiewie może wyjść odwrotnie** → Degradacja jest zaprojektowana
i pokryta scenariuszem, więc wynik pomiaru zmienia implementację jednej gałęzi, a nie
podejście ani delty.

**Rynek zmienia stan między odczytem a zapisem** → Odczyt `DAY` tuż przed zamknięciem sesji
oznaczy najnowszą świecę jako trwającą i archiwum jej nie zapisze; minutę później okres jest
zamknięty, a świecy nie ma. Domknie ją kolejne uzupełnianie, bo zaległość liczona od
poprzedniej świecy urośnie powyżej okresu. Odwrotny przypadek — odczyt tuż po otwarciu
sesji, gdy provider zdążył już oddać nową świecę, a stan rynku jeszcze się nie odświeżył —
zapisałby świecę bieżącą jako zamkniętą, czyli dokładnie dzisiejsze zachowanie, i poprawi się
przy następnym odczycie. Obie strony są samonaprawialne w granicach jednego okresu; żadna nie
utrwala wartości na stałe. Cache stanu rynku ma minutę życia (`market_status.py`), więc okno
błędu jest tego rzędu.

**Trzy naprawy w jednej zmianie** → Wybór operatora, odnotowany świadomie. Naprawy dwa i trzy
muszą jechać razem (patrz decyzja wyżej), naprawa pierwsza jest niezależna. Delta obejmuje
cztery zdolności, więc `review.md` będzie odpowiednio dłuższy, a PR wart podziału na commity
po grupach zadań.

## Migration Plan

**Jest migracja `0007` i MUSI zostać zastosowana zanim ruszy nowy `market-data`.** Nowy kod
czyta `history_ends_at` w każdym odczycie pokrycia — `/candles`, `/coverage`,
`/jobs/estimate`, `POST /pairs` — więc uruchomiony przed migracją odpowiada na to wszystko
pięćsetką. To nie jest degradacja, to cztery endpointy naraz.

Migracja nie jedzie ani z obrazem, ani z workflow. `Dockerfile` mówi wprost dlaczego
(8.6: restart nie ma ścigać się o migrację), a `deploy-market-data.yml` nie robi jej
w ogóle — więc robi ją operator, i jest to krok, o którym trzeba pamiętać, bo nic o nim
nie przypomni.

Kolejność:

1. Wdrożyć `capital-gateway` w całości — warunek na `history_ended`, oznaczanie świecy
   w budowie i zasiew strumienia razem. Osobno nie wolno: bez warunku `market-data` skasuje
   granicę i natychmiast zapisze ją ponownie z tego samego błędu, a bez zasiewu odjęcie
   świecy bieżącej z archiwum zabrałoby ją z wykresu, nie dając nic w zamian.
2. **`uv run alembic upgrade head`** z tożsamością produkcyjną (`DATABASE_USER` ustawione —
   `migrations/env.py` używa tego samego mechanizmu co moduł).
3. Wdrożyć `market-data`. Nowe pole w DTO gatewaya było do tej chwili po prostu ignorowane
   — `market-data` czyta odpowiedź gatewaya przez własny model, więc kolejność 1 → 3 jest
   bezpieczna w tę stronę i tylko w tę.
4. Operator prosi o US100 od 2024-01-01 dla wszystkich siedmiu rozdzielczości. Granica
   zostaje zdjęta, zlecenie planuje pełny zakres i zbiera to, co provider ma.
5. Sprawdzić `GET /coverage/US100?resolution=DAY`: `earliest_reachable` jest albo puste,
   albo wskazuje moment, w którym faktycznie skończyły się dane.

Krok 2 zostawia wąskie okno, w którym stary jeszcze writer może trafić na koniec historii
i spróbować zapisać flagę bez punktu — check-constraint go wtedy odrzuci i kawałek padnie,
raz, retryowalnie. To jest cena rzędu jednego kawałka, a cena odwrotnej kolejności to
cztery endpointy leżące do czasu ręcznej interwencji. Rozważano rozbicie na dwie migracje
po przeciwnych stronach kroku 3; odrzucone, bo dokłada operatorowi krok, o którym też nikt
nie przypomni, żeby uniknąć czegoś, co jest jedną nieudaną próbą.

Wycofanie: rewert obu modułów, migracji **nie** cofać. Kolumna zostawiona na miejscu nie
przeszkadza kodowi sprzed zmiany, a `downgrade -1` na działającej produkcji zabrałby ją
spod zapytań, które właśnie ją czytają — czyli powtórzyłby tę samą awarię z drugiej strony.
Flagi zdjęte do czasu wycofania zostają zdjęte, co jest bezpieczne: najgorsze, co robi brak
granicy, to jedno dodatkowe żądanie przy kolejnym zleceniu.

**Co się faktycznie wydarzyło.** Ten plan przy wdrożeniu nie istniał w tej postaci — sekcja
otwierała się zdaniem „bez migracji bazy", napisanym zanim `0007` powstała i nigdy potem
nieprzejrzanym. PR zmergowano, trzy deploye przeszły, i produkcyjny `market-data` stanął na
nowym kodzie przy bazie na `0006`. Kreator odpowiedział „the archive failed to answer this
request", bo tak wygląda `UndefinedColumnError` po przejściu przez catch-all w `app.py`.
Naprawione ręcznym `alembic upgrade 0007` na produkcji. Szczegóły w `review.md` — to jest
ten rodzaj rzeczy, dla którego ten plik istnieje.
