## Context

Motywacja jest w `proposal.md` — Why. Stan, który kształtuje podejście:

- `JobRunner._worker_loop` (`market_data/jobs/runner.py`) łapie wyjątki wyłącznie wokół
  `execute_chunk`. Poza tą osłoną zostaje `pool.acquire()` z `claim_pending_chunk` oraz czekanie na
  `_wake`. Wyjątek stamtąd kończy zadanie workera na dobre; `_report_worker_death` zapisze o tym
  jedną linię w logu i to wszystko, co się wtedy dzieje.
- Kawałek zna `started_at` i `finished_at` (`jobs/models.py`, `ChunkOut`), ale żadne z tych pól nie
  jest nigdzie sumowane do „kiedy ostatnio coś się w tym zleceniu ruszyło".
- `GET /jobs` zwraca po wierszu na parę (`JobPairViewOut`), każdy z pełną listą swoich kawałków, i
  nie jest ani stronicowany, ani ograniczony. Zakładka odpytuje go co 10 sekund i trzyma w pamięci
  wszystkie wiersze wszystkich zleceń.
- Terminal ma dziś dwa dialogi napisane osobno (`AcceptanceDialog` w `AddInstrumentWizard.tsx`,
  `DeleteDialog` w `InstrumentsView.tsx`) — obydwa jako `div` z `role="dialog"` i własnym tłem,
  bez obsługi fokusu i klawiatury — oraz jedno potwierdzenie zrobione wierszem tabeli
  (`CollectionHistoryView.tsx`).
- Logowanie rozstrzyga się przed montowaniem aplikacji: `main.tsx` czeka na `initialize()`
  z `entra.ts` i dopiero potem renderuje. Poza tym miejscem nikt nie wie, że logowanie w ogóle
  istnieje — reszta terminala widzi interfejs `Identity`.

## Goals / Non-Goals

**Goals:**

- Awaria w pętli roboczej kosztuje jedno podejście i sama się zgłasza.
- „Zlecenie stoi" da się stwierdzić z zakładki bez czytania logów.
- Ponowienie jest zadawane tam, gdzie widać jego zakres — na całym zleceniu.
- Jeden dialog terminala, z którego korzystają wszystkie potwierdzenia.
- Operator ze skonfigurowaną tożsamością nie musi szukać przycisku logowania.

**Non-Goals:**

- Ponowienie zawężone do pary albo do interwału. Zakres ponowienia zostaje na zleceniu; ta zmiana
  dotyczy wyłącznie tego, gdzie i jak się o nie pyta (decyzja operatora, 2026-08-09).
- Ustalenie, dlaczego zlecenie z 9 sierpnia stanęło. Ta zmiana daje narzędzia, żeby następny raz
  było widać, nie stawia diagnozy wstecz.
- Automatyczne ponawianie zleceń przez moduł, wznawianie kawałków po timeoucie, watchdog zabijający
  zawieszone żądanie do gatewaya. Wykrywanie stania w miejscu zostaje po stronie operatora.
- Zmiany w bazie danych. Moment ostatniej aktywności jest wyliczany z kawałków, które już go znają.

## Decisions

### Moment ostatniej aktywności liczy moduł, nie terminal

`JobPairView` i `Job` dostają `last_activity_at`: największy ze znanych `finished_at` i `started_at`
swoich kawałków, a w braku obu — `created_at` zlecenia. Pole idzie do `JobPairViewOut` i `JobOut`,
więc kontrakt rośnie, ale nic z niego nie znika.

**Dlaczego nie w terminalu**, skoro ma już wszystkie kawałki w odpowiedzi: bo „aktywność" jest
definicją należącą do modułu, który kawałki wykonuje, a nie do widoku, który je rysuje. Policzona
w terminalu żyłaby w jednym konsumencie, a drugi (albo test end-to-end, albo alert) policzyłby ją
inaczej. Przy okazji przestaje być prawdą, że pełna lista kawałków musi jechać w odpowiedzi, żeby
dało się cokolwiek o postoju powiedzieć.

**Dlaczego `started_at`, a nie tylko `finished_at`**: kawałek, który ruszył i trwa, jest aktywnością
— to właśnie przypadek z 9 sierpnia. Licząc tylko rozstrzygnięcia, zlecenie z jednym długim
kawałkiem wyglądałoby na stojące od chwili poprzedniego kawałka, czyli myliłoby w drugą stronę.

