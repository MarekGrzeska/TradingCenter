## Context

Motywacja: `proposal.md`, „Why". Wymagania: delta w `specs/`.

Co już stoi i czego ta zmiana nie rusza:

- `set_chart` jest jedynym narzędziem własnym modułu `agent`. Sprawdza żądanie **przed**
  zapisem, przez `market-mcp`, i odmawia zdaniem, które wraca do modelu.
- Polecenia leżą w `chart_commands` jako log z rosnącym `id`. Terminal trzyma kursor
  w `localStorage` (`CHART_CURSOR_KEY`) i czyta `GET /chart?after=`, dostając **złożone**
  polecenie ze wszystkiego, czego jeszcze nie zastosował (`ChartCommand.merged_with`).
- `Chart.tsx` czyści serię przy zmianie `source`/`symbol`/`resolution`, a pierwszy
  `redraw` nowej serii woła `fitContent()` — tu ginie kadr. Dalsze `redraw` już go
  pilnują, przesuwając zakres logiczny o liczbę doklejonych świec.
- `useOlderBars` stronicuje historię w tył: `PAGE_BARS = 300`, `MAX_PAGES = 20`,
  wyzwalane przez `needsMore()` pytające o `visibleLogicalRange.from < OLDER_MARGIN_BARS`.
- Migawka do modelu powstaje w `activeChartSnapshot(gridStore)` — czyta **wyłącznie**
  konfigurację slotu, a więc nie ma dziś dostępu do tego, co widać.

Ograniczenie, które kształtuje całą resztę: `gridStore` zapisuje swoją migawkę do
`localStorage`, a `parseGridConfig` odrzuca całość, gdy nie zna kształtu. Wszystko, co
dokładamy, musi albo mieścić się w tym kontrakcie, albo świadomie stać obok niego.

## Goals / Non-Goals

**Goals:**

- Jeden kształt kadru używany w trzech miejscach: schemat narzędzia, wiersz w bazie,
  DTO terminala.
- Kadr wykonalny: terminal dociąga pod niego historię i mówi, gdy się nie da.
- Zachowanie kadru przy zmianie interwału niezależne od tego, kto tę zmianę wywołał.

**Non-Goals:**

- Kadr jako trwały stan slotu. To żądanie jednorazowe; po nim wykres należy do myszy.
- Sterowanie skalą cen (osią pionową). Kadr dotyczy osi czasu.
- Animowane przejście do kadru. Skok jest skokiem.
- Kadr per slot inny niż aktywny. Polecenie agenta trafia do aktywnego slotu, tak jak dziś.

## Decisions

### Kadr to płaski obiekt z regułą „dokładnie jeden sposób"

`focus` niesie pięć opcjonalnych pól: `from`, `to`, `around`, `bars`, `last_bars`.
Rozpoznane formy: (`from` + `to`), (`around` + `bars`), (`last_bars`). Narzędzie sprawdza
ręcznie, że wypełniona jest dokładnie jedna, i odmawia zdaniem wymieniającym trzy formy.

Rozważane i odrzucone: `oneOf` w JSON Schema z wariantami. Czytelniejsze formalnie, ale
modele radzą sobie z nim gorzej niż z płaskim obiektem i opisem pola, a błąd i tak wraca
tą samą drogą — odmową, którą model umie poprawić. Reszta tego pliku jest pisana ręcznie
z tego samego powodu.

Rozważane i odrzucone: jawny dyskryminator `kind`. Jedno pole więcej do pomylenia,
a informacji nie dokłada — komplet wypełnionych pól mówi to samo.

### Czas absolutny na drucie, epoch-sekundy w terminalu

`from`, `to`, `around` to znaczniki ISO 8601 z offsetem (UTC). Nie „ostatnie 3 dni" i nie
liczba względna: polecenie leży w logu i musi znaczyć po godzinie to samo. `last_bars`
jest wyjątkiem nazwanym w specyfikacji — mówi „koniec serii", cokolwiek nim jest.

