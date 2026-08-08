## 1. capital-gateway: katalog zawężalny do klasy aktywów

- [x] 1.1 Dołożyć `asset_class` do `CapitalAdapter.list_instruments` — odsiew w trakcie obchodu drzewa, osobny pułap `max_nodes` dla zapytania z filtrem, `truncated` liczone jak dotąd
- [x] 1.2 Rozszerzyć `GET /instruments` o parametr `asset_class`, z odmową nazywającą znane klasy, gdy podana jest spoza nich
- [x] 1.3 Dodać `GET /asset-classes` zwracające zbiór klas, jakimi moduł opisuje instrumenty
- [x] 1.4 Testy: wyliczenie jednej klasy zwraca wyłącznie tę klasę, klasa nieznana jest odmawiana z listą znanych, nieczytelna gałąź nadal jest pomijana zamiast wywracać odczyt
- [x] 1.5 Uzupełnić README modułu o filtr klasy i o to, dlaczego zapytanie z filtrem ma własny pułap obchodu
- [x] 1.6 *(odkryte podczas implementacji grupy 2)* Dołożyć `before` do `history.collect()`, `adapter.get_history` i `GET /instruments/{symbol}/history`, żeby głęboki odczyt dało się zakotwiczyć w przeszłości, nie tylko w chwili bieżącej — bez tego kawałek zlecenia starszy niż jeden fill nie ma czym się wykonać
- [x] 1.7 Testy: odczyt zakotwiczony w przeszłości kończy pierwszą stronę na podanym momencie, dalsze stronicowanie wstecz działa jak dotychczas, brak kotwicy zachowuje dotychczasowe zachowanie

## 2. market-data: trwały stan zleceń

- [x] 2.1 Migracja `0005_collection_jobs.py` — tabele `collection_jobs` i `collection_job_chunks` oraz kolumna `collect_from` w `tracked_pairs`, wypełniona dla istniejących wierszy z `added_at` minus domyślna głębokość
- [x] 2.2 Moduł `market_data/jobs/store.py` — zapis i odczyt zleceń i kawałków, stan zlecenia wyprowadzany ze stanów kawałków, nigdy trzymany osobno
- [x] 2.3 Przestemplowanie kawałków `pending` i `running` na `interrupted` przy starcie modułu (żaden runner nie przeżywa restartu), w miejscu, gdzie ingest już się synchronizuje
- [x] 2.4 Testy: stan zlecenia wynika z kawałków dla każdej kombinacji, restart zamienia kawałek w toku i w kolejce na przerwany, historia sprzed restartu jest odczytywalna
- [x] 2.5 *(odkryte podczas implementacji)* `tracking.track`/`add_pair` przyjmują i przechowują `collect_from`, z domyślną głębokością gdy nie podano i `LEAST` przy ponownym dodaniu, żeby zlecenia miały do czego kotwiczyć swoje kawałki

## 3. market-data: planowanie i wycena zlecenia

- [x] 3.1 `market_data/jobs/plan.py` — przycięcie daty OD do `earliest_reachable`, odjęcie tego, co pokrywa `coverage_ranges`, podział reszty na okna po `MAX_BARS_PER_FILL` świec danej rozdzielczości
- [x] 3.2 Wycena zlecenia wyprowadzana z tego samego planu: liczba kawałków, szacowana liczba świec z `PERIOD_SECONDS`, szacowany rozmiar jako liczba świec razy stała bajtów na wiersz
- [x] 3.3 Odmowa dla daty w przyszłości; data dowolnie wczesna MUST być przycinana, nigdy odrzucana
- [x] 3.4 Testy: rok 1850 przycięty do osiągalnego, para w pełni pokryta nie rodzi kawałków, dziesięć lat `MINUTE` daje spodziewaną liczbę okien, dziesięć lat `DAY` mieści się w jednym

## 4. market-data: wykonywanie zlecenia