### Próg bezczynności: 5 minut, wyliczany w terminalu

Wyróżnienie „to stoi" włącza się po pięciu minutach bez aktywności i jest stałą terminala, nie
konfiguracją modułu. Pięć minut jest bezpiecznie powyżej tego, co potrafi zająć jeden kawałek
(jedno żądanie do gatewaya pod wspólnym limiterem), i wyraźnie poniżej czterdziestu minut, po
których problem zauważono. Sam czas od ostatniej aktywności zakładka pokazuje zawsze, niezależnie
od progu — próg decyduje wyłącznie o wyróżnieniu.

Alternatywa — moduł oznacza zlecenie jako „stojące" — odrzucona: to sąd o tym, co jest niepokojące,
a nie fakt o zleceniu. Fakt (`last_activity_at`) należy do modułu, ocena do widoku, który i tak
odświeża się co 10 sekund i potrafi ją przeliczyć bez pytania nikogo.

### Pętla robocza: cała iteracja pod osłoną, z narastającą przerwą

Osłona przenosi się z samego `execute_chunk` na całą iterację pętli, łącznie z przejęciem kawałka i
czekaniem. `asyncio.CancelledError` MUST lecieć dalej — to jest `stop()`, jedyne prawidłowe
zakończenie. Po niepowodzeniu worker odczekuje: 5 sekund, potem podwojenie do 60 sekund jako sufitu,
z zerowaniem po pierwszym udanym przejęciu.

**Dlaczego narastająca, a nie stała przerwa**: baza nieosiągalna przez godzinę przy stałych pięciu
sekundach to 720 identycznych linii w logu i 720 prób połączenia — koszt bez informacji. Sufit
60 sekund zostawia powrót do pracy w granicach minuty od ustąpienia przyczyny, co dla zlecenia
liczonego w dziesiątkach minut jest bez znaczenia.

`_fail_orphan` zostaje bez zmian: jest odpowiedzią na „kawałek wybuchł", a nie na „nie udało się
kawałka wziąć". Gdy zawiedzie samo przejęcie, żaden kawałek nie jest przejęty i nie ma czego
rozstrzygać.

### Dialog zlecenia składa się z wierszy, które zakładka już ma

`GET /jobs` zwraca wszystkie wiersze wszystkich zleceń, więc dialog dla zlecenia `N` powstaje
z odfiltrowania wierszy o tym `jobId` — bez dodatkowego żądania i bez nowej trasy.

**Dlaczego nie `GET /jobs/{id}` przy otwarciu**: dialog stoi otwarty w trakcie pracy, którą pokazuje.
Pobrany raz byłby migawką starzejącą się na oczach operatora, a odpytywany osobno — drugim zegarem
świeżości obok tego, który zakładka już ma. Złożony z wierszy zakładki odświeża się razem z nią, co
10 sekund, i po ponowieniu pokazuje skutek bez własnego przeładowania.

