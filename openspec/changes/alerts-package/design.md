## Context

Stan dzisiejszy i pięć wariantów opisuje `docs/telegram-wyzwalacze.html`; motywacja jest w proposal.md.
Trzy fakty z kodu kształtują podejście:

- Wyzwalacze zespołów (`teams/scheduler/clock.py`) mają już dojrzałą semantykę warunku: zbocze,
  czas martwy, trzeci stan, zajęcie wiersza przed sprawdzeniem. Pakiet `alerts` nie może ich
  zaimportować (`tests/test_layering.py`).
- Pakiety rozmawiają ze sobą przez REST sąsiada zamontowany w procesie
  (`tc_runtime.caller_access.in_process`, wzór: `workbench/telegram_client.py`). Narzędzia
  archiwów są dostępne jako funkcje (`workbench/local_tools.py`).
- Producenci (YouTube, social) mają już znacznik stawiany po sukcesie i ponowienie w następnym
  przebiegu. Zmienia się tylko to, kto ten sukces potwierdza.

## Goals / Non-Goals

**Goals:**
- Jedna tabela decyzji „czy i komu”, z historią, którą da się przeczytać bez bazy.
- Przejście bez okna, w którym alerty milkną albo przychodzą podwójnie.

**Non-Goals:**
- Ogólna szyna zdarzeń (wariant D). Zdarzenia płyną tylko do `alerts`, który nikomu ich dalej nie
  rozsyła.
- Wydzielenie silnika warunku do `packages/` (patrz decyzja 3).

## Decisions

### 1. Zdarzenie wchodzi przez REST w procesie, a zapisuje je `alerts`

Producent woła `POST /alerts/events` klientem `in_process` i stawia znacznik po `2xx`. `alerts` w jednej
transakcji zapisuje zdarzenie (unikalne na `(type, source_key)`) i tworzy odpalenia dla pasujących
reguł (unikalne na `(rule_id, event_id)`). Doręczenie robi zegar.

Rozważone alternatywy:
- **Funkcja wstrzyknięta przez assembly**: brak trasy, ale też brak rekordu wołających i odmów
  czytelnych tak samo jak przez HTTP. Wzór `telegram_client` jest już w repo i jest tańszy w nauce.
- **Outbox w bazie producenta czytany przez `alerts`**: łamie zasadę „nie czyta cudzej bazy”.
- **`LISTEN/NOTIFY`**: w jednym procesie nie daje nic ponad wywołanie, a gubi zdarzenie przy
  restarcie.

Trasa publikacji przyjmuje wyłącznie wołającego oznaczonego przez `in_process` (`IN_PROCESS_CALLER`
w scope). `EdgeAuth` i `X-TC-Edge` sprawiają, że żądanie z zewnątrz nie może się tak oznaczyć. Test to
sprawdza.

### 2. Stan czytany przez narzędzia lokalne tylko do odczytu, z ich schematów

Assembly przekazuje `alerts` podzbiór `local_tools` oznaczony `READ_ONLY` (ta sama adnotacja, którą
już niesie każde `@mcp.tool` archiwów). `trading-mcp` jest poza zbiorem: to serwer sieciowy z
narzędziami rachunku, a warunek nad pozycją to osobna zmiana. Katalog dla terminala powstaje z
`inputSchema` i `outputSchema` narzędzi FastMCP. Pola liczbowe wyniku stają się listą wyboru zamiast
`field_path` wpisywanego tekstem. Zagnieżdżenie (`items.0.value`) jest wyliczane ze schematu.

Alternatywa: rejestr serwerów narzędzi z zespołów, razem ze zdalnymi. Odrzucona, bo daje narzędzia
zapisujące i sieć tam, gdzie potrzebny jest odczyt.

### 3. Silnik zbocza: kopia, nie pakiet współdzielony

Około 60 linii (chodzenie po polu, porównanie, zbocze, czas martwy, trzeci stan) zostaje skopiowanych
z `teams/scheduler/clock.py` do `alerts/conditions.py`. Jest jedna zmiana semantyki: pierwsze
sprawdzenie po niedostępności porównuje z ostatnim **znanym** wynikiem (`alerts-conditions`).
Zespoły dziś zerują wtedy `last_result`, więc mogą dać fałszywe zbocze. Poprawka u nich to osobna
zmiana.

