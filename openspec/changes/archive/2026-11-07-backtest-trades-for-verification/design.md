## Context

`GET /runs/{id}/trades` oddaje stronę transakcji (do 1000 na odpowiedź, terminal bierze po 200) jako `TradesPageOut` z
pełnym modelem `TradeOut`. `read_backtest` świadomie nie oddaje listy: raport o kilku tysiącach transakcji wypełniłby
kontekst agenta przy każdym odczycie metryk. Terminal woła wszystkie trasy pakietu przez klienta z tożsamością operatora,
więc plik nie może być zwykłym linkiem `<a href>`: żądanie musi nieść token.

## Goals / Non-Goals

**Goals:** transakcje do ręcznej i agentowej weryfikacji reguł; plik do arkusza bez limitu strony.

**Non-Goals:** policzone sprawdzenia („wszystkie wyjścia przed końcem sesji”) jako osobne narzędzie lub kolumna — agent
i operator dostają dane, a reguły sprawdzają sami. Eksport krzywej kapitału. Inne formaty niż CSV.

## Decisions

**D1. Osobne narzędzie, stronicowane, zamiast listy w `read_backtest`.** `read_backtest_trades(run_id, offset, limit)`
z sufitem 100 i domyślnym 50. Agent sprawdzający regułę przechodzi strony, a każda odpowiedź to osobny, widoczny w
rozmowie krok (około 35 tys. znaków przy 100 transakcjach). `read_backtest` nie rośnie.
*Alternatywy:* (a) lista w `read_backtest`: każdy odczyt raportu ładuje kontekst, nawet gdy agent pyta o metryki;
(b) narzędzie sprawdzające reguły: każda nowa reguła to nowy kod, a model i tak musi móc obejrzeć przypadek, który
reguła wskazała.

**D2. Narzędzie i trasa JSON dzielą jedną funkcję czytającą, CSV ma własny formatter.** `runs.trades_page` czyta już
wiersze; narzędzie zwraca je w modelu `TradeOut` z kontraktu (jedno źródło kształtu), a CSV buduje wiersze w
`trades_csv.py`, gdzie siedzą kolumny, strefa i puste pola. Dzięki temu test kolumn nie dotyka bazy.

**D3. CSV jako strumień po stronach po 1000, w jednym `StreamingResponse`.** Generator czyta `trades_page` kolejnymi
stronami (każda w krótkim `acquire`, bez trzymania połączenia przez czas pobierania) i zwraca fragmenty tekstu. Pamięć
jest ograniczona stroną, nie liczbą transakcji, a uruchomienie na minutach z dziesiątkami tysięcy transakcji pobiera
się tak samo jak to z 54.
*Alternatywa:* zbudować cały plik w pamięci. Odrzucona: ograniczona liczba transakcji to tylko limit liczby świec, który
dopuszcza pliki rzędu dziesiątek megabajtów.

**D4. Format: UTF-8 z BOM, przecinek, kropka, ISO 8601 z przesunięciem, pusty ciąg dla braku.** To format, który czytają
Arkusze Google, pandas i agent bez konfiguracji; polski Excel otwiera go przez „Dane → Z tekstu/CSV”, a BOM sprawia,
że polskie znaki w przyczynach wyjścia nie rozjeżdżają się. Czas wejścia i wyjścia w dwóch kolumnach każdy: UTC (do
porównań z danymi i agentem) i `Europe/Warsaw` (do czytania przez operatora; zmiana czasu jest w przesunięciu).
*Alternatywa:* średnik i przecinek dziesiętny dla Excela PL. Odrzucona: psuje wszystko poza Excelem, a przy
pobraniu przez przeglądarkę nie ma jak zgadnąć ustawień regionalnych.

**D5. Pobranie z terminala przez klienta z tożsamością, plik składany po stronie przeglądarki.** `downloadTrades(runId)`
woła trasę przez `http.send`, odbiera `Blob` i zapisuje go przez tymczasowy link. Nazwę pliku z numerem uruchomienia
terminal składa sam (`run-N-trades.csv`): `Content-Disposition` nie jest czytelny dla przeglądarki bez wystawienia go w
CORS, a nazwa nie niesie niczego, czego terminal nie wie.
*Alternatywa:* link z tokenem w adresie. Odrzucona: token w URL trafia do logów i historii.

**D6. Trasa bez modelu odpowiedzi, ale z opisem typu w OpenAPI.** `responses={200: {"content": {"text/csv": {}}}}`
zostawia kontrakt wygenerowany dla terminala z samą ścieżką, tak jak dla innych tras bez ciała JSON. Nowa ścieżka
wchodzi na listę tras w `caller_access.REST_PATHS`; test, który porównuje listę z opublikowanym dokumentem, pilnuje, żeby
nie została poza rejestrem wołających.

## Risks / Trade-offs

- [Agent czyta dziesiątki stron i zapełnia kontekst.] → Sufit 100, domyślnie 50, a opis mówi, że to strona; przejście
  stron nie jest próbą i niczego nie liczy, więc nie ma kosztu poza kontekstem. Jeśli się to okaże kłopotem, następna
  zmiana to narzędzie liczące reguły (nie cel tej).
- [Transakcje starszych uruchomień mają puste `result_pct` i `mae_pct`.] → Tak jak w liście raportu: puste pole, nie zero
  (`strategies-reports`).
- [Pobranie wielkiego pliku trzyma połączenie klienta, nie bazy.] → D3: strona jest czytana i oddawana, a połączenie wraca
  do puli między stronami.

## Migration Plan

Bez migracji. Trasa i narzędzie są addytywne; wycofanie obrazu je usuwa i niczego nie zostawia w danych.
