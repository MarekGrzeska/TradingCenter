## 1. Szkielet modułu

- [x] 1.1 Utworzyć `modules/agent/` — `agent/`, `tests/`, `pyproject.toml` (uv, fastapi,
      langgraph, langchain-openai, sqlalchemy, alembic, azure-identity, pydantic-settings),
      `README.md`, `.env.example`, `Dockerfile` na wzór `market-data`
- [x] 1.2 `agent/app.py` — aplikacja FastAPI na porcie 8030 z trasą zdrowia i konfiguracją
      logowania roota (bez niej moduł pisze w próżnię, jak `market-data` przed poprawką)
- [x] 1.3 `agent/config.py` — ustawienia z walidacją: tryb bazy (`DATABASE_USER`
      ustawiony/nieustawiony), tryb dostawcy modeli (tożsamość albo klucz, dokładnie jedno),
      `REQUIRE_AUTHENTICATED_PRINCIPAL`, `LOG_LEVEL`
- [x] 1.4 Testy `config.py`: host zdalny bez tożsamości odmawia startu, poświadczenie w
      `DATABASE_URL` obok tożsamości odmawia startu, brak szyfrowania przy hoście zdalnym
      odmawia startu, dwa tryby dostawcy naraz odmawiają startu
- [x] 1.5 `uv run ruff check .` i `uv run pyright` przechodzą na pustym module

## 2. Baza i migracje

- [x] 2.1 `agent/db.py` — silnik i sesje, pobieranie poświadczenia Entra przy nawiązywaniu
      połączenia i jego odnawianie (wzorzec z `market_data/db.py`, przepisany, nie
      zaimportowany)
- [x] 2.2 `agent/models.py` — sesje (tytuł, właściciel, model, wersja promptu, utworzenie,
      ostatnia aktywność), wiadomości (sesja, rola, treść, porządek, model, moment,
      oznaczenie niepełnej), zużycie (sesja, wiadomość, model, tokeny wejścia/wyjścia/
      cache/rozumowania, stawki, koszt `NUMERIC`, moment)
- [x] 2.3 `migrations/` — alembic z `0001_sessions_messages_usage.py`; `alembic.ini` i
      `env.py` na wzór `market-data`
- [x] 2.4 Testy `-m db` (testcontainers): migracje wchodzą na czystej bazie, porządek
      wiadomości jest powtarzalny, sesja bez wiadomości nie wchodzi na listę rozmów
- [x] 2.5 Test: poświadczenie nie pojawia się w logu błędu połączenia

## 3. Katalog modeli i prompt systemowy

- [x] 3.1 `agent/models_catalogue.py` — katalog z konfiguracji: identyfikator, nazwa
      modelu u dostawcy, nazwa do pokazania, porządek kosztu, stawki wejścia i wyjścia
- [x] 3.2 Start modułu odmawia, gdy model w katalogu nie ma stawki
- [x] 3.3 `agent/prompt.py` — prompt systemowy agenta terminala tradingowego z
      identyfikatorem wersji; prompt nazywa brak narzędzi i brak rekomendacji
- [x] 3.4 `GET /models` — katalog na wyjściu; test, że odpowiedź wystarcza do zbudowania
      wybieraka (identyfikator, nazwa, porządek, stawki)
- [x] 3.5 Testy: model spoza katalogu jest odmową z nazwą modelu w przyczynie; sesja bez
      wskazanego modelu dostaje domyślny

## 4. Rozmowa i strumień

- [x] 4.1 `agent/graph.py` — graf LangGraph z jednym węzłem modelu, historia budowana z
      tabel; miejsce na węzeł narzędzi zostawione, ale puste
- [x] 4.2 `agent/provider.py` — klient OpenAI na kluczu (tożsamości zarządzanej nie ma do
      czego użyć), wybór modelu po katalogu
- [x] 4.3 Trasy sesji: `POST /sessions`, `GET /sessions`, `GET /sessions/{id}`,
      `GET /sessions/{id}/messages`, `PATCH /sessions/{id}` (model i/albo nazwa),
      `DELETE /sessions/{id}`
- [x] 4.3a Nazwa nadana ręcznie nie jest nadpisywana tytułem wyprowadzonym; nazwa pusta,
      sama ze spacji albo dłuższa niż 120 znaków jest odmową
- [x] 4.3b Usunięcie znaczy `deleted_at`, nie `DELETE` — wiersze `usage` zostają, a każde
      czytanie sesji filtruje po `deleted_at IS NULL`, więc usunięta rozmowa odpowiada tak
      jak nieistniejąca na wszystkich trasach naraz
- [x] 4.4 `POST /sessions/{id}/messages` — zapis wypowiedzi operatora **przed** wywołaniem
      modelu, odpowiedź `text/event-stream`
