## 1. Szkielet modułu

- [x] 1.1 Założyć `modules/terminal/` z `package.json`, `tsconfig.json`, `vite.config.ts`,
      `index.html` i `.gitignore`; React + TypeScript, pnpm, wersja biblioteki wykresu przypięta
      dokładnie
- [x] 1.2 Wpiąć Tailwind v4 przez plugin Vite i zdefiniować w `@theme` tokeny: tła, powierzchnie,
      obramowania, tekst, akcent, kolor wzrostu i spadku; ciemny motyw jako domyślny
- [x] 1.3 Skonfigurować w `vite.config.ts` proxy `/api` i `/ws` na `http://localhost:8010`,
      z podnoszeniem WebSocketa; `.env.example` z `VITE_GATEWAY_HTTP=/api` i `VITE_GATEWAY_WS=/ws`
      oraz komentarzem, że oba przyjmują też pełny URL
- [x] 1.4 Ustawić `vitest` z `@testing-library/react` i `msw`; skrypty `dev`, `build`, `test`,
      `lint`, `typecheck` w `package.json`
- [x] 1.5 Potwierdzić, że `pnpm install && pnpm dev` podnosi pustą stronę w świeżo skopiowanym
      katalogu, bez niczego z reszty repozytorium
- [x] 1.6 Napisać `scripts/dev.ps1` w korzeniu repozytorium: podnosi `capital-gateway` na porcie
      8010 i terminal jednym poleceniem, oznacza logi obu źródeł prefiksem i ubija oba przy
      przerwaniu, nie zostawiając osieroconego procesu na porcie
- [x] 1.7 Skrypt sprawdza warunki przed startem — `uv` i `pnpm` na ścieżce, istnienie
      `modules/capital-gateway/.env` — i mówi wprost, czego brakuje, zamiast paść w połowie
- [x] 1.8 Skrypt czeka, aż gateway odpowie na `/capabilities`, zanim uzna start za udany, i wypisze
      oba adresy: terminal i Swagger gatewaya
- [x] 1.9 Zostawić skrypt wyłącznie wygodą: oba moduły dają się uruchomić osobno własnymi
      poleceniami i żaden nie zależy od jego istnienia; zapisać to w `README.md` repozytorium

## 2. Warstwa danych — kontrakt i normalizacja

- [x] 2.1 Opisać typy terminala: `Bar`, `Instrument`, `InstrumentPage`, `Resolution`,
      `StreamEvent`; `Resolution` obejmuje `MINUTE`, `MINUTE_5`, `MINUTE_15`, `MINUTE_30`,
      `HOUR`, `HOUR_4`, `DAY`, `WEEK`
- [x] 2.2 Zadeklarować interfejs `MarketDataSource` w kształcie z `design.md`
- [x] 2.3 Napisać normalizację czasu: ISO z REST-u na sekundy od epoki, jawnie, bez polegania na
      strefie lokalnej; test na utrwalonej odpowiedzi z działającego gatewaya sprawdzający
      konkretną godzinę
- [x] 2.4 Napisać scalanie świec po znaczniku czasu — świeca z okresu znanego podmienia, z nowego
      dopisuje, seria nigdy nie ma dwóch świec o tym samym znaczniku; testy jednostkowe
- [x] 2.5 Rozstrzygnąć, czy `ts` z gatewaya niesie strefę, i zapisać wynik w `README.md` modułu —
      to pierwsza rzecz do potwierdzenia przy realnym gatewayu

## 3. Warstwa danych — implementacje

- [x] 3.1 Zaimplementować adapter gatewaya: `searchInstruments`, `listInstruments` (z flagą
      `truncated`), `history` przez `GET /instruments/{symbol}/history`
- [x] 3.2 Odwzorować błędy gatewaya na błędy nazywające przyczynę — nieznany symbol,
      nieobsługiwana rozdzielczość, źródło nieosiągalne; żaden komunikat nie niesie poświadczeń
- [x] 3.3 Zaimplementować hub gniazd z liczeniem referencji po kluczu `symbol|resolution`:
      pierwszy odbiorca otwiera, kolejni dzielą, ostatni zamyka; testy na współdzieleniu i
      zamknięciu
- [x] 3.4 Dodać wznawianie z rosnącym odstępem i rozrzutem, sufit 30 s, oraz publikowanie stanu
      połączenia; test harmonogramu na sterowanym zegarze
- [x] 3.5 Dociągać lukę po wznowieniu: po powrocie połączenia odczytać ostatnie świece i scalić je
      z serią
- [x] 3.6 ~~Zaimplementować źródło mock~~ — **wycofane**. Zostało zbudowane (deterministyczne
      ziarno, świece historyczne, tykanie na żywo, test powtarzalności) i usunięte na życzenie:
      terminal ma pokazywać rynek, a rynek jest w gatewayu. Testy nigdy z niego nie korzystały —
      każdy ma własną atrapę sterowaną z testu — więc usunięcie nic nie odsłoniło.
