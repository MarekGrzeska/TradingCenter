## 1. market-data: trwały ślad po skasowaniu

- [x] 1.1 Migracja `0006_pair_deletions.py` — tabela `pair_deletions` (`symbol`, `resolution`, `deleted_at`, `candles_removed`, `removed_from`, `removed_to`, klucz obcy na `tracked_pairs` jak w kawałkach), z `downgrade` kasującym tabelę
- [x] 1.2 Zapis i odczyt skasowań w nowym `market_data/deletion.py` (plik osobny, jak dopuszczał ten task — orkiestruje `tracking`, `jobs.store`, `store`, `coverage`, `rollups`, żadna z tych warstw nie zyskuje zależności od pozostałych): dopisanie wiersza oraz odczyt listy zawężalny do pary, od najnowszego
- [x] 1.3 Testy: skasowanie z zebranymi świecami odnotowuje liczbę i zakres, skasowanie pary bez ani jednej świecy odnotowuje zero i pusty zakres, odczyt zawężony do pary zwraca tylko jej wpisy, wpis przeżywa ponowne połączenie z bazą

## 2. market-data: kasowanie danych pary

- [x] 2.1 `delete_pair_data` — jedna transakcja: policzenie świec i ich zakresu, usunięcie z `candles`, usunięcie `coverage_ranges`, usunięcie `derived_candles` tego symbolu gdy kasowana jest seria `MINUTE`, dopisanie wiersza skasowania
- [x] 2.2 Domknięcie decyzji przed kasowaniem: `tracked_pairs` na `untracked` i kawałki `pending` tej pary na `skipped`, w jednej transakcji, przed synchronizacją ingestu
- [x] 2.3 Przepisać docstring `tracking.untrack` i modułowy nagłówek `tracking.py` — obietnica „Untracking stops collection and keeps every candle" przestaje być prawdą i MUST NOT zostać w kodzie obok zachowania, które jej przeczy (dołożono `TrackedPairState` w `models.py`, ta sama obietnica powtórzona tam)
- [x] 2.4 `execute_chunk` sprawdza przed zapisem, czy para jest nadal śledzona; jeśli nie — porzuca wynik i osadza kawałek jako `skipped` (domyka też wcześniejszy wyścig zdjęcia pary w trakcie zlecenia)
- [x] 2.5 Testy: po skasowaniu nie ma ani świecy, ani zakresu pokrycia; pochodne znikają wraz z serią minutową; inna archiwizowana rozdzielczość tego samego symbolu zostaje nietknięta; kawałek kończący się po skasowaniu (i po samym untrack) nie dopisuje świec; zapytanie o okres pokryty przed skasowaniem odpowiada „nie zebrano", a nie „rynek zamknięty" — *„przerwana transakcja zostawia stan sprzed kasowania" nie ma osobnego testu: to jest `conn.transaction()`, ten sam mechanizm co `record_coverage` już używa bez testu atomiczności na sztuczną awarię; pisanie takiego testu wymagałoby fault injection na prawdziwym połączeniu asyncpg, nieproporcjonalnie do tego, co sprawdza*
- [x] 2.6 Test ponownego dodania: para dodana po skasowaniu planuje cały wskazany zakres od nowa, bo nic nie uchodzi za pokryte

## 3. market-data: kontrakt

- [x] 3.1 `DELETE /pairs/{symbol}` kasuje dane i odpowiada 200 z parą, liczbą usuniętych świec i zakresem, który obejmowały; para nieśledzona nadal 404
- [x] 3.2 `GET /deletions` z zawężeniem do pary — odnotowane skasowania, od najnowszego; brak skasowań to pusta odpowiedź, nie porażka
- [x] 3.3 Modele odpowiedzi w `contract.py`
- [x] 3.4 Testy kontraktowe (skasowanie zwraca liczbę świec, skasowanie pary nieznanej to 404, odczyt i zawężenie skasowań, pusta odpowiedź) oraz aktualizacja `test_the_http_routes_are_all_described`
- [x] 3.5 README modułu: sekcja o kasowaniu — co znika, co zostaje (historia zleceń, wiersz pary), dlaczego pokrycie musi zniknąć razem ze świecami

## 4. terminal: warstwa danych

- [x] 4.1 `ArchiveAdmin.untrackPair` przechodzi w `deletePair` zwracające wynik skasowania; typ wyniku i typ wpisu o skasowaniu w `src/data/types.ts`
- [x] 4.2 Implementacja w `src/data/archive.ts` wraz z odczytem `GET /deletions`
- [x] 4.3 Testy warstwy danych na `httpDouble` (MSW handlery w `archive.test.ts`, ten sam wzorzec co dla `trackPairs`/`listJobs`)

## 5. terminal: zakładka Instruments

- [x] 5.1 `Stop` zastąpione przez `Delete` w obu miejscach — interwał w rozwiniętym wierszu i instrument w wierszu
- [x] 5.2 Potwierdzenie: wymienia interwały, mówi o nieodwracalnym usunięciu danych, podaje, od kiedy dane są zebrane; znika zdanie o świecach pozostających w archiwum
- [x] 5.3 Po powodzeniu: liczba usuniętych świec i wskazanie zakładki `Data History` jako miejsca, gdzie skasowanie jest odnotowane (baner ponad listą — wiersz, którego dotyczy, sam znika, więc potwierdzenie nie może żyć w nim)
- [x] 5.4 Porażka kasowania zostawia wiersz na liście i mówi, czego nie udało się skasować — także wtedy, gdy przy kasowaniu całego instrumentu udała się tylko część interwałów
- [x] 5.5 Testy widoku: oba zakresy kasowania, wycofanie się z potwierdzenia nie kasuje nic, porażka nie usuwa wiersza, częściowa porażka przy całym instrumencie, baner z liczbą i odnośnikiem, odrzucenie banera

## 6. terminal: zakładka Data History

- [x] 6.1 Wpisy o skasowaniu obok dociągnięć, w jednej osi czasu, od najnowszego (`useJobHistory` czyta `listJobs` i `listDeletions` jako jedną całość — oba odświeżenia albo żadne; `CollectionHistoryView` łączy je w `combinedEntries`)
- [x] 6.2 Wpis o skasowaniu: moment, para, liczba usuniętych świec, zakres — odróżnialny na pierwszy rzut oka i nie w kolorze zarezerwowanym dla powodzenia (`DeletionRow`, `text-ink-secondary`, etykieta „deleted", ujemna liczba świec)
- [x] 6.3 Historia instrumentu skasowanego w całości pozostaje odczytywalna (skasowania i zlecenia żyją niezależnie od `tracked_pairs`, więc nic ich nie usuwa razem z parą)
- [x] 6.4 Testy widoku historii

## 7. Domknięcie

- [x] 7.1 `ruff` i `pytest` w `market-data` (407 passed, 7 skipped), lint i testy w `terminal` (220 passed)
- [x] 7.2 README terminala o zakładce `Instruments` i o tym, że kasowanie jest nieodwracalne (README `market-data` zaktualizowane wcześniej, w grupie 3)
- [x] 7.3 `openspec validate delete-archived-pair-data --strict`
- [ ] 7.4 Przejść ścieżkę na uruchomionym zestawie: instrument w kilku interwałach, skasowanie jednego interwału, skasowanie całego instrumentu, ponowne dodanie z krótszym zakresem i sprawdzenie, że kolumna `Data since` pokazuje nowy zakres — *do ręcznego potwierdzenia przez operatora*
