## 1. market-data — pętla robocza przeżywa własną awarię

- [x] 1.1 `JobRunner._worker_loop`: osłona obejmuje całą iterację — przejęcie kawałka i czekanie też, nie tylko `execute_chunk`
- [x] 1.2 `asyncio.CancelledError` leci dalej nietknięty; `stop()` MUST zostać jedynym prawidłowym końcem pętli
- [x] 1.3 Przerwa po niepowodzeniu: 5 s, podwajana do sufitu 60 s, zerowana po pierwszym udanym przejęciu kawałka
- [x] 1.4 Przyczyna trafia do logu przy każdym niepowodzeniu, z rozróżnieniem „nie udało się wziąć pracy" od „kawałek wybuchł" (`_fail_orphan` zostaje bez zmian — nie ma czego rozstrzygać, gdy nic nie zostało przejęte)
- [x] 1.5 Test: przejęcie kawałka rzuca raz, worker wykonuje kawałek przy kolejnym podejściu bez restartu modułu
- [x] 1.6 Test: przejęcie rzuca raz za razem — worker nie kręci się bez przerwy (odstępy rosną), a po ustaniu przyczyny wraca do pracy
- [x] 1.7 Test: `stop()` w trakcie czekania kończy pętlę i nie zapisuje jej jako awarii

## 2. market-data — moment ostatniej aktywności

- [x] 2.1 `Job` i `JobPairView` dostają `last_activity_at`: maksimum ze znanych `finished_at` i `started_at` swoich kawałków, a w braku obu — `created_at` zlecenia
- [x] 2.2 `JobOut` i `JobPairViewOut` wystawiają to pole; opis w kontrakcie mówi, że kawałek trwający też liczy się jako aktywność
- [x] 2.3 Test: zlecenie z kawałkiem w toku podaje moment jego rozpoczęcia, a nie moment poprzedniego rozstrzygnięcia
- [x] 2.4 Test: zlecenie bez ani jednego rozpoczętego kawałka podaje moment swojego utworzenia
- [x] 2.5 Test: wiersz zawężony do pary liczy moment z kawałków tej pary — aktywność innej pary tego samego zlecenia go nie przesuwa
- [x] 2.6 Test: dwa odczyty tego samego stojącego zlecenia dają ten sam moment

## 3. terminal — wspólny dialog

- [x] 3.1 Sprawdzone, czy `jsdom` unosi natywny `<dialog>` — nie unosi w żadnej wersji (25, 26, 30: pusta implementacja bez `showModal`), więc `jsdom` zostaje na `^25`, a fokus i `Escape` są obsłużone w komponencie; cały zestaw testów terminala uruchomiony jako punkt odniesienia (242 passed)
- [x] 3.2 Komponent `ConfirmDialog` w `src/ui/`: tytuł, treść, nazwa akcji potwierdzającej, praca wykonywana po potwierdzeniu, zamknięcie
- [x] 3.3 Praca w toku należy do komponentu: akcja potwierdzająca mówi, że trwa, i nie zleca pracy drugi raz
- [x] 3.4 Błąd zatrzymany w dialogu — nazwany w środku, z możliwością ponowienia próby; zamyka się wyłącznie powodzenie
- [x] 3.5 `Escape` przechwycone, gdy praca trwa; poza tym zamyka jak wycofanie się; `Tab` nie wychodzi poza dialog
- [x] 3.6 Fokus wraca po zamknięciu na element, z którego dialog został wywołany
- [x] 3.7 Testy komponentu: wycofanie nic nie robi, praca w toku blokuje drugie potwierdzenie, błąd zostaje w dialogu, powodzenie zamyka, `Escape` w trakcie pracy nie zamyka

## 4. terminal — istniejące dialogi przechodzą na wspólny

