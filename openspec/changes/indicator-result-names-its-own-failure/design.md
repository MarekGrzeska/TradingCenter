## Context

Motywacja: `proposal.md`. Wymagania: `specs/`.

Stan dzisiejszy, bo z niego wynika kształt zmiany. `routers/indicators.py` liczy w trzech etapach:
najpierw rozwiązuje wpisy i parametry, potem — w jednym bloku połączenia — czyta serię rysowaną,
serie grubsze wymagane przez `htf_levels_*`/`pivots_*` i serię drobną wymaganą przez
`session_range_*`/`opening_range`/`time_profile`, dopiero na końcu wywołuje `_result_out` dla
każdego wpisu. Odmowy z powodu brakującej serii pomocniczej podnoszone są w etapie środkowym,
jako `HTTPException` — czyli zanim którykolwiek wskaźnik zdążył cokolwiek policzyć. Stąd
wszystko albo nic: nie ma miejsca, w którym część wyników już istnieje, a jedna seria się nie
udała.

Dwie rzeczy z tego bloku nie znikną i kształtują rozwiązanie. Odczyt serii pomocniczej jest
wspólny dla wielu wpisów — trzy okna sesji i profil czasowy czytają tę samą serię drobną, i mają
ją czytać raz. Semafor obejmuje cały blok obliczeniowy, bo to on jest obietnicą, że wskaźniki nie
zagłodzą strumienia świec.

Ta zmiana stoi na `add-technical-indicators`: obie dotykane zdolności istnieją dziś wyłącznie
w delcie tamtej, niezarchiwizowanej zmiany.

## Goals / Non-Goals

**Goals:**

- Wynik niesie własną porażkę, w tym samym miejscu, w którym niósłby wartości.
- Odczyt serii pomocniczej robiony raz na serię, nie raz na wpis, mimo że porażka jest per wpis.
- Konsument, który pola nie czyta, nie widzi nic gorszego niż dziś.

**Non-Goals:**

- Zmiana ziarnistości odmów wynikających z pomyłki wołającego. Nieznany identyfikator, parametr
  poza zakresem, odwrócony zakres i sufit żądania zostają odmową całości — decyzja niżej.
- Ponawianie po stronie modułu. Brakująca seria nie pojawi się przez powtórzenie odczytu.
- Zbieranie brakującej serii przy okazji. Co jest archiwizowane, jest decyzją operatora
  (`market-data-tracking`), a nie skutkiem ubocznym rysowania wykresu.

## Decisions

### Granica biegnie po tym, czyj to jest problem

Rozważone: (a) wszystko per wynik, (b) tylko brak serii per wynik, (c) brak serii i parametry per
wynik.

Wybrane (b). Brak serii nie jest pomyłką wołającego — jest właściwością tego, co ktoś zdecydował
się zbierać, zmienia się w czasie bez zmiany żądania i **różni się wpis po wpisie**, więc jedyne
miejsce, w którym da się o nim powiedzieć prawdę, jest przy wpisie. Nieznany identyfikator i
parametr poza zakresem są odwrotnością tego: nie zmienią się, dopóki nie zmieni się żądanie, są
takie same przy każdym powtórzeniu i są czyjąś literówką. Odmowa na literówkę jest głośna;
częściowa odpowiedź na literówkę przechodzi niezauważona przez konsumenta, który nie sprawdza
każdego wyniku — a właśnie takim konsumentem jest każdy, kto do dziś nie musiał.

Odrzucone (a) mimo że jednolitsze: kupuje jednolitość ceną wyciszenia jedynych błędów, które
naprawdę są błędami. Odrzucone (c) z tego samego powodu w mniejszej skali — katalog podaje zakres
każdego parametru, więc parametr poza nim to żądanie zbudowane wbrew temu, co konsument przeczytał.

### Pole `error` na istniejącym wyniku, nie osobna lista porażek

Rozważone: (a) `error: str | None` w `IndicatorResultOut`, (b) osobna lista `failures` obok
`results`, (c) unia typów — wynik albo porażka.

Wybrane (a). Konsument iteruje po `results`, żeby cokolwiek narysować, więc porażka postawiona
tam jest w miejscu, przez które i tak przechodzi; przy (b) musiałby złączyć dwie listy po
identyfikatorze, żeby się dowiedzieć, dlaczego czegoś nie ma — a najprostsza implementacja
konsumenta (pominięcie listy, której nie zna) daje dokładnie dzisiejsze zachowanie: wskaźnik
znika bez słowa. Odrzucone (c), bo generowany TypeScript unii dyskryminowanej jest znacznie
gorszy w użyciu niż pole opcjonalne, a `terminal/src/data/archive.ts` musiałby rozgałęziać się
przed mapowaniem zamiast po nim.

Wynik z `error` **jest w `results`** i zachowuje swój `id` oraz rozwiązane `params`. Nie niesie
`warmup_bars` ani `anchored_at` (nic nie zostało wczytane) i ma `settled: false` — nie dlatego, że
historia była płytka, tylko dlatego, że nie ma czego uznać za ustalone.

### `_exactly_one_shape` zmienia się w „dokładnie jeden albo dokładnie żaden"

