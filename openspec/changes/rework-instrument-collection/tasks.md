## 1. capital-gateway: katalog zawężalny do klasy aktywów

- [x] 1.1 Dołożyć `asset_class` do `CapitalAdapter.list_instruments` — odsiew w trakcie obchodu drzewa, osobny pułap `max_nodes` dla zapytania z filtrem, `truncated` liczone jak dotąd
- [x] 1.2 Rozszerzyć `GET /instruments` o parametr `asset_class`, z odmową nazywającą znane klasy, gdy podana jest spoza nich
- [x] 1.3 Dodać `GET /asset-classes` zwracające zbiór klas, jakimi moduł opisuje instrumenty
- [x] 1.4 Testy: wyliczenie jednej klasy zwraca wyłącznie tę klasę, klasa nieznana jest odmawiana z listą znanych, nieczytelna gałąź nadal jest pomijana zamiast wywracać odczyt
- [x] 1.5 Uzupełnić README modułu o filtr klasy i o to, dlaczego zapytanie z filtrem ma własny pułap obchodu

## 2. market-data: trwały stan zleceń

- [ ] 2.1 Migracja `0005_collection_jobs.py` — tabele `collection_jobs` i `collection_job_chunks` oraz kolumna `collect_from` w `tracked_pairs`, wypełniona dla istniejących wierszy z `added_at` minus domyślna głębokość
- [ ] 2.2 Moduł `market_data/jobs/store.py` — zapis i odczyt zleceń i kawałków, stan zlecenia wyprowadzany ze stanów kawałków, nigdy trzymany osobno
- [ ] 2.3 Przestemplowanie kawałków `running` na `interrupted` przy starcie modułu, w miejscu, gdzie ingest już się synchronizuje
- [ ] 2.4 Testy: stan zlecenia wynika z kawałków dla każdej kombinacji, restart zamienia kawałek w toku na przerwany, historia sprzed restartu jest odczytywalna

## 3. market-data: planowanie i wycena zlecenia

- [ ] 3.1 `market_data/jobs/plan.py` — przycięcie daty OD do `earliest_reachable`, odjęcie tego, co pokrywa `coverage_ranges`, podział reszty na okna po `MAX_BARS_PER_FILL` świec danej rozdzielczości
- [ ] 3.2 Wycena zlecenia wyprowadzana z tego samego planu: liczba kawałków, szacowana liczba świec z `PERIOD_SECONDS`, szacowany rozmiar jako liczba świec razy stała bajtów na wiersz
- [ ] 3.3 Odmowa dla daty w przyszłości; data dowolnie wczesna MUST być przycinana, nigdy odrzucana
- [ ] 3.4 Testy: rok 1850 przycięty do osiągalnego, para w pełni pokryta nie rodzi kawałków, dziesięć lat `MINUTE` daje spodziewaną liczbę okien, dziesięć lat `DAY` mieści się w jednym

## 4. market-data: wykonywanie zlecenia

- [ ] 4.1 Przepisać `fill_gap` na wykonanie kawałka o zadanym oknie `(od, do)` zamiast głębokości liczonej z konfiguracji, zachowując jedno żądanie do gatewaya na kawałek
- [ ] 4.2 Runner kawałków pod istniejącym `backfill_concurrency` i tym samym rate gate; wynik każdego kawałka zapisywany natychmiast po jego zakończeniu
- [ ] 4.3 Kawałek nieudany odnotowuje nazwaną przyczynę i nie zatrzymuje pozostałych; kawałek sięgający poza koniec historii providera jest pomijany, a nie oznaczany jako nieudany
- [ ] 4.4 Ponowienie: wykonanie wyłącznie kawałków `failed` i `interrupted` jako kolejna próba tego samego zlecenia, z podbiciem numeru próby
- [ ] 4.5 Podłączyć `record_coverage` tak, by luka po nieudanym kawałku dawała rozdzielone przedziały pokrycia
- [ ] 4.6 Testy: porażka kawałka w środku zostawia świece z kawałków udanych i lukę w pokryciu, ponowienie nie pyta o zakresy już pokryte, ponowienie zlecenia bez porażek jest odmawiane, odczyt świec w trakcie zlecenia nie czeka na jego koniec

