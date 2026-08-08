## 1. Szkielet modułu

- [x] 1.1 Utwórz `modules/market-data/` z `pyproject.toml`, `README.md` i `.env.example` wzorowanymi na `capital-gateway`
- [x] 1.2 Dodaj zależności: `fastapi`, `uvicorn`, `httpx`, `websockets`, `pydantic-settings`, `asyncpg`, `alembic`
- [x] 1.3 Napisz `config.py` — adres gatewaya, połączenie do bazy, limit śledzonych par, równoległość uzupełnień, domyślna głębokość historii
- [x] 1.4 Dodaj `pytest` z `docker`-owym Postgresem dla testów integracyjnych i sprawdź, że pusta suita przechodzi

## 2. Schemat bazy

- [x] 2.1 Migracja: tabela świec z kluczem (symbol, rozdzielczość, początek okresu) i jawną kolumną strony ceny
- [x] 2.2 Migracja: tabela śledzonych par z trwałym stanem i znacznikiem dodania
- [x] 2.3 Migracja: tabela zakresów pokrycia wraz z flagą „historia providera się skończyła"
- [x] 2.4 Test: powtórny zapis tej samej trójki nadpisuje wpis i nie tworzy duplikatu
- [x] 2.5 Test: zapis świecy w budowie jest odrzucany na poziomie warstwy dostępu do danych

## 3. Odczyt z gatewaya

- [x] 3.1 Klient HTTP do `/instruments/{symbol}/history` z mapowaniem `CandleHistory` na model wewnętrzny
- [x] 3.2 Klient WebSocket do `/ws/stream` z rozpoznaniem wiadomości świecy, kwotowania, statusu i błędu
- [x] 3.3 Sprowadzenie znaczników czasu do jednej postaci — ISO z historii i epoka ze strumienia na wspólny początek okresu
- [x] 3.4 Test: świeca z historii i świeca ze strumienia dla tego samego okresu mają identyczny znacznik czasu

## 4. Archiwum

- [x] 4.1 Zapis świecy zamkniętej z nadpisaniem wpisu o tej samej trójce
- [x] 4.2 Reguła autorytatywności: wartość z odczytu historii wygrywa z wartością ze strumienia
- [x] 4.3 Odczyt zakresu świec uporządkowany od najstarszej, bez powtórzeń
- [x] 4.4 Zapis i odczyt zakresów pokrycia, w tym granica wynikająca z `history_ended`
- [x] 4.5 Rozstrzyganie „rynek zamknięty" kontra „brak danych" na podstawie pokrycia
- [x] 4.6 Test: brak świecy wewnątrz pokrycia jest raportowany inaczej niż brak poza pokryciem

## 5. Rozdzielczości pochodne

- [x] 5.1 **Zweryfikuj empirycznie**, czy provider kotwiczy `HOUR_4` na północy UTC — wylicz próbkę z serii minutowej i porównaj ze świecami pobranymi z gatewaya
- [x] 5.2 Rollupy dla `MINUTE_5`, `MINUTE_15`, `MINUTE_30`, `HOUR`, `HOUR_4` (tabela, nie widok materializowany — patrz `design.md`)
- [x] 5.3 Przyrostowe odświeżanie po zamknięciu okresu
- [x] 5.4 Oznaczanie świecy powstałej z niepełnego okresu
- [x] 5.5 Test: wyliczona świeca ma otwarcie pierwszej, maksimum i minimum wszystkich, zamknięcie ostatniej

## 6. Śledzone pary

- [x] 6.1 Dodanie pary z walidacją symbolu przez gateway i sprawdzeniem limitu
- [x] 6.2 Usunięcie pary zatrzymujące zbieranie i zachowujące dane
- [x] 6.3 Odczyt listy wraz ze stanem połączenia i czasem najnowszej świecy
- [x] 6.4 Wykrywanie „zbieranie ustało" — najnowsza świeca starsza niż dwa okresy przy otwartym rynku
- [x] 6.5 Test: konfiguracja przeżywa restart modułu
- [x] 6.6 Test: dodanie ponad limit kończy się odmową z podaniem powodu

## 7. Ingest