Terminal zamienia ISO na epoch-sekundy w swoim mapperze, tak samo jak `archive.ts` robi to
dla świec. Poza mapperem żadne pole drutu nie jest widziane.

### Granice liczby świec: 10 … 1000

`bars` i `last_bars` mieszczą się w `[10, 1000]`. Dół bierze się z czytelności — kadr na
trzy świece jest przybliżeniem, którego wykres nie umie sensownie pokazać. Góra z tego, co
terminal umie dociągnąć bez kwadransa czekania: `PAGE_BARS × MAX_PAGES` to 6000, ale kadr
na 6000 świec to dwadzieścia odczytów, więc granica stoi wyraźnie niżej. Liczba jest
w opisie schematu i w zdaniu odmowy, żeby model nie musiał zgadywać.

### Kolumna `focus` w `chart_commands`, składana tak jak reszta

Nowa migracja `0006` dokłada nullowalną kolumnę `JSONB focus` i rozszerza
`chart_commands_sets_something` o nią. JSONB z tego samego powodu co `indicators`: to jest
obiekt na drucie i czytelnik nie powinien parsować stringa, żeby go zobaczyć.

`merged_with` traktuje `focus` jak każde inne pole — nowszy wygrywa, pominięty zostawia
poprzedni. Konsekwencja przyjęta świadomie: terminal, który wraca po godzinie, dostanie
też kadr sprzed godziny i skoczy tam, gdzie agent prosił. Rozważane odrzucanie kadru
starszego niż N minut — odrzucone: żaden próg nie jest przewidywalny dla operatora, a
„agent kazał mi patrzeć na 3 stycznia, odświeżyłem stronę i wróciłem na 3 stycznia" jest
zachowaniem, którego się spodziewa. Panel i tak mówi, co zastosował.

### Sprawdzenie kadru nie wymaga dodatkowego odczytu z archiwum

Narzędzie odmawia wyłącznie tego, co widać bez pytania kogokolwiek: forma, `from < to`,
granice liczby świec, kadr w całości późniejszy niż teraz. „Archiwum nie ma tam świec"
zostaje po stronie terminala, który i tak musi to sprawdzić przy dociąganiu, i mówi o tym
istniejącą drogą — listą `skipped` w `ChartControlResult`.

Rozważane: odczyt świec przez `market-mcp` w celu sprawdzenia pokrycia. Odrzucone — jeden
odczyt więcej na każde wywołanie z kadrem, żeby dowiedzieć się rzeczy, którą druga strona
i tak ustali, a ustali dokładniej.

### Dwa różne mechanizmy po stronie terminala: kadr reaktywny, widok nie

Kadr musi obudzić `Chart`, więc idzie przez `gridStore` jako pole **przejściowe**: trzymane
obok `GridConfig`, publikowane własnym `subscribe`, i **nie** zapisywane do
`localStorage`. Do `SlotConfig` nie wchodzi, bo `parseGridConfig` odrzuca całą
konfigurację, gdy nie zna kształtu, a kadr jest żądaniem, nie tym, co operator ułożył.

Widoczny zakres idzie w drugą stronę i **nie może** być reaktywny: `Chart` zna go
z `subscribeVisibleLogicalRangeChange`, które strzela przy każdej klatce przewijania.
Zapis do stanu Reacta na każdej klatce to przerysowanie panelu przy każdym ruchu myszy.
Dlatego zwykły, niereaktywny rejestr `slotId → {from, to}`, do którego `Chart` pisze,
a czyta go wyłącznie `activeChartSnapshot` w chwili wysyłania pytania. Nikt się na nim nie
subskrybuje, bo nikt nie musi.

### Dociąganie pod kadr przez istniejący pager

`useOlderBars` dostaje drugi powód do dociągania obok „widok blisko lewej krawędzi":
„najstarsza narysowana świeca jest późniejsza niż początek żądanego kadru". Ten sam limit
`MAX_PAGES` kończy sprawę, gdy archiwum nie ma tak daleko. Kadr stosuje się dopiero, gdy
warunek przestaje być spełniony — albo pager się poddał, i wtedy leci `skipped`.

