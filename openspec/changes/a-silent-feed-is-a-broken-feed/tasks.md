## 1. capital-gateway — cisza jest zerwaniem

- [x] 1.1 W `stream/upstream.py` zamienić odczyt sesji na odczyt z terminem końcowym: brak
      **danych** przez próg kończy sesję tą samą drogą co wyjątek (status, ponowne połączenie)
- [x] 1.2 Dodać eskalację tolerancji ciszy: start 120 s, podwojenie po każdym wznowieniu, które
      znowu nic nie przyniosło, sufit 10 minut, zerowanie na pierwszej wiadomości
- [x] 1.3 Testy na sztucznym transporcie i sztucznym zegarze: milczący socket zostaje zerwany
      i wznowiony; wiadomość przed progiem nie zrywa niczego; tolerancja rośnie i wraca do 120 s

## 2. capital-gateway — granica okresu bez kwotowania

- [x] 2.1 W `stream/hub.py` dać pokojowi własny zegar obok kwotowania: pokój bez granicy pyta
      o nią sam, a oba wejścia do odczytu są pod jednym zamkiem
- [x] 2.2 Nałożyć eskalację na `BOUNDARY_RETRY_SECONDS` (30 s → 10 minut), gdy provider wciąż
      nie ma okresu do zbudowania
- [x] 2.3 Testy: pokój `DAY` bez kwotowań ustala granicę i publikuje świecę w budowie; odstęp
      między pytaniami rośnie, gdy provider odpowiada „jeszcze nie"

## 3. capital-gateway — okres, który na pewno minął

- [x] 3.1 W `stream/forming.py` dodać mapę nominalnej długości okresu (z `DAY` i `WEEK`), osobną
      od `BUCKET_SECONDS` i nazwaną tak, żeby nie dało się jej pomylić z granicą do podłogowania
- [x] 3.2 `on_quote` dla rozdzielczości bez stałej granicy odmawia rozciągnięcia świecy starszej
      niż cała długość jej okresu i wchodzi w stan „okres zamknięty"
- [x] 3.3 Testy: kwotowanie z następnego tygodnia nie dokleja się do świecy sprzed tygodnia;
      `DAY` i `WEEK` nadal nie mają arytmetycznej granicy okresu

## 4. market-data — druga linia obrony

- [x] 4.1 W `gateway/stream.py` nałożyć termin odbioru (20 minut, liczony od dowolnej wiadomości)
      kończący iterację tak samo jak zamknięcie połączenia
- [x] 4.2 Test na prawdziwym gnieździe: subskrypcja, przez którą nic nie przyszło, kończy się.
      Że koniec subskrypcji domyka lukę i subskrybuje ponownie, trzyma już
      `test_a_resumed_subscription_closes_the_gap_it_left` — reguła testowana raz, w swojej warstwie

## 5. Domknięcie

- [x] 5.1 Dopisać do `modules/capital-gateway/README.md` — sekcja o strumieniu — czym jest cisza
      i skąd wzięły się progi
- [x] 5.2 `uv run pytest` · `ruff check .` · `pyright` w obu modułach