- [x] 7.1 Nasłuch na żywo z subskrypcją na śledzoną parę i zapisem świec zamkniętych
- [x] 7.2 Wznawianie subskrypcji z rosnącym odstępem, dopóki para jest śledzona
- [x] 7.3 Uzupełnianie wstecz przez `/history`, bez własnego stronicowania
- [x] 7.4 Domknięcie luki przy starcie modułu dla każdej śledzonej pary
- [x] 7.5 Domknięcie luki po wznowieniu zerwanej subskrypcji
- [x] 7.6 Ograniczenie równoległości uzupełnień, żeby nie zagłodzić ruchu interaktywnego
- [x] 7.7 Raportowanie postępu i przyczyn niepowodzeń, czytelne dla operatora
- [x] 7.8 Test: start po przerwie dociąga brakujący przedział; start bez przerwy nie wysyła żądań

## 8. Kontrakt modułu

- [x] 8.1 `GET` świec po zakresie czasu z rozdzielczością i stroną ceny w odpowiedzi
- [x] 8.2 Oznaczanie części żądanego przedziału, która nie jest pokryta
- [x] 8.3 Subskrypcja WebSocket ze snapshotem jako pierwszą wiadomością, czytanym w jednej transakcji z dopięciem odbiorcy
- [x] 8.4 Rozgłaszanie zmian po snapshocie, z jawnym oznaczeniem świecy zamkniętej i w budowie
- [x] 8.5 `GET` pokrycia pary
- [x] 8.6 Zarządzanie śledzonymi parami przez kontrakt
- [x] 8.7 Błędy nazywające przyczynę, bez surowych błędów bazy i bez poświadczeń
- [x] 8.8 OpenAPI dla tras HTTP i opis wiadomości WebSocket w `README.md`, z testem pilnującym, że ścieżka WS jest nieobecna w schemacie
- [x] 8.9 Test: subskrypcja nieśledzonej pary jest odrzucana
- [x] 8.10 Test: snapshot i kolejne zmiany nie tworzą duplikatu świecy tego samego okresu

## 9. Terminal — źródło składane

- [x] 9.1 Implementacja `MarketDataSource` czytająca świece i strumień z archiwum
- [x] 9.2 Złożenie w `marketData.ts`: świece z archiwum, instrumenty z gatewaya, jedna instancja na aplikację
- [x] 9.3 Obsługa snapshotu w `useBarFeed` — zastąpienie dotychczasowego zszywania historii ze strumieniem
- [x] 9.4 Usunięcie dociągania luki po stronie terminala, skoro przynosi ją snapshot
- [x] 9.5 Rozróżnienie stanów: archiwum nieosiągalne kontra gateway nieosiągalny
- [x] 9.6 Test: wykres, siatka i wyszukiwarka działają bez zmian w swoim kodzie
- [x] 9.7 Test: gdy archiwum nie odpowiada, wyszukiwarka instrumentów działa dalej

## 10. Terminal — panel konfiguracji

- [x] 10.1 Nowa zakładka w rejestrze, z własną ścieżką
- [x] 10.2 Lista archiwizowanych par ze stanem zbierania i czasem najnowszej świecy
- [x] 10.3 Dodawanie pary: wybór instrumentu z wyszukiwarki plus rozdzielczość
- [x] 10.4 Pokazanie powodu, gdy archiwum odmawia dodania
- [x] 10.5 Wyróżnienie pary, dla której zbieranie ustało
- [x] 10.6 Podgląd pokrycia wybranej pary
- [x] 10.7 Zdejmowanie pary z potwierdzeniem i informacją, że dane zostają
- [x] 10.8 Odróżnienie pustej listy od nieosiągalnego archiwum
- [x] 10.9 Test: dodanie i zdjęcie pary odzwierciedla się na liście
- [x] 10.10 Środowisko lokalne: `compose.yaml` z bazą w kontenerze, usługi na hoście, `scripts/dev.sh` dla macOS i Linuksa obok istniejącego `dev.ps1`

## 11. Domknięcie