Zakładka zostaje płaska i ułożona od najnowszego zdarzenia (`terminal-collection-history`,
„Historia jest ułożona od najnowszego zdarzenia"). Grupowanie wierszy po zleceniu — rozważane jako
prostsze miejsce na przycisk — złamałoby ten porządek, czyli cofnęłoby zamkniętą już zmianę
`data-history-newest-first`.

### Wspólny dialog na natywnym `<dialog>`

Nowy komponent w `src/ui/` opakowuje natywny element `<dialog>` otwierany przez `showModal()`.
Fokus przenoszony do środka, uwięziony wewnątrz, oddawany z powrotem po zamknięciu, `Escape`,
warstwa nad resztą strony i bezwładność tła — to wszystko daje platforma. Zdarzenie `cancel` jest
przechwytywane, gdy trwa potwierdzona praca, bo wtedy dialog ma zostać (spec `terminal-dialogs`,
„Dialog zostaje na ekranie, dopóki praca trwa").

Komponent bierze: tytuł, treść, nazwę akcji potwierdzającej, funkcję wykonującą pracę i sposób
zamknięcia. Praca w toku, blokada drugiego kliknięcia i błąd pokazany w środku należą do niego —
miejsce pytające dostarcza treść i skutek, nic więcej.

**Alternatywa — własny `div` z ręcznym pilnowaniem fokusu** (dzisiejszy kształt obu dialogów) —
odrzucona: ręczna pułapka na fokus to sto linii, które psują się cicho i których nikt nie ogląda,
dopóki ktoś nie wejdzie klawiaturą.

**Koszt**: `jsdom` w wersji 25 nie zna `showModal()`. Podnosimy go do `^26` (tam element `<dialog>`
jest zaimplementowany) — zmiana wyłącznie w `devDependencies`. Gdyby wsparcie okazało się
niewystarczające do przetestowania zachowań, zostają one utrzymane w komponencie, a testy sprawdzają
je przez jego własne wejścia; przeglądarka pozostaje źródłem prawdy.

Trzy istniejące miejsca przechodzą na ten komponent w jednej zmianie: kreator, kasowanie i
ponowienie. Zostawienie któregokolwiek po staremu odbiera całej zasadzie sens, bo to właśnie
rozjeżdżanie się dialogów jest problemem, który zamykamy.

### Automatyczne logowanie w `main.tsx`, z jednorazowym znacznikiem

Po `initialize()`, przed `createRoot`, terminal sprawdza `identity.state()`. Gdy jest `signed-out` —
i tylko wtedy, nigdy przy `unconfigured` — zapisuje znacznik w `sessionStorage` i wywołuje
`signIn()`. Strona odchodzi do Entry, wraca, `initialize()` rozstrzyga powrót. Znacznik zastany po
powrocie bez zalogowania znaczy „już próbowaliśmy" i blokuje drugie przekierowanie; zalogowanie go
kasuje.

**Dlaczego przed montowaniem, a nie w efekcie w powłoce**: zamontowana aplikacja natychmiast pyta
o świece, dostaje odmowę i pokazuje ekran błędu, po czym znika w przekierowaniu. Operator widzi
mignięcie awarii, której nie było.

**Dlaczego `sessionStorage`, a nie zmienna w module**: przekierowanie to pełne przeładowanie strony,
po którym pamięć modułu jest pusta. `sessionStorage` przeżywa przeładowanie i umiera z kartą — ten
sam wybór, co dla sesji MSAL, z tego samego powodu.

Wskaźnik „signed out" z przyciskiem w `TopBar` zostaje nietknięty. Jest teraz drogą wyjścia po
nieudanym automacie, a nie główną drogą wejścia.

## Risks / Trade-offs

**Automatyczne przekierowanie zabiera terminal operatorowi, który nie chciał się logować** → tylko
raz na wejście, blokowane znacznikiem, a `unconfigured` nie dotyka tego w ogóle. Powrót bez
zalogowania kończy się terminalem w stanie „signed out" i przyciskiem — czyli dokładnie tym, co jest
dziś.

**Pętla przekierowań, gdyby znacznik nie zadziałał** → najgorszy możliwy skutek tej zmiany, bo
strony w pętli nie da się przeczytać. Ryzyko ograniczone tym, że znacznik jest zapisywany *przed*
odejściem ze strony, więc jego brak po powrocie oznaczałby wyłączony `sessionStorage`, w którym
i tak nie działa MSAL. Test w scenariuszu „powrót bez zalogowania" pilnuje tego wprost.

**Podniesienie `jsdom` psuje testy niezwiązane ze zmianą** → jsdom jest tylko `devDependency`;
weryfikacja to jedno uruchomienie całego zestawu testów terminala zaraz po podniesieniu, przed
napisaniem czegokolwiek nowego.

**Klikalny wiersz tabeli myli się z zaznaczaniem tekstu** → wiersz dostaje jawną rolę przycisku
w kolumnie akcji i obsługę klawiatury; otwarcie dialogu przez kliknięcie gdziekolwiek w wierszu jest
wygodą, nie jedyną drogą.

**`last_activity_at` liczone z kawałków przy każdym odczycie** → to maksimum z listy, którą odczyt
i tak już zmaterializował w pamięci; żadnego dodatkowego zapytania ani indeksu.

**Próg pięciu minut wyróżni zlecenie, które po prostu czeka na wolny slot limitera** → wyróżnienie
mówi „nic się tu nie dzieje", co jest wtedy prawdą; nie mówi „awaria". Wartość jest jedną stałą
w jednym pliku, więc zmiana kosztuje jedną linię, gdyby okazała się za ciasna.