- [x] 4.0 *(odkryte podczas implementacji grupy 3)* `split_into_windows` i `plan_chunks` układają kawałki od najnowszego wstecz, nie od najstarszego — inaczej prośba o głębię sprzed znanej granicy historii providera wysyłałaby jedno żądanie na każdy skazany na porażkę kawałek zamiast odkryć granicę raz
- [x] 4.1 Nowa funkcja `execute_chunk` wykonania kawałka o zadanym oknie `(od, do)` przez `before=chunk_end` na gatewayu, osobna od `fill_gap` (ten zostaje dla pojedynczych par bez zlecenia — restart i wznowienie strumienia); `GatewayHistory.history()` w market-data przyjmuje `before`
- [x] 4.2 `JobRunner` z pulą workerów pod `backfill_concurrency`, dzielącym `asyncio.Semaphore` z `Ingest` (zbudowany raz w `app.py`, przekazany do obu); wynik każdego kawałka zapisywany natychmiast po jego zakończeniu; `notify()` budzi bezczynne workery
- [x] 4.3 Kawałek nieudany odnotowuje nazwaną przyczynę i nie zatrzymuje pozostałych; kawałek, który odkryje `history_ended`, kończy się jako wykonany (nawet z zerem świec), a wszystkie pozostałe jeszcze niepodjęte kawałki tej pary w tym zleceniu są masowo oznaczane jako pominięte (`skip_chunks_beyond_history`) zamiast każdy z osobna odkrywać tę samą granicę
- [x] 4.4 Ponowienie: `store.retry_job` (grupa 2) resetuje kawałki `failed`/`interrupted` na `pending` z podbitym numerem próby; `JobRunner`, odpytując kolejkę, podejmuje je bez rozróżniania od pierwszego przebiegu — jawne obudzenie przez `notify()` po ponowieniu zostaje spięte w grupie 5 (endpoint HTTP)
- [x] 4.5 `record_coverage` wywoływane dla pełnego żądanego okna kawałka (nie tylko zakresu zwróconych świec), żeby granica `history_ended` i luka po nieudanym kawałku dawały poprawne, rozdzielone przedziały pokrycia bez szwu między sąsiadującymi kawałkami
- [x] 4.6 Testy: sukces zapisuje świece i osiada jako `done`, puste okno to `done` z zerem świec (nie `failed`), pełne okno pokryte nawet gdy świec mało, odmowa/nieosiągalność gatewaya osiada jako `failed` z powodem i nie propaguje wyjątku, odkrycie `history_ended` masowo pomija starsze kawałki tej samej pary i nie rusza innej pary/zlecenia, runner podejmuje i kończy oczekujący kawałek, `notify()` budzi bezczynny worker bez czekania na odpytanie, `stop()` kończy workery; `Ingest` przyjmuje i używa dostarczonego semafora zamiast budować własny

## 5. market-data: kontrakt

- [x] 5.1 Modele w `contract.py` dla zlecenia, kawałka, wyceny i wyniku dodania wielu par
- [x] 5.2 `POST /pairs` przyjmuje wiele par i opcjonalną datę OD, odpowiada wynikiem osobno dla każdej pary i identyfikatorem zlecenia; żądanie w starej postaci zachowuje dotychczasowe znaczenie i dotychczasowy status błędu, gdy jedyna para zostaje odrzucona
- [x] 5.3 `POST /jobs/estimate` — wycena bez skutków ubocznych, z nazwaniem par nieznanych providerowi i wyceną pozostałych
- [x] 5.4 `GET /jobs` z zawężeniem do pary (jeden wiersz na parę) oraz `GET /jobs/{id}` — stan, postęp z kawałków, świece zapisane, para w toku, przyczyny porażek
- [x] 5.5 `POST /jobs/{id}/retry` — odpowiada tym, co zostanie ponowione, budzi `JobRunner`; odmawia (409) dla zlecenia bez porażek i (404) dla zlecenia nieznanego
- [x] 5.6 `GET /pairs` niesie `collect_from` dla każdej pary
- [x] 5.7 Testy kontraktowe (wiele par jedną decyzją, częściowa odmowa, stara postać, wycena, odczyt/listowanie/ponowienie zleceń), zaktualizowany `test_the_http_routes_are_all_described`, oraz aktualizacja README modułu o pojęcie zlecenia i kawałka

## 6. terminal: warstwa danych

- [x] 6.1 Typy zlecenia, kawałka, wyceny i klasy aktywów w `src/data/types.ts`, w słowniku terminala, nie w kształcie drutu
- [x] 6.2 Rozszerzyć `ArchiveAdmin` w `src/data/source.ts` o wycenę, tworzenie zlecenia dla wielu par, odczyt zleceń i ponowienie
- [x] 6.3 Implementacja w `src/data/archive.ts` z mapowaniem snake_case i istniejącym `mapStatus`, bez wycieku kształtów drutu poza plik
- [x] 6.4 `src/data/gatewaySource.ts` — wyliczenie instrumentów klasy oraz odczyt klas aktywów
- [x] 6.5 Testy warstwy danych na `httpDouble`

## 7. terminal: reużywalny autocomplete

- [x] 7.1 `src/ui/Autocomplete.tsx` — sterowany propem źródła, obsługa strzałek i Entera, Escape, jawny brak dopasowań, jawna porażka źródła z ponowieniem, widoczny i odwoływalny wybór
- [x] 7.2 Przenieść debounce i ochronę przed wyprzedzającą się odpowiedzią z `useInstrumentSearch` do wspólnego haka używanego przez komponent
- [x] 7.3 Trzy źródła: klasy aktywów, instrumenty w klasie, instrumenty archiwizowane
- [x] 7.4 Sygnalizacja ucięcia listy przy podpowiedziach, ze wskazaniem, że wpisanie frazy sięga dalej
- [x] 7.5 Testy komponentu, w tym identyczność zachowania klawiatury dla wszystkich trzech źródeł

## 8. terminal: połączona zakładka Instruments

