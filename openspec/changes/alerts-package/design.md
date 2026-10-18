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

### 8. Przejście w dwóch wdrożeniach (expand / contract)

- **Wdrożenie 1**: `alerts` startuje, a jego lifespan wykonuje jednorazową migrację danych, oznaczoną
  w tabeli `migrations_done`. Czyta przypisania (`GET /telegram/assignments`), reguły kanałów i
  tematów (`GET /youtube/channels`, `/topics`) i próg postów (ustawienie) w procesie, po czym tworzy
  reguły. Producenci przełączają się z wysyłki na publikację w tym samym wdrożeniu. Tabele `purposes`,
  `assignments` i kolumna `alert_rule` jeszcze zostają, a trasy celów odpowiadają `410`.
- **Wdrożenie 2**: migracje usuwają `purposes`, `assignments` i `alert_rule`, a
  `ALERT_MIN_IMPACT_SCORE` trafia do `RETIRED_SETTINGS`.

Kolejność startu pakietów w lifespanie: `telegram`, `youtube` i `social` migrują przed `alerts`, a
`alerts` przed producentami pętli. Migrację danych robi `alerts` dopiero po tym, jak sąsiedzi
serwują.

## Risks / Trade-offs

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

Dwa wdrożenia, jak w decyzji 8. Przed pierwszym: `ALERTS_DATABASE_URL` w `deploy/env.required`, baza i
rola w `ensure-databases.sh`, ewentualnie `ALERTS_OPENAI_API_KEY` w środowisku `vps`.

Wycofanie wdrożenia 1: `deploy.sh` przywraca poprzednie obrazy. Tabele celów i przypisań stoją
nietknięte, więc stara brama działa jak przedtem, a reguły w bazie `alerts` czekają nieużywane.
Wdrożenie 2 jest nieodwracalne tylko dla tabel, które od wdrożenia 1 nikt nie czytał.

## Open Questions

- Domyślne liczby: najkrótszy interwał (proponowane 30 s), okno ponowień (6 h), sufit wysyłek reguły
  (20/h), retencja zdarzeń (30 dni). Ustawienia, nie wymagania. Do skorygowania po tygodniu na
  produkcji.
- Czy `tc-openai` obsługuje jedno wywołanie ze schematem bez strumienia. Jeśli nie, `alerts` woła
  SDK `openai` wprost; zależność workbench już ma.