- [x] 3.7 Budować adresy z `VITE_GATEWAY_HTTP` i `VITE_GATEWAY_WS` niezależnie, przyjmując ścieżkę
      względną i pełny URL; ścieżka względna dla strumienia rozwija się na `ws`/`wss` zgodnie ze
      schematem strony. Test na obu kształtach — inaczej rozjazd wyjdzie dopiero przy wdrożeniu
- [x] 3.8 ~~Wystawić wybór źródła jako stan aplikacji~~ — **wycofane** razem z 3.6. Przy jednej
      implementacji przełącznik nie ma czego przełączać; źródło jest pojedynczą instancją modułu
      (`marketData.ts`), po którą sięgają widoki. Interfejs `MarketDataSource` zostaje — to szew
      pod bazę świec, nie pod wybór w UI.

## 4. Powłoka terminala

- [x] 4.1 Wprowadzić rejestr zakładek — nazwa, ścieżka, widok — i wyprowadzić z niego routing
      oraz pasek nawigacji; wpisy `Positions`, `Orders`, `Account` oznaczone jako przygotowane
      na przyszłość
- [x] 4.2 Zbudować layout: pasek górny z nazwą i wskaźnikiem połączenia, pasek zakładek, obszar
      treści na pełną wysokość. Przełącznik źródła zniknął razem z 3.8.
- [x] 4.3 Dodać stronę nieznanego adresu z drogą powrotną oraz widok „ta zakładka jeszcze nie
      działa" dla wpisów przygotowanych na przyszłość
- [x] 4.4 Dodać granicę błędu obejmującą pojedynczy widok, z komunikatem i ponowieniem, tak żeby
      awaria jednego nie gasiła reszty terminala
- [x] 4.5 Podpiąć wskaźnik stanu źródła do huba i do odczytów HTTP — cisza na strumieniu ma
      wyglądać inaczej niż stojący rynek. Zaimplementowane jako niezależny od aktywnych
      subskrypcji `ping()` na źródle (MarketDataSource), odpytywany cyklicznie — działa nawet
      gdy żaden wykres nie jest zamontowany. Odróżnienie „cisza na strumieniu" od „rynek stoi"
      jest per-wykres i należy do zadania 5.7, nie do globalnego wskaźnika.
- [x] 4.6 Testy powłoki: przejście między zakładkami zmienia adres, wejście z adresu wprost
      pokazuje zakładkę, nieznany adres daje stronę zastępczą

## 5. Wykres

- [x] 5.1 Zbudować komponent wykresu sterowany wyłącznie symbolem i rozdzielczością; tworzenie w
      `useLayoutEffect`, kolory czytane z tokenów motywu
- [x] 5.2 Zaciągnąć historię i podać ją jednym `setData`, a świece na żywo puszczać przez
      `update`, bez trzymania serii w stanie Reacta. Historia jest scalana z tym, co już przyszło
      ze strumienia, a nie podmienia to — subskrypcja startuje przed odczytem, więc świeca w
      budowie normalnie przychodzi pierwsza i inaczej znikałaby do następnego ticku.
- [x] 5.3 Sprzątać po sobie: zakończenie subskrypcji i usunięcie wykresu przy odmontowaniu,
      odporne na podwójne wywołanie efektu w `StrictMode`
- [x] 5.4 Dopasowywać rozmiar przez `ResizeObserver` na kontenerze, bez wymiarów w propsach
- [x] 5.5 Dodać wybór rozdzielczości w nagłówku wykresu, z odrzucaniem spóźnionych odpowiedzi;
      test na szybkim przełączaniu. Zamiast licznika generacji wystarczyła flaga zamknięta w
      pojedynczym przebiegu efektu — daje tę samą gwarancję, a nie czyta `ref.current` w cleanupie.
- [x] 5.6 Oznaczyć świecę w budowie na ekranie i zdejmować oznaczenie, gdy zastąpi ją świeca
      zamknięta
- [x] 5.7 Rozróżnić stany: ładowanie, pusta seria, błąd odczytu z ponowieniem, strumień zerwany
- [x] 5.8 Pokazywać wartości spod kursora — otwarcie, maksimum, minimum, zamknięcie, czas —
      dławione do jednej klatki; brak wolumenu pokazywany jako brak danej, nie jako zero
- [x] 5.9 Testy komponentu z zaślepioną biblioteką wykresu: stany, przepięcie subskrypcji przy
      zmianie symbolu, sprzątanie przy odmontowaniu

## 6. Siatka wykresów

- [x] 6.1 Opisać model konfiguracji: sześć slotów o stałych identyfikatorach, każdy z symbolem i
      rozdzielczością, oraz wybrany układ
- [x] 6.2 Zbudować siatkę na CSS Grid z presetami `1x1`, `2x1`, `2x2`, `3x2`; układ decyduje
      wyłącznie o liczbie widocznych slotów, konfiguracja ukrytych zostaje zapamiętana