- [x] 4.1 `AcceptanceDialog` (`AddInstrumentWizard.tsx`) zbudowany na wspólnym komponencie; wycena i wiersze par zostają jego treścią
- [x] 4.2 `DeleteDialog` (`InstrumentsView.tsx`) zbudowany na wspólnym komponencie; nieodwracalność i zasięg danych zostają w treści
- [x] 4.3 Istniejące testy obu dialogów MUST przejść bez zmiany treści asercji — zmienia się implementacja, nie zachowanie; poprawki dopuszczalne wyłącznie tam, gdzie test sięgał do struktury DOM starego dialogu
- [x] 4.4 W terminalu nie zostaje żadne potwierdzenie zadawane poza dialogiem (przegląd `src/` pod kątem pytań o zgodę)

## 5. terminal — zakładka Data History

- [x] 5.1 `pnpm contract:generate` — `contract.generated.ts` z nowym polem; `contract:check` przechodzi
- [x] 5.2 Wiersz trwającego dociągnięcia pokazuje czas od ostatniej aktywności obok postępu i liczby świec
- [x] 5.3 Próg bezczynności jako jedna nazwana stała (5 minut); wiersz powyżej progu wyróżniony tak, by odróżniał się od takiego, w którym praca postępuje
- [x] 5.4 Wiersz dociągnięcia otwiera dialog zlecenia — kliknięciem i z klawiatury; wpis o skasowaniu nie otwiera niczego
- [x] 5.5 Dialog zlecenia składany z wierszy, które zakładka już ma (filtr po `jobId`), bez dodatkowego żądania; odświeża się razem z zakładką co 10 s
- [x] 5.6 Dialog wymienia wszystkie pary zlecenia z ich stanem, postępem i liczbą świec, przyczyny porażek oraz moment ostatniej aktywności zlecenia
- [x] 5.7 Ponowienie wywoływane z dialogu, nazwane ponowieniem zlecenia, ze zdaniem mówiącym, ile kawałków w ilu parach obejmie
- [x] 5.8 Przycisk `Retry` znika z wiersza pary; potwierdzenie wierszem tabeli usunięte z `CollectionHistoryView.tsx`
- [x] 5.9 Test: zlecenie stojące dłużej niż próg jest wyróżnione, a czas od ostatniej aktywności widać bez otwierania dialogu
- [x] 5.10 Test: dialog otwarty z wiersza jednej pary wymienia także pary tego zlecenia, których nie ma w widocznym fragmencie listy
- [x] 5.11 Test: nieudane ponowienie zostaje w dialogu, a wiersze zlecenia MUST NOT pokazać się jako trwające
- [x] 5.12 Test: przy wierszu pary nie ma przycisku ponawiającego zlecenie

## 6. terminal — logowanie zaczyna się samo

- [x] 6.1 `main.tsx`: po `initialize()`, a przed `createRoot`, stan `signed-out` przy skonfigurowanej tożsamości wywołuje `signIn()`
- [x] 6.2 Stan `unconfigured` MUST NOT wywoływać logowania — tryb lokalny bez zmian
- [x] 6.3 Znacznik w `sessionStorage` zapisywany **przed** odejściem ze strony; zastany po powrocie bez zalogowania blokuje drugie przekierowanie, a zalogowanie go kasuje
- [x] 6.4 Wskaźnik „signed out" z przyciskiem w `TopBar` zostaje jako droga wyjścia po nieudanym automacie
- [x] 6.5 Test: skonfigurowana tożsamość i brak zalogowania → `signIn()` wywołane raz
- [x] 6.6 Test: powrót bez zalogowania ze znacznikiem w `sessionStorage` → `signIn()` nie jest wywołane, terminal renderuje się jako niezalogowany
- [x] 6.7 Test: `unconfigured` → `signIn()` nie jest wywołane ani razu

## 7. Domknięcie

- [x] 7.1 `market-data`: `ruff`, `pytest`
- [x] 7.2 `terminal`: `lint`, `typecheck`, `test`
- [x] 7.3 README modułów, jeśli opisują pętlę roboczą, układ `Data History` albo sposób logowania
- [x] 7.4 `openspec validate operator-knows-what-is-happening --strict`
- [x] 7.5 `review.md` po wykonaniu — warunek zamknięcia zmiany
