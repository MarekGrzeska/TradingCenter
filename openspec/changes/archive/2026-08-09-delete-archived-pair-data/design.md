## Context

Powód zmiany: proposal.md, „Why". Tu tylko to, co kształtuje rozwiązanie.

Dane pary leżą dziś w czterech miejscach i żadne z nich nie jest oczywiste:

- `candles` — świece zebrane dla pary (symbol, rozdzielczość);
- `derived_candles` — rozdzielczości wyliczone z serii minutowej tego samego symbolu
  (`rollups.refresh_all` po każdej zapisanej minutówce); pochodne powstają **tylko** dla symbolu
  zbieranego w `MINUTE` — para śledzona wprost w `HOUR` ma własne świece w `candles`
  ([app.py:270](modules/market-data/market_data/app.py#L270) opisuje, dlaczego kolejność odczytu
  jest właśnie taka);
- `coverage_ranges` — zweryfikowane przedziały czasu, jedyne źródło odpowiedzi „rynek był zamknięty"
  kontra „tego nie zebraliśmy", i to, od czego planowanie zleceń odejmuje pracę do wykonania;
- `tracked_pairs` — wiersz decyzji operatora, dziś przestawiany na `untracked`, nigdy nie usuwany.

Dwa istniejące więzy ograniczają swobodę:

1. `collection_job_chunks` ma klucz obcy na `tracked_pairs(symbol, resolution)`, założony wprost
   przy tym, że zdjęcie pary przestawia wiersz, a nie go kasuje
   ([0005_collection_jobs.py:117](modules/market-data/migrations/versions/0005_collection_jobs.py#L117)).
2. Zbieranie pary jest żywe: subskrypcja u gatewaya i, być może, biegnące zlecenie zapisujące
   świece kawałek po kawałku. Kasowanie danych pary, która wciąż jest zbierana, to wyścig.

## Goals / Non-Goals

**Goals:**

- Skasowanie zostawia archiwum w stanie, w którym para wygląda jak nigdy niezbierana — łącznie z
  pokryciem, żeby kolejne zlecenie pobrało zakres od nowa.
- Skasowanie nie może częściowo się udać.
- Skasowanie jest odnotowane trwale i czytelne w tej samej historii co dociągnięcia.
- Żadna świeca nie ginie inaczej niż na jawne żądanie operatora.

**Non-Goals:**

- Kosz, cofnięcie skasowania, miękkie kasowanie z opóźnionym sprzątaniem. Operacja jest
  nieodwracalna i tak ma być nazwana; półśrodek dawałby fałszywe poczucie bezpieczeństwa.
- Kasowanie zakresu czasu („usuń rok 2019 dla tej pary"). Jednostką jest para.
- Kasowanie wielu par jednym żądaniem kontraktu. Instrument w czterech interwałach to cztery
  żądania — terminal i tak wysyła je równolegle, tak jak dziś przy zdejmowaniu.
- Zmiana czegokolwiek w tym, jak zlecenia planują pracę.

## Decisions

### Kasowanie to trzy kroki, nie jedno żądanie do bazy

Wyścig z żywym zbieraniem rozstrzyga kolejność, nie zamek:

1. **Zamknij decyzję** (transakcja): `tracked_pairs` na `untracked`, a nierozpoczęte kawałki zleceń
   tej pary (`pending`) na `skipped`. Od tego momentu nic nowego nie ruszy dla tej pary.
2. **Zatrzymaj to, co biegnie**: synchronizacja ingestu (ta sama, którą robi dziś zdjęcie pary)
   zamyka subskrypcję.
3. **Usuń dane i odnotuj** (jedna transakcja): policz świece i ich zakres, usuń `candles`,
   `derived_candles` (gdy kasowana jest seria minutowa) i `coverage_ranges`, zapisz wiersz
   skasowania.

Rozważane zamiast tego: odmowa (409) dla pary z biegnącym zleceniem. Odrzucone — operator kasuje
najczęściej właśnie dlatego, że zlecenie pobrało nie to, co chciał, więc żądanie „poczekaj, aż
skończy się ściągać to, czego nie chcesz" jest wrogie.

### Kawałek nigdy nie zapisuje dla pary, której nikt nie zbiera

Krok 1 nie zatrzymuje kawałka **już w locie** — ten może skończyć żądanie do gatewaya po
skasowaniu danych i dopisać świece do pary, która właśnie przestała istnieć. Dlatego `execute_chunk`
przed zapisem sprawdza, czy para jest nadal śledzona; jeśli nie — porzuca wynik i osadza kawałek
jako `skipped`.

To jest jedno zdanie w runnerze i domyka też wcześniejszy, cichszy wyścig: dziś zdjęcie pary w
trakcie zlecenia nie przerywa dopisywania jej świec.

### Wiersz w `tracked_pairs` zostaje

Otwarte pytanie z proposalu: wiersz pary trwał dotąd jako lewa krawędź luki do domknięcia przy
ponownym dodaniu, a po skasowaniu danych ta rola znika. Mimo to wiersz zostaje — trzyma go klucz
obcy `collection_job_chunks`, a historia zleceń ma przeżyć skasowanie (decyzja operatora). Usunięcie
wiersza wymagałoby albo skasowania historii zleceń, albo zerwania więzu, który dziś gwarantuje, że
kawałek nazywa parę istniejącą.

Wiersz nie niesie żadnej obietnicy o danych: `collect_from` zostaje, ale po skasowaniu nic nie
uchodzi za pokryte, więc ponowne dodanie planuje cały zakres od nowa. To jest dokładnie zachowanie
opisane scenariuszem „Ponowne dodanie pary skasowanej".

### Skasowania w osobnej tabeli, nie jako rodzaj zlecenia

Migracja `0006_pair_deletions.py`: `symbol`, `resolution`, `deleted_at`, `candles_removed`,
`removed_from`, `removed_to` (dwa ostatnie puste, gdy nie było ani jednej świecy), klucz obcy na
`tracked_pairs` na wzór kawałków.

Rozważane: dopisanie skasowania jako zlecenia o osobnym stanie. Odrzucone — zlecenie ma kawałki,
postęp, ponowienie i wycenę, a skasowanie nie ma z tego nic; wpychanie go w ten kształt zmusiłoby
każdy odczyt zleceń do rozróżniania, czy patrzy na pracę, czy na jej odjęcie.

Skasowania czyta osobny endpoint `GET /deletions` (zawężany parą, jak `GET /jobs`), a łączy je w
jedną oś czasu terminal. Kontrakt zostaje przy dwóch prostych kształtach zamiast jednego kształtu z
wariantem.

### `DELETE /pairs/{symbol}` odpowiada, ile zniknęło

Dziś 204 bez treści. Po zmianie 200 z parą, liczbą usuniętych świec i zakresem, który obejmowały —
to jedyny moment, w którym da się to pokazać operatorowi, a panel ma tym potwierdzić wykonanie.
Para nieśledzona nadal jest odmową (404), nie cichym sukcesem.

### Terminal: jeden przycisk, potwierdzenie mówiące o utracie

`Stop` znika, zostaje `Delete` w obu miejscach (interwał w rozwiniętym wierszu, instrument w
wierszu). Potwierdzenie wymienia interwały, mówi o nieodwracalnym usunięciu danych i podaje, od
kiedy dane są zebrane — operator ma zobaczyć rozmiar straty, zanim ją zatwierdzi, a tę datę wiersz
i tak już zna z kolumny `Data since`.

Kasowanie instrumentu w całości to nadal N równoległych żądań, jak dziś. Powodzenie części z nich
przy porażce reszty MUST być pokazane jako to, czym jest: panel odświeża listę i mówi, czego nie
udało się skasować.

## Risks / Trade-offs

- **Operator kasuje przez pomyłkę i traci historię, której provider już nie ma** → potwierdzenie
  nazywa operację kasowaniem, mówi o nieodwracalności i podaje, od kiedy dane są; wpis w historii
  zostawia ślad, co i kiedy zniknęło. Kosza nie ma i to jest świadome (Non-Goals).
- **Świece pochodne przeżywają skasowanie minutówek** → usuwane w tej samej transakcji. Bez tego
  odczyt rozdzielczości pochodnej odpowiadałby z `derived_candles` danymi wyliczonymi ze świec,
  których już nie ma.
- **Pokrycie przeżywa świece** → jedna transakcja. To jest najgorszy możliwy stan pośredni: para
  bez danych, której planowanie zleceń nie ruszy, bo zakres uchodzi za pobrany.
- **Kasowanie na dużej parze blokuje bazę na długo** (dziesięć lat `MINUTE` to miliony wierszy) →
  usunięcie idzie po kluczu głównym `(symbol, resolution, period_start)`, więc jest zakresowe, a nie
  po skanie; przy pierwszym uruchomieniu na realnych danych warto zmierzyć czas i, jeśli okaże się
  bolesny, dzielić usuwanie na porcje — ale dzielenie oznaczałoby porzucenie jednej transakcji, więc
  MUST NOT wejść bez ponownego rozstrzygnięcia stanu pośredniego.
- **Zależność od `rework-instrument-collection`** → delty tej zmiany są pisane wobec stanu po jego
  archiwizacji (zakładka `Data History`, zdejmowanie interwału i instrumentu, pojęcie zlecenia).
  Wdrażanie w odwrotnej kolejności nie ma sensu i nie jest przewidziane.

## Migration Plan

Migracja `0006_pair_deletions.py` dokłada jedną tabelę; nie ma danych do przeniesienia, bo dotąd
żadne skasowanie nie było możliwe. Wycofanie: `downgrade` kasuje tabelę, a moduł wraca do
zachowania, w którym `DELETE /pairs` tylko zatrzymuje zbieranie — świece usunięte przed wycofaniem
nie wracają.

`DELETE /pairs` zmienia znaczenie bez zmiany ścieżki. Jedynym konsumentem tego endpointu jest
terminal z tego repozytorium i obie zmiany idą razem; gdyby pojawił się konsument zewnętrzny,
zmiana MUST być dla niego łamiąca (proposal.md, „What Changes").