- [x] 4.5 Tura modelu w zadaniu niezwiązanym z cyklem życia żądania; rozłączenie wołającego
      zamyka kolejkę, nie turę
- [x] 4.6 Komentarz utrzymujący w strumieniu co kilkanaście sekund (bezczynne połączenie
      App Service jest zrywane po 230 s)
- [x] 4.7 Zdarzenia strumienia: fragment, domknięcie, błąd — trzy odróżnialne
- [x] 4.8 Tytuł sesji nadawany z pierwszej wypowiedzi operatora, stabilny przy kolejnych
- [x] 4.9 Testy na fałszywym modelu: fragmenty przed końcem, rozłączenie w połowie zapisuje
      całość, błąd w połowie zapisuje część z oznaczeniem niepełnej, wypowiedź operatora
      zostaje po nieudanym wywołaniu

## 5. Zużycie i koszt

- [x] 5.1 Zapis wiersza zużycia przy każdym wywołaniu modelu, ze stawkami i kosztem
      policzonym w chwili zapisu
- [x] 5.2 Zużycie nieraportowane przez dostawcę zapisywane jako nieznane, odróżnialne od
      zerowego
- [x] 5.3 Zużycie z wywołania przerwanego błędem zapisywane w tym, co dostawca podał
- [x] 5.4 `GET /usage` — agregaty w podziale na model, sesję i czas, w zakresie dat; sumy
      liczone z zapisanych kosztów
- [x] 5.5 Testy: zmiana cennika nie rusza kosztu dawnych wierszy; pusty zakres to puste
      zestawienie, nie błąd; nieznane zużycie nie wpada do sumy jako zero

## 6. Dostęp z przeglądarki

- [x] 6.1 Tożsamość wołającego z nagłówków Easy Auth; tryb lokalny bez warstwy przed
      modułem przypisuje tożsamość lokalną
- [x] 6.2 Sesja przypisana do tożsamości; cudza sesja odpowiada tak samo jak nieistniejąca
- [x] 6.3 `REQUIRE_AUTHENTICATED_PRINCIPAL` włączony odmawia wywołania bez tożsamości przed
      dotknięciem modelu
- [x] 6.4 Testy: lista rozmów zwraca tylko własne, cudza sesja jest nieodróżnialna od
      nieistniejącej, brak tożsamości to odmowa
- [x] 6.5 `agent` nie dokłada własnego CORS — nagłówki są zadaniem App Service; test
      pilnujący, że middleware CORS nie ma

## 7. Terminal — panel agenta

- [x] 7.1 `src/data/config.ts` — `VITE_AGENT_HTTP` i domyślny prefiks `/agent-api`; proxy w
      `vite.config.ts`; test porównujący prefiksy z listą zakładek
- [x] 7.2 `src/agent/agentApi.ts` — DTO agenta pisane ręcznie, wywołania sesji i katalogu,
      token z `Identity`
- [x] 7.3 `src/agent/stream.ts` — parser ramek SSE nad `fetch` + `ReadableStream`, z testami
      na ramkę rozciętą między porcjami
- [x] 7.4 `agentChatStore.ts` — stan na sesjach z modułu zamiast zaszytych odpowiedzi;
      zapamiętana ostatnio otwarta rozmowa, zachowany zapis stanu zwinięcia
- [x] 7.5 Lista rozmów w panelu: wybór rozmowy, nowa rozmowa, porządek od ostatnio używanej
- [x] 7.5a Zmiana nazwy i usunięcie wprost z wiersza listy; usunięcie za potwierdzeniem,
      nazwa brana z odpowiedzi modułu, a usunięcie rozmowy otwartej zamyka jej transkrypt
- [x] 7.6 Wybierak modelu zbudowany z katalogu, z widoczną różnicą stawki; katalog
      niedostępny mówi to wprost i nie podstawia listy z kodu
- [x] 7.7 Strumień w dymku: oczekiwanie przed pierwszym fragmentem, dopisywanie kolejnych,
      oznaczenie odpowiedzi niepełnej, komunikat o nieosiągalnym module
- [x] 7.8 Usunąć plakietkę „mockup" i zaszyte `CANNED_REPLY`/`seedMessages`
- [x] 7.9 Testy panelu: zmiana zakładki nie przerywa strumienia, powrót do rozmowy wczytuje
      transkrypt z modułu, przeładowanie wraca do tej samej rozmowy

## 8. Terminal — zakładka Agents cost

- [x] 8.1 Wpis w `src/app/tabs.ts` i widok `src/agent/cost/AgentCostView.tsx`
- [x] 8.2 Wybór zakresu dat; przekroje: model, rozmowa, czas; suma kosztu w jednym miejscu
- [x] 8.3 Przejście z rozmowy do jej wywołań
- [x] 8.4 Zużycie nieznane pokazane jako nieznane; pusty zakres mówi, że nic nie zużyto;
      moduł nieosiągalny mówi to wprost