- [x] 8.1 Usunąć wpis `archive` z `src/app/tabs.ts`, zostawiając `/archive` na stronie „nie ma takiej zakładki"; przenieść zawartość `src/archive/` do `src/instruments/` i skasować katalog `archive`
- [x] 8.2 Lista per instrument: jeden wiersz, wszystkie interwały skrótem w jednej kolumnie, moment rozpoczęcia archiwizowania, stan zbierania; grupowanie `/pairs` po symbolu po stronie terminala
- [x] 8.3 Wyróżnienie interwału, dla którego zbieranie nie nadąża albo ustało, wewnątrz wiersza
- [x] 8.4 Pokrycie po rozwinięciu instrumentu — osobno dla każdego interwału, z nazwaniem luk
- [x] 8.5 Zdejmowanie pojedynczego interwału i całego instrumentu, oba za potwierdzeniem wymieniającym, co przestanie być zbierane, i stwierdzającym, że świece zostają
- [x] 8.6 Zachować dotychczasowe rozróżnienie „nic nie jest archiwizowane" od „nie udało się zapytać"
- [x] 8.7 Testy widoku listy

## 9. terminal: kreator dodawania i dialog akceptacji

- [x] 9.1 Kreator: klasa aktywów, instrument w klasie, multiselect interwałów, data OD — z blokadą zatwierdzenia i nazwaniem tego, czego brakuje
- [x] 9.2 Zmiana klasy czyści wybrany instrument
- [x] 9.3 Data OD wcześniejsza niż historia providera jest prośbą o wszystko, nie błędem walidacji
- [x] 9.4 Dialog akceptacji: wiersz na parę instrument–interwał z zakresem, szacowaną liczbą rekordów i rozmiarem, sumą dla całości, oznaczeniem zakresu przyciętego i pary już zbieranej
- [x] 9.5 Nieudana wycena zamyka drogę do akceptacji na ślepo; odrzucenie dialogu nie dodaje niczego i zachowuje wybory kreatora
- [x] 9.6 Akceptacja dodaje pary, uruchamia zlecenie i wskazuje zakładkę `Data History` jako miejsce śledzenia postępu; odmowa dla części par nie przekreśla reszty
- [x] 9.7 Testy kreatora i dialogu

## 10. terminal: zakładka Data History

- [x] 10.1 Wpis `data-history` w `src/app/tabs.ts` i katalog `src/history/`
- [x] 10.2 Widok per instrument i per interwał: kiedy, jaki zakres, ile świec, jaki stan; wiele dociągnięć tej samej pary od najnowszego
- [x] 10.3 Praca w toku: udział ukończonych kawałków, świece zapisane do tej pory, para właśnie obsługiwana
- [x] 10.4 Odpytywanie co 30 s, ustające przy opuszczeniu zakładki; nieudane odświeżenie zostawia wiersze i mówi o sobie
- [x] 10.5 Zakończenie powodzeniem na zielono z liczbą świec i zakresem; pokrycie częściowe jako osobny stan z udziałem pokrycia i wyliczeniem przyczyn
- [x] 10.6 Ponowienie z poziomu wiersza — z powiedzeniem, co zostanie ponowione, przed zrobieniem tego, i z obsługą sytuacji, w której samo zlecenie ponowienia zawodzi
- [x] 10.7 Odróżnienie „nic jeszcze nie dociągano" od „archiwum nieosiągalne"
- [x] 10.8 Testy widoku, w tym odpytywania i ponowienia

## 11. terminal: wykres tylko na instrumentach archiwizowanych

- [x] 11.1 Zamienić `src/grid/SymbolField.tsx` na `Autocomplete` ze źródłem „instrumenty archiwizowane"
- [x] 11.2 Ograniczyć rozdzielczości w slocie do tych, w których wybrany instrument jest archiwizowany
- [x] 11.3 Puste archiwum i nieosiągalna lista mówią o sobie wprost i kierują do zakładki `Instruments`, zachowując instrument już ustawiony w slocie
- [x] 11.4 Slot wracający z sesji z instrumentem zdjętym z archiwizowanych rozpoznaje to i mówi, zamiast wpadać w pętlę wznawiania
- [x] 11.5 Usunąć drogę z wyniku wyszukiwania wprost do slotu wraz z jej testami
- [x] 11.6 Testy slotu

## 12. Domknięcie

- [ ] 12.1 `ruff` i `pytest` w `capital-gateway` i `market-data`, `pnpm lint` i testy w `terminal`
- [ ] 12.2 Przejść ścieżkę end-to-end na uruchomionym zestawie: dodanie instrumentu w kilku interwałach od odległej daty, dialog, zlecenie, podgląd postępu, wymuszona porażka i ponowienie
- [ ] 12.3 Zaktualizować README terminala o nowy układ zakładek oraz `docs/` tam, gdzie opisują zakładkę `Archive`
- [ ] 12.4 `openspec validate rework-instrument-collection --strict`