Walidator, który dziś wymusza jeden z czterech kształtów, jest tym, co pilnuje, żeby pusty wynik
nie przeszedł niezauważony. Zostaje, rozszerzony: dokładnie jeden kształt i `error` puste, albo
zero kształtów i `error` ustawione. Trzecia kombinacja — kształt i przyczyna naraz — jest
sprzecznością i MUST się nie dać zbudować, bo to ona zamieniłaby „nie policzono" w „policzono
pusto" u konsumenta, który czyta tylko kształt.

To jest ta sama zasada, którą wymaganie „Wynik ma jeden z czterech kształtów" nazywa dla
konsumenta, wymuszona po stronie modelu, a nie zostawiona dyscyplinie autora — tak samo jak
granica wobec strategii w `add-technical-indicators`.

### Odpowiedź częściowa to `200`, nie `207`

Rozważone: `200` z przyczynami w treści, `207 Multi-Status`.

Wybrane `200`. Treść już niesie wynik każdego wpisu z osobna, więc kod stanu mówiący „część się
nie udała" byłby drugim miejscem do sprawdzenia, mówiącym mniej niż pierwsze. `207` jest przy tym
z WebDAV-a i mało który klient HTTP traktuje go jak sukces bez pomocy. Odmowa dalej jest `422` i
dalej ma kształt `Problem` — konsument rozróżnia „żądanie było złe" od „archiwum czegoś nie ma"
po kodzie stanu, bez czytania treści.

### Odczyt serii pomocniczej: raz na serię, porażka rozdana wpisom

Odczyty serii pomocniczych zostają tam, gdzie są — jeden na rozdzielczość, w tym samym bloku
połączenia. Zmienia się to, co robią, gdy nic nie znajdą: zamiast podnosić `HTTPException`,
zapisują przyczynę pod tą rozdzielczością. Etap trzeci, budujący wyniki, pyta o tę przyczynę po
tym, czego wpis potrzebuje (`needs_minute_series`, `higher_resolution`) i albo liczy, albo zwraca
wynik z przyczyną.

Alternatywa — odczyt per wpis, żeby porażka rodziła się tam, gdzie ma być zgłoszona — została
odrzucona: trzy okna sesji i profil czasowy czytałyby wtedy tę samą serię drobną cztery razy,
w bloku, który istnieje po to, żeby wskaźniki nie zajmowały procesu dłużej, niż muszą.

Sufit dla serii drobnej (`FINE_RESOLUTION` × zakres) zostaje odmową całego żądania, mimo że dotyczy
tych samych wpisów. Jest sufitem, a sufity są po stronie kształtu żądania — patrz decyzja pierwsza.

### Terminal: wybór operatora zostaje jego wyborem

Rozważone: odznaczyć nieudany wskaźnik, zostawić zaznaczony.

Wybrane: zostawić. Odznaczenie jest decyzją, której operator nie podjął, a jej cena jest
niesymetryczna — po zebraniu brakującej serii wskaźnik ma zacząć się rysować sam, przy najbliższym
dopytaniu, bez klikania od nowa. Nieudany wynik nie idzie do rysowania (żadna seria, żaden
prymityw), a plakietka i istniejący toast nazywają go po identyfikatorze wraz z przyczyną —
toast dokłada się do tego, co już powstało na `add-technical-indicators`, i deduplikuje po tym
samym kluczu slotu.

## Risks / Trade-offs

- **Konsument, który nie czyta `error`, dostaje wynik bez kształtu** → walidator gwarantuje, że
  wtedy wszystkie cztery kształty są puste, a nie że jeden jest pusty „normalnie". Mapper
  terminala pomija taki wynik przed rysowaniem, zamiast wpuszczać go z pustą listą.
- **Częściowa odpowiedź wycisza problem archiwum** — wskaźnik nie działa od tygodni, a nikt nie
  patrzy → dlatego przyczyna idzie do toasta, nie tylko do plakietki, i nazywa wskaźnik po
  identyfikatorze. To jest cała zmiana widoczna dla operatora.
- **`settled: false` zaczyna znaczyć dwie rzeczy** — płytka historia i brak serii → rozróżnia je
  `error`; `settled` bez `error` to dalej wyłącznie płytka historia. Ryzyko jest w opisie pola,
  nie w danych, i tam zostaje zaadresowane.
- **Kolejność wobec `add-technical-indicators`** — delta MODIFIED wobec wymagań, których jeszcze
  nie ma w `openspec/specs/` → ta zmiana nie może zostać zarchiwizowana przed tamtą; scalanie
  delty do specyfikacji, która jeszcze nie istnieje, nie ma czego zmodyfikować.

## Migration Plan

Brak migracji bazy, brak zmian w `infra/`. Nic z tego nie jest przechowywane. Wdrożenie to nowy
obraz `market-data` i nowy build terminala; wycofanie to `revert`.

Kolejność w obrębie zmiany jest wymuszona przez `CLAUDE.md`, „A new field on market-data's wire":
model w `contract.py`, potem `pnpm contract:generate`, dopiero potem kod terminala. Job terminala
i tak wystartuje w CI przy zmianie `contract.py`, więc pominięcie kroku środkowego zatrzyma się na
`contract:check`.

Wobec `main` ta zmiana wchodzi po `add-technical-indicators`.