- [x] 11.1 `README.md` modułu: co, jak uruchomić, jak testować, kontrakt — na jeden ekran.
      Ścięty z 373 do 195 linii, w układzie `capital-gateway` i `terminal`: what / run / test /
      contract, a na końcu jedna sekcja z regułami i tym, co zostało zmierzone. Rozumowanie,
      które powtarzało `design.md` (wybór bazy, odrzucenie widoku materializowanego), wypadło —
      README opisuje kontrakt, nie decyzje.
- [x] 11.2 `docs/architecture.md` i `README.md` repozytorium: moduł w tabeli i na rysunku.
      Rysunek dostał `market-data` między gatewayem a terminalem, z osobnym kanałem instrumentów
      omijającym archiwum — bo to jedyna rzecz, po którą terminal nadal chodzi do gatewaya.
      Sekcja „Ownership of data" nazywa archiwum po imieniu i odnotowuje `migrations/` jako to,
      co dochodzi do anatomii modułu ze stanem trwałym.
- [x] 11.3 Uruchom pełną suitę obu modułów i terminala, zanotuj polecenie i wynik. Wszystko
      czysto, na `docs/market-data-closeout`:

      | Gdzie | Komenda | Wynik |
      |---|---|---|
      | capital-gateway | `uv run pytest -q` | 121 passed, 8 skipped, 2,1 s |
      | capital-gateway | `uv run ruff check . && uv run ruff format --check .` | czysto, 30 plików |
      | market-data | `uv run pytest -q` | 278 passed, 7 skipped, 12,5 s |
      | market-data | `uv run pytest -m db -q` | 171 passed, 7 skipped, 107 deselected, 14,6 s |
      | market-data | `uv run ruff check .` | czysto |
      | terminal | `pnpm test` (`vitest run`) | **142 passed**, 13 plików, 5,8 s |
      | terminal | `pnpm typecheck` / `pnpm lint` | czysto, bez wyjścia |
      | terminal | `pnpm build` | `dist/` 421,46 kB (gzip 134,46 kB), 1,15 s |

      Liczby terminala są **po** poprawkach z 11.4: 131 testów przed nimi, 142 po. Dziesięć
      dołożonych pilnuje rzeczy, które ta suita przepuściła — kolizji prefiksu ze ścieżką
      zakładki, rozstrzygania odmowy od zerwania i warstwy, na której rysuje się komunikat.

      Pominięcia są zamierzone: 8 w gatewayu i 7 w archiwum to testy za `--run-live`, a 107
      odrzuconych w `market-data` to zbiór `db` niewybrany przez domyślne uruchomienie. Testy
      `-m db` wymagały działającego Dockera i przeszły przeciw kontenerowi jednorazowemu.

      Uwaga do zanotowania, bo kosztowała czas: **`pnpm` nie stoi na PATH na tej maszynie** —
      shim corepacka wywraca się na Node 25 (`ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING`), a sam
      `pnpm` z cache'a corepacka wymaga siebie na PATH, żeby uruchomić `pnpm install` w kontroli
      zależności. Suita terminala szła przez shim wskazujący na `pnpm.cjs`. To środowisko, nie
      repozytorium: `scripts/dev.sh` już schodzi na `npm`, gdy `pnpm` go nie ma.
- [x] 11.4 Przejdź ręcznie ścieżkę: dodaj parę w panelu, poczekaj na świece, otwórz wykres,
      zrestartuj moduł, sprawdź domknięcie luki. **Przejście pełne**, w dwóch podejściach:
      rano przez sterowany Chrome (playwright-core), po południu na parze krypto, bo dopiero
      wtedy wiadomo było, że `BTCUSD` handluje się w weekend, a stojące rano notowanie było
      awarią providera, nie kalendarzem.

      - **Dodanie pary w panelu.** `BTCUSD` `MINUTE` wybrany z wyszukiwarki, `POST /pairs` → 201,
        a w logu gatewaya walidacja symbolu, uzupełnienie i przyjęta subskrypcja w kilka sekund —
        ingest podejmuje parę **bez restartu**.
      - **Świece na żywo.** Od 15:32 do 15:49 UTC seria rosła co minutę, potwierdzone przez
        `/pairs` i w bazie. To ta część, której rano nie dało się przejść.
      - **Wykres** narysował ~8 godzin świec z archiwum, z odczytem
        `O 64938.5 H 64943.85 L 64938.5 C 64942.25 V 147`.
      - **Restart domyka lukę realnymi danymi.** Start o 15:31:59 dociągnął i **zapisał**:
        `BTCUSD MINUTE: asked for 3 candles, wrote 3`, `US100 HOUR: asked for 20, wrote 20`.
        Rano sprawdzona była tylko gałąź „zapisano 0"; teraz obie. Pokrycie scala się w jeden
        wiersz, a `BACKFILL_CONCURRENCY=1` trzyma odczyty po kolei na jednym połączeniu.
      - **Stan zbierania po raz pierwszy mówi prawdę.** `US100 HOUR` → `market_closed`
        (sobota), `BTCUSD MINUTE` → `collecting`, a w chwili realnego zerwania strumienia →
        `stalled`. Przed poprawkami z 11.4d wszystko było `unknown`.

      Wyszły przy tym trzy kolejne błędy, wszystkie widoczne **wyłącznie na żywo** — opisane
      w 11.4d–f.