Alternatywa: `packages/tc-conditions`. Odrzucona na teraz, bo dwie kopie z różną semantyką trzeciego
stanu to dwa zachowania, a nie jedno. Wspólny pakiet ma sens dopiero po wyrównaniu. Kopię mierzy
`scripts/measure-duplication.py`.

### 4. Szablon to własny podstawiacz, nie `str.format`

Pola `{name}` są zastępowane wartościami atrybutu, wartości i nazwy reguły. Nic poza tym nie jest
interpretowane. `str.format` pozwala na `{x.__class__}` i daje dostęp do obiektów z szablonu
wpisanego w przeglądarce, dlatego jest wykluczony. Treść jest cięta do limitu bramy przez `alerts`,
ze znacznikiem ucięcia, bo brama ucięcia odmawia. Szablon domyślny zdarzenia to `{text}`, czyli
gotowa treść producenta. Formatowanie treści zostaje więc tam, gdzie jest dziś.

### 5. Doręczenie po nazwie adresata, z klasyfikacją odmowy

`alerts` woła `POST /telegram/messages` z `destination`. Odmowy bramy dzielą się na trwałe (nieznany
adresat, zablokował, jeszcze nie odbiera, za długa treść) i przejściowe (`429` z `retry_after`, brak
odpowiedzi). Trwała kończy odpalenie, a przejściowa ustawia `next_attempt_at`. Brama zostaje bez
pamięci — pamięta `alerts`.

### 6. Szkic: własny klucz i jedno wywołanie ze strukturą

`ALERTS_OPENAI_API_KEY` i `ALERTS_DRAFT_MODEL` to osobna linia rachunku, tak jak `TEAMS_` obok
`AGENT_`. Wywołanie jest jedno, nie strumieniowane, z wymuszonym schematem odpowiedzi równym
`RuleIn` z polem `defects`. Do promptu trafia katalog przycięty do nazw: typy z atrybutami, narzędzia
z polami liczbowymi, śledzone instrumenty, adresaci. Wynik przechodzi walidację zapisu
(`alerts-drafts`). Zużycie trafia do tabeli `draft_usage`, a ona stanowi dobowy sufit.

Alternatywa: narzędzie `draft_alert_rule` w rozmowie. Odrzucona na teraz, bo rozmowa nie ma dokąd
oddać formularza do zatwierdzenia, a zapis z rozmowy jest zakazany (`alerts-rules`). Pocket i rozmowa
to osobna zmiana.

### 7. Zegar: jeden obrót, trzy prace

Pętla co `ALERTS_TICK_SECONDS` (domyślnie 5 s):
1. zajmuje należne reguły stanu przez `UPDATE … SET next_check_at = … WHERE next_check_at <= now()
   … RETURNING` z `FOR UPDATE SKIP LOCKED`;
2. zajmuje należne odpalenia do doręczenia tak samo;
3. raz na godzinę usuwa zdarzenia po retencji.

Publikacja zdarzenia budzi zegar od razu (`asyncio.Event`), więc alert o filmie nie czeka pięciu
sekund. Zapytania 1 i 2 przechodzą przez skill `db-cost-check` przed scaleniem, z indeksami
częściowymi na `next_check_at WHERE enabled` i `next_attempt_at WHERE state = 'pending'`.

### 8. Przejście w trzech krokach, w których nic nie milknie

Każde scalenie wdraża produkcję, a wdrożenie nie może zostawić alertów bez drogi do telefonu. Stąd kolejność:

1. **Konwersja** (grupa 8). `alerts` startuje i raz, pod znacznikiem w `migrations_done`, zamienia to, co operator już
   ustawił, na reguły: przypisania bramy, reguły alertu kanałów i tematów oraz próg postów. Dane bierze od sąsiadów
   przez klienta z assembly (`GET /telegram/assignments`, `/youtube/channels`, `/youtube/topics`), a regułom daje typy
   zdarzeń w minimalnym kształcie, które konwersja sama wstawia. Producenci wysyłają jeszcze po staremu, więc reguły stoją
   bezczynnie, a stare przypisania dalej działają.
