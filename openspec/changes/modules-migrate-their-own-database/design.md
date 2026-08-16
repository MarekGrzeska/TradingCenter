## Context

Motywacja jest w `proposal.md` („Why"). Tu liczy się stan zastany, bo to on rozstrzyga
wybory poniżej.

Dziś migrację produkcyjną wykonuje operator ze swojej maszyny, tożsamością administratora
Entra serwera, przez `alembic upgrade head` z katalogu modułu. `Dockerfile` obu modułów
mówi wprost, że kontener nie migruje, a jako powód podaje wyścig dwóch workerów o ten sam
`alembic_version`. `schema_version.py` — bliźniaczy w obu modułach — porównuje głowę
migracji z obrazu z rewizją w bazie i odmawia startu, gdy się różnią.

Trzy fakty z produkcji, które kształtują całą tę zmianę:

1. **Wszystkie obiekty w obu bazach są własnością administratora Entra**, bo to on je
   utworzył. Rola aplikacji dostała `GRANT` na tabele, które istniały w dniu nadania, plus
   `ALTER DEFAULT PRIVILEGES FOR ROLE <administrator>` dodane 15 sierpnia. To działa, ale
   jest przypięte do jednej roli tworzącej.
2. **Firewall serwera wpuszcza IP wychodzące App Service'ów** (`infra/database.tf`,
   `*_outbound`) oraz jedno stałe IP operatora. Runner GitHuba nie jest ani jednym, ani
   drugim.
3. **Smoke check `deploy-agent.yml` czyta control plane**, nie proces. 16 sierpnia
   `az webapp show --query state` odpowiadał `Running` przez cały czas, gdy kontener
   wychodził z kodem 3 w pętli. `deploy-market-data.yml` jest inny — `/ws/candles` jest
   wyłączone spod Easy Auth i probe sięga do procesu.

## Goals / Non-Goals

**Goals:**

- Migracja wykonuje się sama, jako część uruchomienia modułu, i jest bezpieczna przy wielu
  instancjach.
- Grant przestaje być osobnym krokiem — nie przez lepsze pamiętanie o nim, tylko przez
  usunięcie warunku, który go wymagał.
- Nieudana migracja jest widoczna jako czerwone wdrożenie, a nie jako zielone wdrożenie
  z ciemną produkcją.

**Non-Goals:**

- Migracje odwracające się same (`downgrade`). Wycofanie schematu zostaje operacją ręczną
  i przemyślaną — automatyczny `downgrade` przy cofnięciu obrazu kasowałby dane.
- Migracje bezprzestojowe (expand/contract, dwie fazy wdrożenia). Ten system ma jedną
  instancję na moduł i akceptowalny przestój startu; wprowadzanie tu dyscypliny
  dwufazowej byłoby kosztem bez odbiorcy.
- Zarządzanie rolami Postgresa Terraformem.
- `capital-gateway` i `market-mcp` — nie mają własnej bazy, więc nie mają czego migrować.

## Decisions

### 1. Migruje kontener przy starcie, a nie runner CI ani osobny job w Azure

**Wybrane:** migracja w `lifespan` aplikacji, przed wpuszczeniem ruchu.

Wariant z runnerem GitHuba wymaga otwarcia reguły firewalla na IP wyjściowe runnera
i zamknięcia jej w `always()`, a do tego uczynienia principala CI drugim administratorem
Entra bazy. To ostatnie jest podniesieniem uprawnień CI dokładnie tam, gdzie repozytorium
konsekwentnie ich nie daje — `terraform-apply.yml` odmawia planu dotykającego `azuread_*`
właśnie dlatego. Dodatkowo administrator numer dwa oznacza drugą rolę tworzącą obiekty,
czyli drugi komplet `ALTER DEFAULT PRIVILEGES` — wracamy do problemu, który ta zmiana ma
zlikwidować.

Wariant z osobnym jobem w Azure (Container Apps Job na tym samym obrazie) unika obu tych
rzeczy, ale dokłada zasób do utrzymania, własne IP wyjściowe do wpuszczenia przez firewall
i osobną ścieżkę logów. Kupuje za to możliwość migrowania bez restartu aplikacji — czego
ten system nie potrzebuje.

Wariant wybrany nie potrzebuje **niczego nowego**: tożsamość jest ta, którą moduł już ma,
przejście przez firewall jest to, które już działa, a logi są tam, gdzie operator już
patrzy. Wyścig, którym `Dockerfile` uzasadniał odmowę, rozwiązuje decyzja 3.

**Cena:** zła migracja blokuje start modułu. To jest cena zamierzona — patrz decyzja 5.

### 2. Migruje tożsamość aplikacji, nie administratora

Tabela utworzona przez rolę aplikacji należy do niej, więc nie potrzebuje `GRANT`.
To nie jest optymalizacja, tylko usunięcie całej klasy błędu: `permission denied` na
tabeli, która istnieje, czyta się jak brak tabeli i prowadzi śledztwo w złą stronę —
kosztowało to raz (`prompt_revisions`, 15 sierpnia) i kosztowałoby znowu.