- [x] 11.4a **Naprawiony:** panel archiwum był nieosiągalny pod własnym adresem. Proxy dev
      trzymało prefiks `/archive`, a to jest ścieżka zakładki Archive — więc przeładowanie
      zakładki, zakładka w przeglądarce i link, który wypisuje `scripts/dev.sh`, oddawały
      `{"service":"market-data"}` zamiast aplikacji. Kliknięcie działało, bo router nigdy nie pyta
      serwera, i **dlatego nie złapał tego żaden test**. To nie jest usterka serwera dev: cokolwiek
      stanie przed dwoma backendami na produkcji, przesłoni zakładkę tak samo. Prefiks archiwum to
      teraz `/archive-api` (`vite.config.ts`, `config.ts`, `.env.example`, README terminala), a
      `config.test.ts` porównuje listę prefiksów backendów z listą ścieżek zakładek, żeby następny
      prefiks nie mógł tego powtórzić. Poprawione też `dev.sh`, który wypisywał link do panelu
      nawet przy `--no-terminal`.

- [x] 11.4b **Naprawiony:** wykres niearchiwizowanej pary mówił „RECONNECTING" w kółko.
      Archiwum odmawia subskrypcji pary, której nikt nie zbiera — i ma rację, tak stanowi
      `market-data-api`. Ale odmawia **przed handshake'em**, gołym `403`, a przeglądarkowe
      `WebSocket` nie udostępnia statusu odrzuconego handshake'u: strona widzi tylko „nie
      połączyło się", czyli to samo, co przy archiwum wyłączonym. Na siatce `2x2` trzy z czterech
      slotów były czarnym polem z plakietką `RECONNECTING` ponawianą bez końca (20 prób w 12 s),
      podczas gdy prawdziwa odpowiedź brzmiała „tej pary nikt nie archiwizuje".

      Wybrane rozwiązanie **(a)** — kontrakt archiwum bez zmian, decyzja „odmawiamy przed
      handshake'em" zostaje. `SocketHub` dostał opcjonalne pytanie zadawane po nieudanym
      połączeniu, a `archive.ts` odpowiada na nie czytając `GET /pairs`: pary nie ma na liście →
      „`BTCUSD HOUR` is not being archived — add it in the Archive tab", stan `closed`, koniec
      ponawiania. Para jest na liście albo `/pairs` też nie odpowiada → ponawianie trwa, bo to
      jest właśnie przypadek zerwania. Pytanie zadawane **raz na serię niepowodzeń** i ponownie
      dopiero po połączeniu, które zadziałało, oraz z własnym terminem (5 s), żeby wiszące
      `/pairs` nie zamknęło pętli ponawiania na zawsze. Scenariusze dopisane do delty
      `terminal-market-data`. W przeglądarce: 4 próby zamiast 20, a każdy slot podaje powód
      i przycisk Retry.