2. **Producenci** (grupa 9). Zamiast wysyłać do bramy z celem, publikują zdarzenie; ogłoszenie ich typu zastępuje
   minimalny kształt. Od tej chwili reguły z kroku 1 są jedyną drogą.
3. **Sprzątanie** (grupa 11). Znikają `purposes`, `assignments`, `alert_rule` i trasy, które ich dotyczyły.

Kroki 1 i 2 leżą w różnych scaleniach i wdrożeniach; okno między nimi nic nie kosztuje, bo dopóki producenci nie
publikują, reguły nie mają co łapać. Zostaje jedno okno w kroku 2: zdarzenie opublikowane w sekundach między startem
procesu a ogłoszeniem typu.

Kolejność startu pakietów w lifespanie: `telegram`, `youtube` i `social` migrują przed `alerts`, a konwersja czyta ich
dane dopiero po tym, jak serwują.

## Risks / Trade-offs

- [Reguła ceny widzi wartość z chwili sprawdzenia, nie ekstremum między sprawdzeniami: szpilka, która przebiła poziom i wróciła w ciągu jednego interwału, przepadnie] → `get_last_price` celowo nie niesie high/low okresu w toku (`market-data-tools`: zakres okresu w toku nie jest zakresem zamkniętym), więc zmiana tego narzędzia byłaby zmianą kontraktu archiwum. Najkrótszy interwał (30 s) zawęża lukę; ekstremum okresu jest osobną zmianą w `market_data`.
- [Film odczytany tuż przed wdrożeniem 1 ma znacznik starej wysyłki, a nowy kod opublikuje go
  ponownie] → znacznik publikacji to ta sama kolumna co znacznik wysyłki. Film już powiadomiony nie
  jest publikowany, kosztem tego, że nie trafi do historii zdarzeń.
- [Reguła migrowana z przypisania `*` łapie wszystko i zalewa po pierwszym zdarzeniu każdego typu] →
  migracja tworzy z `*` reguły tylko dla typów, które `*` faktycznie dostawał (YouTube, social), a nie
  regułę „wszystko”. Sufit wysyłek reguły zostaje jako druga linia.
- [Wolumen zdarzeń social: każdy odczytany post, nie tylko ≥ 8] → rząd setek dziennie, bez treści
  posta poza gotowym tekstem powiadomienia. Retencja 30 dni. Pomiar w `db-cost-check`.
- [Model w szkicu wymyśla pole albo instrument] → walidacja zapisu i wady pokazane przy polach. Szkic
  nie ma drogi do zapisu.
- [Dziewiąty pakiet podnosi budżet połączeń] → pula 2, wpis w `test_pool_budget.py`. Praca to kilka
  zapytań na obrót.
- [Zmiana modyfikuje wymagania z dwóch niezarchiwizowanych zmian] → archiwizowana po nich (proposal).

## Migration Plan

Trzy kroki, jak w decyzji 8. Przed pierwszym wdrożeniem: `ALERTS_DB_PASSWORD` w środowisku `vps`
(`deploy/scripts/fill-github-environment.sh`), ewentualnie `ALERTS_OPENAI_API_KEY`.

Wycofanie kroku 1 lub 2: `deploy.sh` przywraca poprzednie obrazy. Tabele celów i przypisań stoją nietknięte aż do
kroku 3, więc stara brama działa jak przedtem, a reguły w bazie `alerts` czekają nieużywane. Krok 3 jest
nieodwracalny tylko dla tabel, których od kroku 2 nikt nie czyta.

## Open Questions

- Domyślne liczby: najkrótszy interwał (proponowane 30 s), okno ponowień (6 h), sufit wysyłek reguły
  (20/h), retencja zdarzeń (30 dni). Ustawienia, nie wymagania. Do skorygowania po tygodniu na
  produkcji.
- Czy `tc-openai` obsługuje jedno wywołanie ze schematem bez strumienia. Jeśli nie, `alerts` woła
  SDK `openai` wprost; zależność workbench już ma.
