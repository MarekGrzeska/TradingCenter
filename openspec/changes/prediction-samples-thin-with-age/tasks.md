## 1. Schemat

- [x] 1.1 Migracja `polymarket` 0008: `outcomes.thinned_through timestamptz` — granica, przed którą próbki wyniku są godzinowe

## 2. Magazyn

- [x] 2.1 `store.thin_samples(conn, outcome_id, start, end)`: z każdej godziny UTC w `[start, end)` zostaje ostatnia próbka, reszta usunięta; zwraca liczbę usuniętych
- [x] 2.2 `store.outcomes_to_thin`, `store.oldest_sample_at`, `store.note_thinned` — co przebieg ma zrobić i gdzie skończył
- [x] 2.3 `store.unthin_from(conn, outcome_id, moment)`: backfill starszy niż granica cofa ją do swojej godziny
- [x] 2.4 Testy `db`: godzina zostawia ostatnią próbkę, świeże próbki i `collected_ranges` nietknięte, granica cofa się tylko w tył

## 3. Pętla

- [x] 3.1 `Ingest.thin()`: wyniki po kolei, porcje po 7 dni, przerwa między porcjami, pod semaforem połączeń próbkowania
- [x] 3.2 Uruchamiany z pętli próbkowania raz na dobę (pierwszy raz po starcie), jako zadanie obok ticku, anulowane z modułem
- [x] 3.3 `_fill_window` cofa granicę, gdy zapisał próbki starsze niż ona
- [x] 3.4 Test `db` przebiegu: stare minutowe → godzinowe, granica zapisana, drugi przebieg nic nie usuwa

## 4. Odczyt i kontrakt

- [x] 4.1 `GET /outcomes/{id}/history` i narzędzie `get_price_history` zwracają `hourly_until`
- [x] 4.2 `contract-sync`: kontrakty terminala i pocketa
- [x] 4.3 README `polymarket_data`: retencja jako zapisana decyzja

## 5. Po wdrożeniu (operatora i pomiar)

- [ ] 5.1 Po pierwszym przebiegu: liczba wierszy i rozmiar `price_samples`, kredyty CPU bazy w czasie przebiegu