## 5. market-data: kontrakt

- [ ] 5.1 Modele w `contract.py` dla zlecenia, kawałka, wyceny i wyniku dodania wielu par
- [ ] 5.2 `POST /pairs` przyjmuje wiele par i opcjonalną datę OD, odpowiada wynikiem osobno dla każdej pary i identyfikatorem zlecenia; żądanie w starej postaci zachowuje dotychczasowe znaczenie
- [ ] 5.3 `POST /jobs/estimate` — wycena bez skutków ubocznych, z nazwaniem par nieznanych providerowi i wyceną pozostałych
- [ ] 5.4 `GET /jobs` z zawężeniem do pary oraz `GET /jobs/{id}` — stan, postęp z kawałków, świece zapisane, pokryty zakres, przyczyny porażek
- [ ] 5.5 `POST /jobs/{id}/retry` — odpowiada tym, co zostanie ponowione; odmawia dla zlecenia bez porażek i dla zlecenia nieznanego
- [ ] 5.6 `GET /pairs` niesie `collect_from` dla każdej pary
- [ ] 5.7 Testy kontraktowe, w tym utrzymanie starej postaci `POST /pairs`, oraz aktualizacja README modułu o pojęcie zlecenia i kawałka

## 6. terminal: warstwa danych

- [ ] 6.1 Typy zlecenia, kawałka, wyceny i klasy aktywów w `src/data/types.ts`, w słowniku terminala, nie w kształcie drutu
- [ ] 6.2 Rozszerzyć `ArchiveAdmin` w `src/data/source.ts` o wycenę, tworzenie zlecenia dla wielu par, odczyt zleceń i ponowienie
- [ ] 6.3 Implementacja w `src/data/archive.ts` z mapowaniem snake_case i istniejącym `mapStatus`, bez wycieku kształtów drutu poza plik
- [ ] 6.4 `src/data/gatewaySource.ts` — wyliczenie instrumentów klasy oraz odczyt klas aktywów
- [ ] 6.5 Testy warstwy danych na `httpDouble`

## 7. terminal: reużywalny autocomplete

- [ ] 7.1 `src/ui/Autocomplete.tsx` — sterowany propem źródła, obsługa strzałek i Entera, Escape, jawny brak dopasowań, jawna porażka źródła z ponowieniem, widoczny i odwoływalny wybór
- [ ] 7.2 Przenieść debounce i ochronę przed wyprzedzającą się odpowiedzią z `useInstrumentSearch` do wspólnego haka używanego przez komponent
- [ ] 7.3 Trzy źródła: klasy aktywów, instrumenty w klasie, instrumenty archiwizowane
- [ ] 7.4 Sygnalizacja ucięcia listy przy podpowiedziach, ze wskazaniem, że wpisanie frazy sięga dalej
- [ ] 7.5 Testy komponentu, w tym identyczność zachowania klawiatury dla wszystkich trzech źródeł

## 8. terminal: połączona zakładka Instruments

- [ ] 8.1 Usunąć wpis `archive` z `src/app/tabs.ts`, zostawiając `/archive` na stronie „nie ma takiej zakładki"; przenieść zawartość `src/archive/` do `src/instruments/` i skasować katalog `archive`
- [ ] 8.2 Lista per instrument: jeden wiersz, wszystkie interwały skrótem w jednej kolumnie, moment rozpoczęcia archiwizowania, stan zbierania; grupowanie `/pairs` po symbolu po stronie terminala
- [ ] 8.3 Wyróżnienie interwału, dla którego zbieranie nie nadąża albo ustało, wewnątrz wiersza
- [ ] 8.4 Pokrycie po rozwinięciu instrumentu — osobno dla każdego interwału, z nazwaniem luk
- [ ] 8.5 Zdejmowanie pojedynczego interwału i całego instrumentu, oba za potwierdzeniem wymieniającym, co przestanie być zbierane, i stwierdzającym, że świece zostają
- [ ] 8.6 Zachować dotychczasowe rozróżnienie „nic nie jest archiwizowane" od „nie udało się zapytać"
- [ ] 8.7 Testy widoku listy