**Konsekwencja, którą trzeba wykonać ręcznie i raz:** obiekty, które już istnieją, są
własnością administratora, a `ALTER TABLE` z roli aplikacji na cudzej tabeli odmawia.
Przed pierwszym wdrożeniem operator przenosi własność wszystkich obiektów obu baz —
tabel, sekwencji, widoków i `alembic_version` — na rolę aplikacji i nadaje jej
`CREATE ON SCHEMA public` (PostgreSQL 15 nie daje go już `PUBLIC`). Kroki w „Migration
Plan".

Rozważone i odrzucone: zostawić migracje administratorowi i tylko zautomatyzować ich
uruchomienie. Odrzucone, bo wtedy każda automatyzacja musi nieść poświadczenie
administratora tam, gdzie się wykonuje — a jedyne miejsce, które je ma, to maszyna
operatora, czyli dokładnie to, od czego uciekamy.

### 3. Blokada doradcza sesji, nie transakcji

`pg_advisory_lock(key)` na połączeniu trzymanym przez czas migracji, zwalniana w `finally`.
Klucz stały, wyprowadzony z nazwy modułu, ten sam w obu bliźniakach co do sposobu i różny
co do wartości — dwie bazy logiczne stoją na jednym serwerze, a blokady doradcze są
per baza, więc kolizja i tak jest niemożliwa; różne wartości są po to, żeby log był
czytelny.

Nie `pg_advisory_xact_lock`, bo alembic prowadzi własne transakcje i część migracji może
potrzebować `COMMIT` w środku; blokada związana z transakcją zwolniłaby się wtedy w
połowie roboty.

Nie `LOCK TABLE alembic_version`, bo to blokuje dopiero od chwili, gdy tabela istnieje —
a pierwsze uruchomienie przeciwko pustej bazie jest właśnie tym przypadkiem, w którym
wyścig boli najbardziej.

