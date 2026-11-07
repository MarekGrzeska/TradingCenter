## Context

Bramka ma dziś jeden `CapitalClient`, czyli jedną parę `CST`/`X-SECURITY-TOKEN`, jeden `RateGate` i jedno konto aktywne, przełączane przez `PUT /api/v1/session`. Strumień (`stream_tokens_for`) bierze tokeny z tej samej sesji. `trading-mcp` nie zna pojęcia konta. `teams` trzyma jedną sesję MCP do `trading-mcp` (`ToolServer`), wspólną dla wszystkich runów.

Pomiary z 28 października 2026 (`docs/demo-wiele-kont-rownolegle.html`, sekcja 08, cztery sesje z jednego klucza API):
- konto jest stanem sesji: A=random, B=devtest i C=demo2 działały jednocześnie, a pozycja otwarta z A nie była widoczna z B;
- przełączenie konta w sesji handlowej nie zerwało strumienia innej sesji; w oknie 10 s nie zerwało go nawet przełączenie na tej samej sesji;
- świeży login zawsze otwiera się na koncie `preferred` (demo2).

## Goals / Non-Goals

**Goals:**
- Każde żądanie może wskazać konto i działa na nim niezależnie od innych żądań.
- Wołający, którzy nie wskazują konta, zachowują się dokładnie tak jak dziś.

**Non-Goals:**
- Osobne loginy capital.com i osobne budżety zapytań na strategię (opcja C z dokumentu). Zbędne, skoro konto jest per sesja.
- Zakładanie kont demo przez API. Operator robi to w panelu dostawcy.
- Raport P&L per strategia. Kolumna konta w śladzie jest podstawą, ale sam raport to osobna praca.
- Przypisywanie konta rozmowie (`agent`). Rozmowa dalej działa na koncie aktywnym.

## Decisions

### D1. Konto w nagłówku `X-Capital-Account`, a nie w ścieżce

Trasy pozostają te same i dostają opcjonalny nagłówek. Odrzucone `/accounts/{id}/positions` i podobne: podwajają trasy, rejestr dostępu (`capital-access-control`, wpisy po ścieżce) i snapshot OpenAPI, a trasa bez konta i tak musi zostać dla zgodności. Odrzucony parametr zapytania: przy `POST /orders` konto ląduje obok ciała zlecenia, z którym nie ma nic wspólnego, a nagłówek jest tym samym miejscem dla każdej metody. FastAPI publikuje nagłówek w OpenAPI, więc kontrakt go widzi.

### D2. Pula sesji po koncie, z jednym `RateGate`

`SessionPool` trzyma `CapitalClient` po identyfikatorze konta, tworzony leniwie przy pierwszym żądaniu wskazującym to konto. Każdy klient zna swoje konto docelowe. Wszystkie dostają ten sam obiekt `RateGate` (dziś każdy tworzy własny w `__init__`). Sesja domyślna, czyli „aktywna”, jest wpisem puli bez wskazanego konta, a jej konto docelowe zmienia `PUT /accounts/active`. Przed utworzeniem sesji identyfikator jest sprawdzany na liście kont, z pamięcią podręczną odświeżaną przy chybieniu. Dzięki temu nieznane konto dostaje 400 bez zbędnego logowania. Bezczynne sesje nie są podtrzymywane: wygasają u dostawcy, a następne żądanie loguje się ponownie (D3). Odrzucone „przełącz i wykonaj pod muteksem” (opcja A): każde wywołanie kosztowałoby dodatkowe zapytanie, a muteks serializowałby wszystkie konta.

### D3. Konto przywracane wewnątrz zadania logowania

`_login` po udanym `POST /session` porównuje `currentAccountId` z odpowiedzi z kontem docelowym klienta. Jeśli są różne, wysyła `PUT /session`, zanim zadanie się zakończy. Wszyscy czekający na wspólne logowanie (`_login_inflight`) dostają więc sesję już na właściwym koncie, a nie na preferowanym. Odmowa przełączenia kończy zadanie błędem, a żądanie nie jest wykonywane (wymóg „fail closed” w specyfikacji). Odrzucone przywracanie w `request()` po ponowieniu: między logowaniem a przełączeniem inne żądanie mogłoby przejść na koncie preferowanym. To jest też cała poprawka błędu z pomiaru 3 i można ją wdrożyć jako pierwszą, osobno.