## 9. terminal: kreator dodawania i dialog akceptacji

- [ ] 9.1 Kreator: klasa aktywów, instrument w klasie, multiselect interwałów, data OD — z blokadą zatwierdzenia i nazwaniem tego, czego brakuje
- [ ] 9.2 Zmiana klasy czyści wybrany instrument
- [ ] 9.3 Data OD wcześniejsza niż historia providera jest prośbą o wszystko, nie błędem walidacji
- [ ] 9.4 Dialog akceptacji: wiersz na parę instrument–interwał z zakresem, szacowaną liczbą rekordów i rozmiarem, sumą dla całości, oznaczeniem zakresu przyciętego i pary już zbieranej
- [ ] 9.5 Nieudana wycena zamyka drogę do akceptacji na ślepo; odrzucenie dialogu nie dodaje niczego i zachowuje wybory kreatora
- [ ] 9.6 Akceptacja dodaje pary, uruchamia zlecenie i wskazuje zakładkę `Data History` jako miejsce śledzenia postępu; odmowa dla części par nie przekreśla reszty
- [ ] 9.7 Testy kreatora i dialogu

## 10. terminal: zakładka Data History

- [ ] 10.1 Wpis `data-history` w `src/app/tabs.ts` i katalog `src/history/`
- [ ] 10.2 Widok per instrument i per interwał: kiedy, jaki zakres, ile świec, jaki stan; wiele dociągnięć tej samej pary od najnowszego
- [ ] 10.3 Praca w toku: udział ukończonych kawałków, świece zapisane do tej pory, para właśnie obsługiwana
- [ ] 10.4 Odpytywanie co 30 s, ustające przy opuszczeniu zakładki; nieudane odświeżenie zostawia wiersze i mówi o sobie
- [ ] 10.5 Zakończenie powodzeniem na zielono z liczbą świec i zakresem; pokrycie częściowe jako osobny stan z udziałem pokrycia i wyliczeniem przyczyn
- [ ] 10.6 Ponowienie z poziomu wiersza — z powiedzeniem, co zostanie ponowione, przed zrobieniem tego, i z obsługą sytuacji, w której samo zlecenie ponowienia zawodzi
- [ ] 10.7 Odróżnienie „nic jeszcze nie dociągano" od „archiwum nieosiągalne"
- [ ] 10.8 Testy widoku, w tym odpytywania i ponowienia

## 11. terminal: wykres tylko na instrumentach archiwizowanych

- [ ] 11.1 Zamienić `src/grid/SymbolField.tsx` na `Autocomplete` ze źródłem „instrumenty archiwizowane"
- [ ] 11.2 Ograniczyć rozdzielczości w slocie do tych, w których wybrany instrument jest archiwizowany
- [ ] 11.3 Puste archiwum i nieosiągalna lista mówią o sobie wprost i kierują do zakładki `Instruments`, zachowując instrument już ustawiony w slocie
- [ ] 11.4 Slot wracający z sesji z instrumentem zdjętym z archiwizowanych rozpoznaje to i mówi, zamiast wpadać w pętlę wznawiania
- [ ] 11.5 Usunąć drogę z wyniku wyszukiwania wprost do slotu wraz z jej testami
- [ ] 11.6 Testy slotu

## 12. Domknięcie

- [ ] 12.1 `ruff` i `pytest` w `capital-gateway` i `market-data`, `pnpm lint` i testy w `terminal`
- [ ] 12.2 Przejść ścieżkę end-to-end na uruchomionym zestawie: dodanie instrumentu w kilku interwałach od odległej daty, dialog, zlecenie, podgląd postępu, wymuszona porażka i ponowienie
- [ ] 12.3 Zaktualizować README terminala o nowy układ zakładek oraz `docs/` tam, gdzie opisują zakładkę `Archive`
- [ ] 12.4 `openspec validate rework-instrument-collection --strict`