- [x] 6.3 Dodać nagłówek slotu z symbolem, rozdzielczością i zmianą jednego i drugiego bez
      opuszczania siatki; slot bez instrumentu zaprasza do wyboru. Doszedł przycisk czyszczenia
      slotu — bez niego stan pusty był osiągalny wyłącznie przy pierwszym uruchomieniu.
- [x] 6.4 Oznaczać slot aktywny, żeby akcje kierowane do slotu miały jawny cel. Aktywacja także
      przy wejściu fokusem, nie tylko kliknięciem, żeby sterowanie klawiaturą dawało ten sam sygnał.
- [x] 6.5 Zapisywać konfigurację w `localStorage` pod kluczem z wersją, ze strażnikiem typu przy
      odczycie i powrotem do domyślnego układu przy danych nieczytelnych; testy na uszkodzonym
      zapisie
- [x] 6.6 Obsłużyć slot wskazujący symbol nieznany bieżącemu źródłu: komunikat w tym slocie,
      reszta siatki działa dalej. Realizowane przez nakładkę błędu wykresu (`not-found` z adaptera
      nazywa symbol), która jest per-slot z konstrukcji; wybór innego instrumentu jest zawsze pod
      ręką w nagłówku slotu.
- [x] 6.7 Test sprawdzający, że dwa sloty na tę samą parę dzielą jedno połączenie, a zejście na
      mniejszy układ kończy subskrypcje slotów, które zniknęły

## 7. Zakładka Instruments

- [x] 7.1 Zbudować wyszukiwarkę z dławieniem 250 ms, przerywaniem poprzedniego żądania i
      odrzucaniem spóźnionych odpowiedzi (ta sama flaga na przebieg efektu co w wykresie, nie
      licznik generacji); lista pokazuje symbol, nazwę, klasę aktywów, flagę handlowalności
      oraz bid i ask tam, gdzie są
- [x] 7.2 Rozróżnić brak wyników od błędu wyszukiwania; błąd niesie ponowienie. Wyszukiwanie
      ponawia się samo po poprawieniu frazy, więc jawny przycisk został przy odczycie katalogu,
      gdzie nie ma czego zmienić.
- [x] 7.3 Dodać wyliczenie katalogu z widocznym ostrzeżeniem, gdy źródło zgłasza ucięcie
- [x] 7.4 Wstawiać wybrany instrument do aktywnego slotu i przechodzić na zakładkę wykresów z
      narysowaną serią; instrument niehandlowalny pokazuje się z widoczną adnotacją
- [x] 7.5 Testy: dławienie nie wysyła zapytania po każdym znaku, spóźniona odpowiedź nie nadpisuje
      wyniku ostatniej frazy, wybór instrumentu trafia do właściwego slotu

## 8. Domknięcie

- [x] 8.1 Napisać `modules/terminal/README.md` w układzie what / run / test / contract, z
      wymaganiem uruchomionego gatewaya — terminal nie ma trybu offline
- [x] 8.2 Uruchomić przeciw działającemu `capital-gateway` na demo: potwierdzić, że świeca
      w budowie faktycznie rusza wykresem na `MINUTE_5`, i zapisać, co się zobaczyło. Ruszyła —
      OHLC ostatniej świecy US100 zmieniło się w ciągu 45 s bez świecy zamkniętej po drodze.
      Potwierdzone też `ts` z `Z` na żywej odpowiedzi (zadanie 2.5). Przy okazji wyszedł błąd:
      przełączenie źródła zostawiało świece poprzedniego na ekranie pod nową etykietą — naprawione
      i przykryte testem.
- [x] 8.3 Zmierzyć siatkę `3x2` na sześciu różnych parach: liczba gniazd, zachowanie przy zmianie
      układu, koszt przerysowań; zapisać wynik zamiast go zakładać. Zmierzone w przeglądarce:
      **sześć gniazd jednocześnie, szczyt sześć**, po jednym na parę. Dwa dodatkowe otwarcia w logu
      zamykają się w tej samej dziesiątej sekundy — `StrictMode` w developmencie podwaja efekty,
      więc świeżo zamontowany wykres subskrybuje, odsubskrybowuje i subskrybuje ponownie; nigdy
      nie są równoczesne, a build produkcyjny nie podwaja. Zejście na `2x2` zamyka gniazda
      zniknionych slotów. Kosztu przerysowań nie mierzono osobno — seria nie przechodzi przez stan
      Reacta z konstrukcji, więc nie ma czego liczyć na tick.
- [x] 8.4 Dopisać terminal do tabeli modułów w `README.md` i podmienić „terminal (later)" na
      rysunku w `docs/architecture.md`
- [x] 8.5 Przepuścić całość przez `pnpm typecheck`, `pnpm lint` i `pnpm test` — plus `pnpm build`,
      bo dopiero on przechodzi przez `tsc -b` na produkcyjnej ścieżce. 118 testów, wszystko czyste.