### D4. Strumień na własnej sesji, która nigdy nie zmienia konta

Hub dostaje osobnego klienta z puli, którego nikt nie przełącza. Pomiar nie odtworzył zerwania strumienia przy przełączeniu, ale okno obserwacji miało tylko 10 s, a docstring opisuje zerwanie, które ktoś kiedyś widział. Osobna sesja kosztuje jedno logowanie i usuwa pytanie, zamiast na nie odpowiadać. Z opisu trasy, narzędzia i ekranu znika wtedy ostrzeżenie o zerwaniu.

### D5. W `teams` konto wstrzykuje silnik, a schemat dla modelu traci parametr

`trading.account_id` leży w `TradingLimits`, obok granic, bo jest warunkiem eksperymentu tak jak one. Przy ogłaszaniu narzędzi `trading-mcp` agentowi zespołu z kontem `assignment.py` usuwa `account_id` ze schematu. Przed wywołaniem silnik nadpisuje argument kontem z rewizji. Odrzucona osobna sesja MCP na run z nagłówkiem konta: `ToolServer` jest współdzielony celowo (jedno połączenie, jeden zamek), a `trading-mcp` musiałby trzymać stan per sesja. Parametr w argumentach jest bezstanowy i widać go w śladzie. Dla rewizji bez konta nic się nie zmienia: model widzi `account_id` jako opcjonalny i go nie dostaje.

### D6. Konto rewizji sprawdzane przy starcie runu, a nie przy zapisie

Ścieżka zapisu buduje rejestr narzędzi z samych ustawień i nie ma sesji MCP („announcing does not touch the pool”). Konto usunięte u dostawcy po zapisie i tak wymaga sprawdzenia w chwili runu. Silnik czyta więc `list_accounts` raz na run zespołu z kontem, zanim wywoła pierwszego agenta. Przy zapisie sprawdzane jest tylko to, co da się sprawdzić bez sieci, czyli zakaz `switch_active_account` i `top_up_demo_account`.

## Risks / Trade-offs

- [Budżet 10 zapytań/s na login dzielą wszystkie sesje] → jeden `RateGate` dla całej puli. Typowy run teamu to kilka odczytów i jedno zlecenie, więc pięć do dziesięciu teamów mieści się w budżecie z zapasem.
- [Logowanie jest ograniczone do 1/s na klucz, a pierwsze użycie kilku kont naraz to kilka logowań] → logowania idą przez wspólną bramkę tempa i się kolejkują. Opóźnienie pierwszego żądania na nowym koncie wynosi do kilku sekund, co przy runie trwającym minuty nie ma znaczenia.
- [Zespół bez konta dalej dzieli konto aktywne z rozmową i operatorem] → zachowanie jak dziś. Ekran kont mówi przed przełączeniem, kogo ono dotyczy.
- [Dwa zespoły z tym samym kontem mieszają wyniki] → terminal ostrzega, ale nie blokuje. Operator może tego chcieć celowo.
- [Parametr `account_id` w ośmiu narzędziach zwiększa powierzchnię opisów] → krótki opis parametru, a w razie potrzeby świadoma korekta sufitu w teście powierzchni `trading-mcp`.
- [Zachowanie dostawcy może się zmienić] → pomiary 1–3 trafiają do testów `-m live --run-live-trading` w bramce.

## Migration Plan

Jeden merge. Wszystko jest wstecznie zgodne: nagłówek jest opcjonalny, pole rewizji opcjonalne, a kolumna `account_id` w `teams.trades` nullable i dodawana migracją w `lifespan`. Wdrożenie odbywa się zwykłą drogą `deploy-vps.yml`. Wycofanie to poprzednie obrazy: kolumna zostaje i nikomu nie przeszkadza, a rewizje z kontem zapisane w międzyczasie stare obrazy zignorują (pole poza modelem) i pobiegną na koncie aktywnym. Dlatego wycofanie trzeba ogłosić operatorowi.

Poprawkę D3 można wydzielić i wdrożyć wcześniej jako zwykłą gałąź.