- [x] 8.5 Testy: liczby biorą się z modułu, terminal niczego nie przelicza

## 9. Środowisko lokalne

- [x] 9.1 `scripts/dev.sh` i `scripts/dev.ps1` — zakładanie bazy `agent`, jeśli jej nie ma,
      i uruchamianie modułu w kolejności migracje → gateway → market-data → agent → terminal
      (`--no-terminal` / `-NoTerminal` bez zmian)
- [x] 9.2 Odmowa skryptu, gdy `.env` agenta wskazuje hosta spoza pętli zwrotnej
- [x] 9.3 `modules/agent/.env.example` uzupełniony o katalog modeli i stawki, gotowy do
      skopiowania bez edycji poza poświadczeniem

## 10. Infrastruktura

- [x] 10.0 Sprawdzić, czy dostawca modeli w ogóle je wyda. Zmierzone 12 sierpnia 2026:
      subskrypcja jest Pay-As-You-Go (więc ryzyko „Free Trial ma quotę 0" nie dotyczy), ale
      `gpt-5.6-*` mają w Azure quotę 0 we wszystkich 28 regionach — stąd przejście na
      OpenAI wprost. Odpowiednik tego kroku teraz: `GET /v1/models` na koncie OpenAI
- [x] 10.1 Modele bierze się wprost z OpenAI — w tym roocie nie powstaje **żaden** zasób
      modelu (`infra/openai.tf` usunięty wraz z kontem, deploymentami i rolą)
- [x] 10.2 `infra/variables.tf` — katalog modeli jako `var.agent_models` (nazwa u dostawcy,
      nazwa do pokazania, porządek kosztu, stawki), z komentarzem, że nazw nie sprawdza nic
      i potwierdza je operator przed apply
- [x] 10.3 `infra/app-service.tf` — czwarta aplikacja na istniejącym planie: tożsamość
      zarządzana, Easy Auth, CORS na adres terminala, ustawienia aplikacji, `lifecycle`
      na obraz kontenera
- [x] 10.4 `infra/key-vault.tf` — sekret `openai-api-key` i referencja
      `@Microsoft.KeyVault(...)` w ustawieniach agenta; wartość wpisuje operator po apply,
      nie przechodzi przez stan Terraforma
- [x] 10.5 `infra/database.tf` — baza logiczna `agent` i reguły firewalla na adresy
      wychodzące aplikacji agenta (`for_each` po jej `possible_outbound_ip_address_list`)
- [x] 10.6 `infra/entra.tf` — rejestracja API agenta i uprawnienie terminala do jego zakresu
- [x] 10.7 Adres agenta (`app-service.tf`) — obok analogicznych wyjść market-data/gateway,
      nie w `outputs.tf` (te trzymają tylko wyjścia bez naturalnego pliku-właściciela,
      wzorem istniejących `market_data_hostname` itp.)
- [x] 10.8 `terraform fmt` i `terraform validate` przechodzą; plan przejrzany przez
      operatora (apply jest jego, nie CI)

## 11. CI i wdrożenie

- [x] 11.1 `.github/workflows/checks.yml` — `agent` w filtrze `changes` i czwarty job
      (ruff, pyright, pytest, pytest -m db)
- [x] 11.2 `.github/workflows/deploy-agent.yml` na wzór pozostałych trzech, zakończony
      sprawdzeniem wdrożonej aplikacji
- [x] 11.3 Filtr terminala obejmuje zmiany w `modules/agent` wyłącznie tam, gdzie dotyczą
      kształtu wystawianego terminalowi

## 12. Dokumentacja i domknięcie

- [x] 12.1 `modules/agent/README.md` — co, jak uruchomić, jak przetestować, jaki kontrakt
- [x] 12.2 `CLAUDE.md` i `README.md` — czwarty moduł, port 8030, komendy, druga baza lokalna
- [x] 12.3 `docs/architecture.md` — agent na schemacie jako konsument, nie peer
- [x] 12.4 Uruchomić cały stos lokalnie i przeprowadzić rozmowę na każdym z trzech modeli;
      sprawdzić, że koszt pojawia się w zakładce. Zrobione po stronie modułu: trzy tury
      strumieniem, każda zakończona `complete`, transkrypt z `model_id` i `prompt_version`,
      `/usage` liczy trzy różne stawki i `unknown_count` = 0 wszędzie. Zostaje przejście
      tą samą drogą przez terminal (5173)
- [ ] 12.5 Sprawdzić strumień na wdrożonej aplikacji, nie tylko lokalnie (buforowanie i
      zerwanie po 230 s widać dopiero tam)
- [ ] 12.6 `openspec validate add-agent-chat --strict`
- [ ] 12.7 `review.md` przed archiwizacją
