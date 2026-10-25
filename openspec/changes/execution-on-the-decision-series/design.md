## Context

`engine.simulate` przechodzi po świecach decyzji, a między dwiema decyzjami odtwarza każdą minutę (`_minute`): tam
wypełniają się zlecenia, wyjścia z `when` i `max_bars`, stopy, cele, trailing i podłoga kapitału (`out_of_capital`).
Minuty, których nie ma, są po prostu pomijane, więc zlecenie czeka na pierwszą istniejącą minutę bez względu na to, ile
świec decyzji minęło. `reports.daily_equity` i `buy_and_hold` też wyceniają na minutach. Limit `max_minute_bars`
(1 500 000) jest liczony z długości zakresu, zanim cokolwiek zostanie przeczytane.

## Goals / Non-Goals

**Goals:** strategia bez poziomów nie zależy od minut; strategia z poziomami nie liczy się po cichu nad dziurą w
minutach.

**Non-Goals:** stopy i cele rozstrzygane na świecy decyzji (niejasna świeca na niekorzyść strategii). To osobna
decyzja z innym rozkładem wyników; nie ma jej w tej zmianie. Nie zmienia się też archiwum ani to, jak oznacza ono
pokrycie minut.

## Decisions

**D1. Serię wykonania wyznacza dokument, nie żądanie uruchomienia.** Jest to czysta funkcja dokumentu: brak `stop`,
`target` i `trail`, a każde wejście ma `order.type == "market"`. Wtedy wykonanie idzie na serii decyzji, a w każdym innym
przypadku na `MINUTE`.
*Alternatywy:* (a) wybór operatora w żądaniu: dodaje pokrętło, które przy strategii bez poziomów zmienia tylko to, czy
test zadziała, a nie wynik; (b) przejście na serię decyzji tylko tam, gdzie brakuje minut: jeden przebieg na dwóch
seriach, czego raport nie umie opisać jednym słowem.

**D2. Na serii decyzji „następna minuta” to otwarcie następnej świecy decyzji.** Ta sama pętla, inna seria pod spodem:
`_minute` dostaje świecę decyzji zamiast minuty. Otwarcie bid świecy M5 to otwarcie jej pierwszej minuty, a spread jest
brany z godziny jej początku, tak jak dla minuty. Złoty plik dostaje parę: ta sama strategia bez poziomów na zakresie z
pełnymi minutami, raz na każdej serii, z równymi transakcjami (scenariusz „Ta sama strategia na obu seriach”).
*Alternatywa:* osobna, uproszczona pętla dla strategii bez poziomów. Odrzucona, bo podwaja kod, który trzeba trzymać w
zgodzie, a podłoga kapitału i finansowanie musiałyby być napisane drugi raz.

**D3. Brak minut sprawdzany po przeczytaniu danych, przed liczeniem.** Sprawdzenie odbywa się w `queue._prepare`, czyli
tam, gdzie dziś znane są już serie, i kończy uruchomienie niepowodzeniem z przyczyną. Świeca decyzji „bez minut” to
taka, w której przedziale `[start, start + okres)` nie ma żadnej minuty. Pojedyncze brakujące minuty, częste w strumieniu,
nie są dziurą.
*Alternatywa:* odmowa przed zakolejkowaniem, na podstawie `coverage_ranges` archiwum. Odrzucona, bo archiwum oznacza
zakres 19.01–20.08 jako pokryty, a minut w nim nie ma. Prawdę mówią dopiero przeczytane świece.

**D4. Krzywa kapitału i kup-i-trzymaj wyceniają na serii wykonania.** Przy wykonaniu na M5 dzienna wycena bierze
ostatnie zamknięcie M5 przed chwilą wyceny zamiast ostatniego zamknięcia minuty. To ta sama cena z dokładnością do
ostatnich pięciu minut przed północą UTC, a nie wymaga czytania minut tylko dla wykresu.

**D5. Limit zakresu w świecach serii wykonania, a serię podaje serwer.** `check_request` dostaje dokument, liczy
`(to − from) / okres` serii wykonania i porównuje z tym samym limitem. `max_minute_bars` zmienia nazwę na
`max_execution_bars` w ustawieniach i kontrakcie, z tą samą wartością domyślną. Formularz terminala dostaje serię
wykonania z odczytu rewizji (`RevisionOut.execution`) i liczy świece tej serii.
*Alternatywa:* terminal wyznacza serię sam z dokumentu. Odrzucona, bo to druga kopia reguły z D1 w innym języku, która
rozjedzie się przy pierwszym nowym rodzaju zlecenia.

## Risks / Trade-offs

- [Podłoga kapitału na M5 nie widzi luki w środku świecy.] Na minutach minuta, która otwiera się za podłogą, zamyka
  pozycję po swoim otwarciu. Na M5 zamknięcie następuje po podłodze, chyba że za podłogą otwiera się cała świeca. Wynik
  bywa przez to o ułamek lepszy przy pozycji tracącej cały kapitał. → Opisane w README pakietu. Dotyczy tylko
  transakcji `out_of_capital`, które i tak kończą przebieg.
- [MAE z high/low świecy M5 równa się MAE z minut.] Skrajne wartości świecy to skrajne wartości jej minut, więc nie ma
  tu ryzyka; zapisuję to, żeby nikt nie dopisywał testu, który to sprawdza.
- [Stare uruchomienia z wersją silnika 3.] Zostają, jakie były. `compare_runs` i tak odmawia zestawienia różnych wersji
  silnika.

## Migration Plan

Bez migracji schematu: seria wykonania trafia do istniejącej kolumny `provenance` (jsonb). Nowe uruchomienia mają ją
od wdrożenia, a `read_backtest` dla starych podaje `null`.