- [x] 11.4c **Naprawiony przy okazji, i groźniejszy:** komunikaty wykresu były niewidoczne.
      `Veil` — to, co wykres pokazuje, gdy nie ma czego narysować: „Loading…", „No candles for…",
      każdy błąd — jest `absolute inset-0` bez `z-index`, a lightweight-charts montuje swoje
      canvasy z `z-index` 1 i 2 w kontenerze, który sam nie otwiera kontekstu stosu. Canvasy
      wygrywały. Komunikat renderował się do DOM, **przechodził swój test** i był zamalowywany
      pustym płótnem. Nie dało się tego złapać w jsdom, bo jsdom nie liczy kolejności malowania,
      i nie dało się tego zobaczyć inaczej niż patrząc na cztery czarne panele, których tekst
      był tam przez cały czas. `z-10` na `Veil`; test pilnuje samej własności, która o tym
      decyduje, z komentarzem, dlaczego nie może pilnować niczego więcej.
- [x] 11.4d **Naprawiony:** próg „zbieranie ustało" był za ciasny i wskaźnik migał. Dwa okresy
      liczone od początku świecy nie zostawiają miejsca na to, ile świeca leci od providera przez
      gateway do archiwum. Zmierzone na żywym strumieniu: zamknięta świeca minutowa pojawiała się
      **52–169 s po zamknięciu okresu**, czyli zdrowa para siedziała 112–229 s wstecz przy progu
      120 s, a stan skakał między `collecting` a `stalled` z odczytu na odczyt. Wskaźnik, który
      kłamie co drugi raz, jest gorszy niż żaden — operator uczy się go ignorować. Dodane
      `DELIVERY_GRACE` = 3 minuty, stałe, nie kolejny okres: dostarczenie trwa tyle samo przy
      `MINUTE` i przy `HOUR_4`, a trzeci okres to tam cztery godziny niewykrytej awarii.
      Po poprawce stan trzymał `collecting` bez przerwy przez cały czas obserwacji.

- [x] 11.4e **Naprawiony, i najpoważniejszy z całej trójki:** zerwanie połączenia *gatewaya
      z providerem* zostawiało w archiwum trwałą dziurę. Gateway zgłasza to jako wiadomość
      błędu, ale **nie zamyka gniazda do nas** — więc pętla nasłuchu nigdy się nie kończy,
      domknięcie luki z góry `run()` nigdy nie przychodzi, a minuty, których nikt nie słuchał,
      zostają. Zaobserwowane: `keepalive ping timeout` o 15:44 kosztował świece `15:42` i `15:44`,
      **które provider nadal miał**, i które zostałyby tam do restartu modułu. Pokrycie zachowało
      się wzorowo — zgłosiło `uncovered` 15:42→15:45 zamiast udawać zamknięty rynek — ale nikt po
      te dane nie wracał. Teraz wiadomość o kłopocie gatewaya domyka lukę, nie zrywając
      subskrypcji; powtórka nic nie kosztuje, bo przy braku dziury fill prosi o zero świec.

- [x] 11.4f **Naprawiony koszt wprowadzony przez 11.4d/Finding 5:** zamknięty rynek jest
      *trwale* spóźniony, więc pytanie o jego stan szło do gatewaya przy **każdym** odczycie
      listy — 74 zapytania o `US100` w kwadrans weekendu. Odpowiedź jest teraz pamiętana przez
      minutę: sesja zmienia się dwa razy na dobę, więc minuta nieświeżości nie kosztuje nic,
      a 20 odczytów `/pairs` w 60 s zeszło z 20 zapytań do **1**.

- [x] 11.5 Napisz `review.md` — dwa przejścia wymagane przez schemat, przed archiwizacją zmiany.
      Przejście po diffie (17 commitów od `5ed0345`) dało osiem ustaleń: sześć naprawionych, dwa
      otwarte. Najpoważniejsze naprawione w tym przeglądzie — odczyt zakresu czytał tabelę rollupów
      dla **każdej** rozdzielczości pochodnej, więc para śledzona na `HOUR` trzymała 5000 świec
      i dostawała w odpowiedzi zero, przy pustym `uncovered`, czyli „rynek był zamknięty przez cały
      dzień". Dwa otwarte (`market_open` bez producenta, postęp ingestu tylko w logu) zmieniają
      kształt kontraktu i są opisane z rekomendacją zamiast dopisane. Przejście po pokryciu
      przeszło wszystkie 62 scenariusze z sześciu delt; sześć luk, wszystkie zaakceptowane
      i wyliczone.
