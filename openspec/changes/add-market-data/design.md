## Context

Motywacja jest w `proposal.md`. Tutaj tylko ograniczenia, które kształtują rozwiązanie — wszystkie
wynikają z tego, co już istnieje:

- **Gateway jest jedynymi drzwiami do providera.** `rategate.py` mówi wprost, że capital.com liczy
  limit dziesięciu żądań na sekundę per konto, więc drugi klient w innym procesie to drugi budżet
  i złamany limit. `market-data` MUST NOT łączyć się z capital.com bezpośrednio — traci się wtedy
  i limit, i blokadę demo z `config.py`.
- **Gateway trzyma jedno połączenie do providera na parę (symbol, rozdzielczość)**, a `hub.py`
  odnotowuje, że provider ogranicza liczbę sesji. Liczba śledzonych par ma więc twardy sufit.
- **Gateway sam stronicuje poza limit tysiąca świec** i mierzy koszt tego odczytu. Powielanie tej
  logiki byłoby drugą implementacją tego samego.
- **Świeca w budowie jest składana przez gateway z kwotowań**, bo provider raportuje świecę dopiero
  przy zamknięciu. `forming.py` świadomie pomija `DAY` i `WEEK`, bo ich granica zależy od sesji
  rynku, nie od zegara.
- **Strona ceny to bid**, wszędzie, żeby szew historii ze strumieniem był ciągły.
- **Terminal ma już gniazdo na drugie źródło** — `MarketDataSource` w `modules/terminal/src/data/`.

Rozeznanie kosztów i miejsca uruchomienia jest w `docs/azure-infrastructure-proposal.html`
i `docs/azure-postgres-cost-research.html`.

## Goals / Non-Goals

**Goals:**

- Świeca zamknięta raz zapisana przeżywa restarty modułu, providera i przeglądarki.
- Wykres przestaje zszywać historię z danymi na żywo — dostaje serię i zmiany.
- Operator widzi i zmienia z terminala, co jest zbierane, bez pliku konfiguracyjnego i bez restartu.
- Archiwum wie, czego mu brakuje, i nie odpytuje providera w kółko o zamknięty weekend.

**Non-Goals:**

- Zdejmowanie sufitu na liczbę śledzonych par. Subskrypcja zbiorcza w gatewayu to osobna zmiana.
- Przechowywanie kwotowań. To dwa–trzy rzędy wielkości więcej danych, a nic dziś tego nie potrzebuje.
- Uwierzytelnianie w gatewayu. Potrzebne przed wystawieniem czegokolwiek poza `localhost`, ale jest
  osobną zmianą dotykającą `capital-session`.
- Infrastruktura i wdrożenie. Opisane w dokumentach, wdrażane osobną zmianą.

## Decisions

### Archiwum jest dla terminala jedynym źródłem świec i strumienia

Alternatywa: `market-data` serwuje tylko historię, a terminal dalej subskrybuje gateway i sam zszywa.

Odrzucona, bo zostawia najtrudniejszy fragment w przeglądarce. Między zakończeniem odczytu historii
a pierwszą wiadomością strumienia jest okno, w którym świeca może uciec — i to z niego wynika
dzisiejszy wymóg „po wznowieniu terminal MUST domknąć lukę". Skoro `market-data` i tak trzyma
otwarty strumień dla ingestu i ma bazę pod ręką, może zszyć ten szew raz, po swojej stronie:
snapshot jest czytany w tej samej transakcji, w której subskrybent dopina się do rozgłaszania, więc
z definicji nie ma ani luki, ani duplikatu.

Handel i katalog instrumentów zostają w gatewayu. Archiwum nie udaje właściciela rzeczy, których
nie posiada.

### Baza to PostgreSQL bez TimescaleDB

Alternatywy: TimescaleDB, ClickHouse, QuestDB, DuckDB.

Rozstrzygnięte w `docs/cloud-cost-comparison.html` i `docs/azure-postgres-cost-research.html`.
Krótko: świecę trzeba **nadpisywać**, gdy provider przyśle wartość autorytatywną, a to jest
najsłabsze miejsce baz analitycznych i jedna klauzula `ON CONFLICT` w Postgresie. Wolumen — rzędu
sześciu gigabajtów rocznie przy stu instrumentach — jest trzy rzędy wielkości poniżej progu, przy
którym wyspecjalizowana baza zaczyna cokolwiek dawać.

TimescaleDB odpada dodatkowo z powodu, którego nie widać z zewnątrz: **Azure udostępnia wyłącznie
edycję Apache-2**, czyli bez kompresji i bez continuous aggregates. Te dwie funkcje były jedynym
argumentem za nim.

### Rozdzielczości pochodne z widoków materializowanych

Skoro nie ma continuous aggregates, rollupy `MINUTE_5` … `HOUR_4` powstają jako widoki
materializowane odświeżane przyrostowo po zamknięciu okresu. Kilkadziesiąt linii SQL zamiast
polityki.