Rozważane: osobny odczyt „daj mi zakres od–do" z pominięciem pagera. Odrzucone —
`useOlderBars` już pilnuje pojedynczego odczytu naraz, korekty kadru po doklejeniu świec
i porzucenia wyniku po zmianie symbolu. Drugie źródło doklejania serii to drugie miejsce,
w którym trzeba to wszystko zrobić poprawnie.

### Zachowanie kadru przy zmianie interwału

Przy zmianie `resolution` `Chart` zapamiętuje w ref-ie trzy rzeczy z **ostatniego**
widocznego zakresu: początek, koniec i to, czy prawa krawędź serii była widoczna. Po
pierwszym `redraw` nowej serii zamiast `fitContent()` ustawia:

- liczbę świec `n = (koniec − początek) / długość_nowego_interwału`, przyciętą do
  `[MIN_VISIBLE_BARS, MAX_VISIBLE_BARS]`;
- kotwicę: prawa krawędź serii, jeśli tam stał, w przeciwnym razie środek dawnego odcinka.

Przycięcie wokół środka, nie wokół krawędzi: operator patrzący na wybicie ma je na środku
ekranu i tam ma zostać.

`fitContent()` zostaje jako zachowanie pierwszego rysowania slotu, który jeszcze niczego
nie pokazywał — tam nie ma czego zachowywać.

### Prompt dostaje własną rewizję

Migracja `0006` seeduje `v6`: akapit o `set_chart` wymienia kadr i trzy sposoby jego
podania. Ten sam powód co przy `0005` — narzędzia, którego prompt nie nazywa, model nie
używa. Tekst `v5` przepisany w migracji w całości, nie łatany w locie, dokładnie jak tam.

## Risks / Trade-offs

- **Kadr złożony z log-u skacze operatorowi po odświeżeniu strony** → panel mówi zdaniem,
  co zastosował, tą samą drogą co dziś dla symbolu i wskaźników. Skok bez zdania czyta się
  jak usterka; skok ze zdaniem jest wykonaniem polecenia.
- **Dociąganie pod kadr może trwać** — do dwudziestu odczytów przy głębokim kadrze → kres
  jest ten sam, który już obowiązuje przewijanie, a wykres nie ustawia widoku, dopóki
  świec nie ma, więc operator widzi wczytywanie, a nie pusty ekran.
- **Rejestr widocznego zakresu może się rozjechać ze stanem** — pisany poza Reactem →
  czytany wyłącznie w chwili wysyłania pytania i wyłącznie dla aktywnego slotu, gdzie
  „ostatnia znana wartość" jest dokładnie tym, o co chodzi. Wpis slotu, który się
  odmontował, jest kasowany przy sprzątaniu `Chart`.
- **Zachowanie kadru przy zmianie interwału zmienia zachowanie, do którego operator
  przywykł** → to jest cel zmiany, nie jej skutek uboczny; wymaganie mówi wprost, że
  wykres przy prawej krawędzi przy niej zostaje, więc najczęstszy przypadek wygląda jak
  dotąd.
- **Model może zacząć przesuwać wykres bez proszenia** → akapit promptu wiąże kadr
  z prośbą operatora, tak samo jak wiąże `indicators`; a operator cofa to przewinięciem.

## Migration Plan

1. Migracja `0006` — kolumna `focus`, rozszerzony check, rewizja promptu `v6`. Wstecznie
   zgodna: istniejące wiersze mają `focus = NULL`, co znaczy „bez kadru".
2. `agent` wdraża się przed terminalem albo po nim, bez znaczenia. Starszy terminal
   ignoruje nieznane pole w odpowiedzi `GET /chart`; nowszy terminal, czytając polecenie
   bez kadru, po prostu nie przesuwa wykresu.
3. Wycofanie: `alembic downgrade` zdejmuje kolumnę, a prompt wraca rewizją, którą operator
   wybiera w terminalu (`agent-prompt-management`). Polecenia zapisane z kadrem tracą go —
   akceptowalne, bo kadr jest żądaniem jednorazowym, a nie stanem, do którego się wraca.