Czekanie realizuje `pg_try_advisory_lock` w pętli z kresem, a nie blokujący
`pg_advisory_lock`, żeby kres w ogóle dało się nałożyć. Kres: **`agent` 5 minut**,
**`market-data` 25 minut** — druga liczba wynika z tego, że archiwum świec jest największą
bazą w systemie i przebudowa indeksu na tabeli świec trwa dłużej niż start procesu
(`market-data-database-connection`, „Kres MUST być dłuższy niż najdłuższa migracja").

Nie 30 minut, choć taka była pierwsza liczba: App Service tnie
`WEBSITES_CONTAINER_START_TIME_LIMIT` na 1800 s, a przy kresie równym sufitowi platformy
to platforma mogłaby poddać się pierwsza — czyli zrestartować kontener i zacząć tę samą
migrację od nowa, nie mówiąc dlaczego. Moduł musi odmawiać pierwszy, więc jego kres stoi
poniżej sufitu, nie na nim.

### 4. Alembic wołany w procesie, nie jako podproces

`command.upgrade(config, "head")` przez API alembica, uruchomiony w wątku roboczym, żeby
nie blokować pętli zdarzeń. Nie `subprocess`, bo obraz musiałby wtedy nieść `alembic` jako
plik wykonywalny i rozwiązywać ścieżkę `alembic.ini` względem katalogu roboczego, który
App Service ustawia po swojemu — dokładnie ten problem, o który potknęła się dzisiejsza
ręczna migracja i który wymusił kopię `alembic.ini` z bezwzględnymi ścieżkami.

`migrations/env.py` obu modułów już umie zbudować silnik z tożsamości (`_identity_connect_args`),
więc wywołanie w procesie trafia w kod, który jest w tej roli przetestowany.

### 5. `schema_version.verify` zostaje, po migracji

Wygląda na zbędny, skoro migracja właśnie przebiegła. Zostaje z dwóch powodów: łapie
**bazę przed obrazem** (migracja przeszła, ale nie zrobiła tego, co miała) i **bazę za
obrazem** (wdrożono starszy obraz na nowszy schemat) — a to drugie staje się po tej
zmianie *bardziej* prawdopodobne, nie mniej, bo schemat będzie się teraz ruszał sam przy
każdym wdrożeniu. Kod czytający schemat z przyszłości jest tak samo nieprzetestowany jak
czytający z przeszłości.

### 6. Wdrożenie widzi proces, nie control plane

`/health` agenta zostaje wyłączone spod Easy Auth, tym samym wzorem co `/ping`
w `market-data` i `/health` w `market-mcp`. Trasa nic nie czyta i zwraca stałe ciało, więc
nie ma tu czego chronić.

To wystarcza, i to jest ładna własność tej architektury: skoro `lifespan` nie kończy się
przed migracją, to **odpowiedź z procesu jest dowodem, że schemat jest na głowie**. Smoke
check nie musi pytać o rewizję — pytanie „czy odpowiadasz" jest już tym pytaniem.

Odrzucone: czytanie logów kontenera przez Kudu w workflow (kruche, zależne od formatu
linii) oraz trasa `/schema` podająca rewizję (nowa trasa publiczna po to, żeby powiedzieć
to, co i tak wynika z faktu odpowiadania).

## Risks / Trade-offs

- **Zła migracja zatrzymuje moduł, zamiast zepsuć jedną trasę** → to jest wybrane
  zachowanie, nie skutek uboczny (`proposal.md`, decyzja o porażce wdrożenia). Poprzedni
  kontener serwuje dalej, dopóki nowy nie przejdzie probe'a, więc produkcja nie ciemnieje
  — pod warunkiem, że migracja jest **testowana na bazie integracyjnej w CI**, co oba
  moduły już robią przez `pytest -m db`.
- **Migracja dłuższa niż warm-up probe App Service** → probe ma własny limit, niezależny od
  naszego kresu blokady. Długa migracja skończy się „site startup probe failed" mimo
  poprawnego przebiegu. Łagodzenie: `WEBSITES_CONTAINER_START_TIME_LIMIT` podniesione dla
  `market-data` do wartości większej niż jego kres blokady; zadanie w `tasks.md`.
- **Przeniesienie własności wykonane w połowie** → moduł wstanie i zacznie działać, a
  padnie dopiero na pierwszej migracji dotykającej tabeli, której nie przepisano. Łagodzenie:
  krok operatora jest jednym skryptem obejmującym wszystkie obiekty ze schematu, a nie
  listą tabel spisaną z pamięci, i kończy się zapytaniem kontrolnym, które ma zwrócić zero
  wierszy.
- **Rola aplikacji dostaje prawo DDL** → jest to poszerzenie jej uprawnień: rola, która
  dotąd tylko czytała i pisała, może teraz tworzyć i kasować tabele we własnej bazie. Nie
  sięga poza swoją bazę (`agent-database-connection`, „Moduł nie dzieli bazy z innym
  modułem" zostaje w mocy), a alternatywa — trzymanie DDL przy administratorze — jest tym,
  co ta zmiana likwiduje.
- **Dwa moduły, jedna zmiana** → większy promień rażenia niż zrobienie najpierw agenta.
  Łagodzenie: kolejność zadań w `tasks.md` jest taka, że `agent` idzie pierwszy i jest
  wdrażany osobno; `market-data` rusza dopiero, gdy pierwszy przeżył wdrożenie.

## Migration Plan

Kolejność jest częścią zmiany, nie przypisem — kod wdrożony przed krokiem 1 daje moduł,
który nie wstaje.

1. **Operator, raz, na obu bazach produkcyjnych** (`agent` i `market_data` — `tradingcenter`
   to nazwa *serwera*, nie bazy na nim), tożsamością
   administratora Entra: przeniesienie własności wszystkich tabel, sekwencji i widoków
   schematu `public` oraz `alembic_version` na rolę aplikacji, plus
   `GRANT CREATE ON SCHEMA public`. Zapytanie kontrolne wypisujące obiekty, których
   właścicielem nie jest rola aplikacji, MUST zwrócić zero wierszy.
2. Wdrożenie `agent` z migracją przy starcie. Bazy nie trzeba przygotowywać — jest już
   na `0009` po naprawie z 16 sierpnia, więc pierwszy start ma zero migracji do wykonania
   i sprawdza samą ścieżkę, nie jej skutek.
3. Wdrożenie `market-data` po tym, jak `agent` przeżył swoje.

**Rollback:** wycofanie obrazu na poprzedni działa dla schematu, który się nie zmienił —
moduł wstanie, `verify` przejdzie. Obraz wycofany **poniżej** rewizji, którą wdrożenie
zdążyło nałożyć, nie wstanie, i to jest zamierzone (decyzja 5). Wtedy rollback jest
operacją ręczną: `alembic downgrade` do rewizji starego obrazu, świadomie, z decyzją o
danych — i to jest jedyna droga, którą ta zmiana zostawia operatorowi ręczną.

Przywrócenie stanu sprzed zmiany, gdyby okazała się zła: kod migrujący zdejmuje się
jednym wdrożeniem, a własność obiektów nie musi wracać do administratora — `ALTER DEFAULT
PRIVILEGES` z 15 sierpnia jest nadal na miejscu i obejmie to, co administrator utworzy
później.

## Open Questions

- Czy `market-data` będzie kiedykolwiek uruchamiane w więcej niż jednej instancji. Blokada
  jest napisana tak, jakby tak, więc odpowiedź nie zmienia ani specyfikacji, ani zadań —
  zmienia tylko to, czy scenariusz dwóch instancji jest realny, czy hipotetyczny.