`DAY` i `WEEK` pochodzą z providera. Wyliczanie ich z serii minutowej dałoby świecę, która wygląda
poprawnie i jest błędna — to samo rozstrzygnięcie, które podjął już `forming.py`.

**Do zweryfikowania, nie do założenia:** czy provider kotwiczy `HOUR_4` na północy UTC. Przed
zaufaniem derywacji trzeba wyliczyć próbkę i porównać ją ze świecami od providera. Jest to zadanie
w `tasks.md`, nie przypis.

### Śledzone pary są jawną decyzją operatora, podejmowaną w terminalu

Alternatywy: lista w konfiguracji; automatyczne dopisywanie przy pierwszym wyświetleniu wykresu.

Odrzucone obie. Konfiguracja w pliku wymaga dostępu do maszyny i restartu. Automatyczne dopisywanie
zamienia obejrzenie wykresu w zobowiązanie utrzymywania połączenia do providera na okrągło — a
połączenia są zasobem limitowanym. Skoro liczba par ma twardy sufit, jego zużycie MUST być
decyzją, a nie efektem ubocznym.

Stąd panel w terminalu jako osobna zdolność i pełne zarządzanie parami w kontrakcie modułu.

### Zakresy pokrycia zamiast wnioskowania z braków

Brak świecy o trzeciej w nocy w sobotę i brak świecy, bo ingest nie działał, są w danych
nierozróżnialne. Bez zapisanych zakresów pokrycia moduł do końca świata odpytywałby providera
o ten sam weekend. Lewa granica pokrycia bierze się z sygnału `history_ended`, który gateway już
publikuje w `CandleHistory` — grzechem byłoby go wyrzucić.

### Świeca w budowie żyje w pamięci, nie w bazie

Zapisywanie jej przy każdym kwotowaniu to około trzystu zapisów na minutę na instrument zamiast
jednego, a po restarcie zostawiałoby w archiwum świecę zaniżoną, nieodróżnialną od prawdziwej.
Konsument dostaje ją w snapshocie i w zmianach, ale utrwalana jest dopiero wersja zamknięta.

### Terminal składa jedno źródło z dwóch

`MarketDataSource` zostaje jednym interfejsem z jedną instancją, ale instancja jest złożeniem:
świece i strumień z archiwum, instrumenty z gatewaya. Złożenie żyje w `marketData.ts`, więc wykres,
siatka i wyszukiwarka nie zmieniają się wcale.

## Risks / Trade-offs

- **Sufit na liczbę par jest przyjęty, nie usunięty** → limit jest konfigurowalny, a przekroczenie
  kończy się jawną odmową z podaniem powodu. Nie ma cichej degradacji.
- **Archiwum staje się na ścieżce krytycznej wykresu** → gdy jest nieosiągalne, wykres mówi o tym
  wprost, a wyszukiwarka instrumentów działa dalej, bo idzie do gatewaya. Terminal nie gaśnie
  w całości.
- **Głębokie uzupełnianie może zagłodzić ruch interaktywny**, bo dzieli budżet dziesięciu żądań na
  sekundę → ograniczona równoległość uzupełnień, a odczyty operatora idą z archiwum i nie czekają
  na ich zakończenie.
- **Pierwszy moduł ze stanem trwałym** → dochodzą migracje i kopie zapasowe, których repozytorium
  dotąd nie miało. Odtworzenie trzech lat historii dla stu instrumentów z providera to około
  dwudziestu siedmiu godzin, więc kopie zapasowe są warunkiem, nie dobrą praktyką.
- **Derywacja rozdzielczości może nie trafić w granice providera** → zadanie weryfikacyjne przed
  zaufaniem wynikom; przy rozbieżności pozostaje pobieranie tych rozdzielczości wprost.

## Migration Plan

Nic nie migruje — moduł powstaje od zera, a `capital-gateway` nie zmienia zachowania. Terminal
przełącza się na archiwum dla świec i strumienia; wycofanie zmiany to przywrócenie poprzedniej
implementacji źródła, bo interfejs pozostaje ten sam.

**Ograniczenie na czas implementacji:** faza `apply` MUST NOT uruchamiać masowego zbierania danych.
Ingest wolno uruchamiać wyłącznie w zakresie potrzebnym do testów, na pojedynczych parach i płytkiej
historii. O tym, co i w jakich rozdzielczościach jest faktycznie archiwizowane, decyduje operator
z panelu — po wdrożeniu, nie w trakcie budowy.

## Open Questions

- Domyślna głębokość uzupełniania dla nowo dodanej pary. Wartość konfigurowalna, więc nie blokuje
  ani specyfikacji, ani podziału zadań — do ustalenia przy pierwszym realnym użyciu.
- Czy panel ma pozwalać wymusić ponowne uzupełnienie wskazanego przedziału. Przydatne przy
  podejrzeniu dziury, ale nie jest potrzebne, żeby archiwum działało.
