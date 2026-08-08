## 1. market-data: trwały ślad po skasowaniu

- [ ] 1.1 Migracja `0006_pair_deletions.py` — tabela `pair_deletions` (`symbol`, `resolution`, `deleted_at`, `candles_removed`, `removed_from`, `removed_to`, klucz obcy na `tracked_pairs` jak w kawałkach), z `downgrade` kasującym tabelę
- [ ] 1.2 Zapis i odczyt skasowań w `market_data/tracking.py` (albo obok, jeśli plik urośnie zanadto): dopisanie wiersza oraz odczyt listy zawężalny do pary, od najnowszego
- [ ] 1.3 Testy: skasowanie z zebranymi świecami odnotowuje liczbę i zakres, skasowanie pary bez ani jednej świecy odnotowuje zero i pusty zakres, odczyt zawężony do pary zwraca tylko jej wpisy, wpis przeżywa ponowne połączenie z bazą

## 2. market-data: kasowanie danych pary

- [ ] 2.1 `delete_pair_data` — jedna transakcja: policzenie świec i ich zakresu, usunięcie z `candles`, usunięcie `coverage_ranges`, usunięcie `derived_candles` tego symbolu gdy kasowana jest seria `MINUTE`, dopisanie wiersza skasowania
- [ ] 2.2 Domknięcie decyzji przed kasowaniem: `tracked_pairs` na `untracked` i kawałki `pending` tej pary na `skipped`, w jednej transakcji, przed synchronizacją ingestu
- [ ] 2.3 Przepisać docstring `tracking.untrack` i modułowy nagłówek `tracking.py` — obietnica „Untracking stops collection and keeps every candle" przestaje być prawdą i MUST NOT zostać w kodzie obok zachowania, które jej przeczy
- [ ] 2.4 `execute_chunk` sprawdza przed zapisem, czy para jest nadal śledzona; jeśli nie — porzuca wynik i osadza kawałek jako `skipped` (domyka też wcześniejszy wyścig zdjęcia pary w trakcie zlecenia)
- [ ] 2.5 Testy: po skasowaniu nie ma ani świecy, ani zakresu pokrycia; pochodne znikają wraz z serią minutową; inna archiwizowana rozdzielczość tego samego symbolu zostaje nietknięta; przerwana transakcja zostawia stan sprzed kasowania; kawałek kończący się po skasowaniu nie dopisuje świec; zapytanie o okres pokryty przed skasowaniem odpowiada „nie zebrano", a nie „rynek zamknięty"
- [ ] 2.6 Test ponownego dodania: para dodana po skasowaniu planuje cały wskazany zakres od nowa, bo nic nie uchodzi za pokryte

## 3. market-data: kontrakt

- [ ] 3.1 `DELETE /pairs/{symbol}` kasuje dane i odpowiada 200 z parą, liczbą usuniętych świec i zakresem, który obejmowały; para nieśledzona nadal 404
- [ ] 3.2 `GET /deletions` z zawężeniem do pary — odnotowane skasowania, od najnowszego; brak skasowań to pusta odpowiedź, nie porażka
- [ ] 3.3 Modele odpowiedzi w `contract.py`
- [ ] 3.4 Testy kontraktowe (skasowanie zwraca liczbę świec, skasowanie pary nieznanej to 404, odczyt i zawężenie skasowań, pusta odpowiedź) oraz aktualizacja `test_the_http_routes_are_all_described`
- [ ] 3.5 README modułu: sekcja o kasowaniu — co znika, co zostaje (historia zleceń, wiersz pary), dlaczego pokrycie musi zniknąć razem ze świecami

## 4. terminal: warstwa danych

- [ ] 4.1 `ArchiveAdmin.untrackPair` przechodzi w `deletePair` zwracające wynik skasowania; typ wyniku i typ wpisu o skasowaniu w `src/data/types.ts`
- [ ] 4.2 Implementacja w `src/data/archive.ts` wraz z odczytem `GET /deletions`
- [ ] 4.3 Testy warstwy danych na `httpDouble`

## 5. terminal: zakładka Instruments

- [ ] 5.1 `Stop` zastąpione przez `Delete` w obu miejscach — interwał w rozwiniętym wierszu i instrument w wierszu
- [ ] 5.2 Potwierdzenie: wymienia interwały, mówi o nieodwracalnym usunięciu danych, podaje, od kiedy dane są zebrane; znika zdanie o świecach pozostających w archiwum
- [ ] 5.3 Po powodzeniu: liczba usuniętych świec i wskazanie zakładki `Data History` jako miejsca, gdzie skasowanie jest odnotowane
- [ ] 5.4 Porażka kasowania zostawia wiersz na liście i mówi, czego nie udało się skasować — także wtedy, gdy przy kasowaniu całego instrumentu udała się tylko część interwałów
- [ ] 5.5 Testy widoku: oba zakresy kasowania, wycofanie się z potwierdzenia nie kasuje nic, porażka nie usuwa wiersza, częściowa porażka przy całym instrumencie

## 6. terminal: zakładka Data History

- [ ] 6.1 Wpisy o skasowaniu obok dociągnięć, w jednej osi czasu, od najnowszego
- [ ] 6.2 Wpis o skasowaniu: moment, para, liczba usuniętych świec, zakres — odróżnialny na pierwszy rzut oka i nie w kolorze zarezerwowanym dla powodzenia
- [ ] 6.3 Historia instrumentu skasowanego w całości pozostaje odczytywalna
- [ ] 6.4 Testy widoku historii

## 7. Domknięcie

- [ ] 7.1 `ruff` i `pytest` w `market-data`, lint i testy w `terminal`
- [ ] 7.2 README terminala o zakładce `Instruments` i o tym, że kasowanie jest nieodwracalne
- [ ] 7.3 `openspec validate delete-archived-pair-data --strict`
- [ ] 7.4 Przejść ścieżkę na uruchomionym zestawie: instrument w kilku interwałach, skasowanie jednego interwału, skasowanie całego instrumentu, ponowne dodanie z krótszym zakresem i sprawdzenie, że kolumna `Data since` pokazuje nowy zakres — *do ręcznego potwierdzenia przez operatora*
