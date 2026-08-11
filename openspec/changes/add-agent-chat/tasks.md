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

- [ ] 2.1 `agent/db.py` — silnik i sesje, pobieranie poświadczenia Entra przy nawiązywaniu
      połączenia i jego odnawianie (wzorzec z `market_data/db.py`, przepisany, nie
      zaimportowany)
- [ ] 2.2 `agent/models.py` — sesje (tytuł, właściciel, model, wersja promptu, utworzenie,
      ostatnia aktywność), wiadomości (sesja, rola, treść, porządek, model, moment,
      oznaczenie niepełnej), zużycie (sesja, wiadomość, model, tokeny wejścia/wyjścia/
      cache/rozumowania, stawki, koszt `NUMERIC`, moment)
- [ ] 2.3 `migrations/` — alembic z `0001_sessions_messages_usage.py`; `alembic.ini` i
      `env.py` na wzór `market-data`
- [ ] 2.4 Testy `-m db` (testcontainers): migracje wchodzą na czystej bazie, porządek
      wiadomości jest powtarzalny, sesja bez wiadomości nie wchodzi na listę rozmów
- [ ] 2.5 Test: poświadczenie nie pojawia się w logu błędu połączenia

## 3. Katalog modeli i prompt systemowy

- [ ] 3.1 `agent/models_catalogue.py` — katalog z konfiguracji: identyfikator, nazwa
      deploymentu, nazwa do pokazania, porządek kosztu, stawki wejścia i wyjścia
- [ ] 3.2 Start modułu odmawia, gdy model w katalogu nie ma stawki
- [ ] 3.3 `agent/prompt.py` — prompt systemowy agenta terminala tradingowego z
      identyfikatorem wersji; prompt nazywa brak narzędzi i brak rekomendacji
- [ ] 3.4 `GET /models` — katalog na wyjściu; test, że odpowiedź wystarcza do zbudowania
      wybieraka (identyfikator, nazwa, porządek, stawki)
- [ ] 3.5 Testy: model spoza katalogu jest odmową z nazwą modelu w przyczynie; sesja bez
      wskazanego modelu dostaje domyślny

## 4. Rozmowa i strumień

- [ ] 4.1 `agent/graph.py` — graf LangGraph z jednym węzłem modelu, historia budowana z
      tabel; miejsce na węzeł narzędzi zostawione, ale puste
- [ ] 4.2 `agent/provider.py` — klient Azure OpenAI: tożsamość zarządzana albo klucz,
      wybór deploymentu po katalogu
- [ ] 4.3 Trasy sesji: `POST /sessions`, `GET /sessions`, `GET /sessions/{id}`,
      `GET /sessions/{id}/messages`, `PATCH /sessions/{id}` (zmiana modelu)
- [ ] 4.4 `POST /sessions/{id}/messages` — zapis wypowiedzi operatora **przed** wywołaniem
      modelu, odpowiedź `text/event-stream`
- [ ] 4.5 Tura modelu w zadaniu niezwiązanym z cyklem życia żądania; rozłączenie wołającego
      zamyka kolejkę, nie turę
- [ ] 4.6 Komentarz utrzymujący w strumieniu co kilkanaście sekund (bezczynne połączenie
      App Service jest zrywane po 230 s)
- [ ] 4.7 Zdarzenia strumienia: fragment, domknięcie, błąd — trzy odróżnialne
- [ ] 4.8 Tytuł sesji nadawany z pierwszej wypowiedzi operatora, stabilny przy kolejnych
- [ ] 4.9 Testy na fałszywym modelu: fragmenty przed końcem, rozłączenie w połowie zapisuje
      całość, błąd w połowie zapisuje część z oznaczeniem niepełnej, wypowiedź operatora
      zostaje po nieudanym wywołaniu

## 5. Zużycie i koszt

- [ ] 5.1 Zapis wiersza zużycia przy każdym wywołaniu modelu, ze stawkami i kosztem
      policzonym w chwili zapisu
- [ ] 5.2 Zużycie nieraportowane przez dostawcę zapisywane jako nieznane, odróżnialne od
      zerowego
- [ ] 5.3 Zużycie z wywołania przerwanego błędem zapisywane w tym, co dostawca podał
- [ ] 5.4 `GET /usage` — agregaty w podziale na model, sesję i czas, w zakresie dat; sumy
      liczone z zapisanych kosztów
- [ ] 5.5 Testy: zmiana cennika nie rusza kosztu dawnych wierszy; pusty zakres to puste
      zestawienie, nie błąd; nieznane zużycie nie wpada do sumy jako zero

## 6. Dostęp z przeglądarki

- [ ] 6.1 Tożsamość wołającego z nagłówków Easy Auth; tryb lokalny bez warstwy przed
      modułem przypisuje tożsamość lokalną
- [ ] 6.2 Sesja przypisana do tożsamości; cudza sesja odpowiada tak samo jak nieistniejąca
- [ ] 6.3 `REQUIRE_AUTHENTICATED_PRINCIPAL` włączony odmawia wywołania bez tożsamości przed
      dotknięciem modelu
- [ ] 6.4 Testy: lista rozmów zwraca tylko własne, cudza sesja jest nieodróżnialna od
      nieistniejącej, brak tożsamości to odmowa
- [ ] 6.5 `agent` nie dokłada własnego CORS — nagłówki są zadaniem App Service; test
      pilnujący, że middleware CORS nie ma

## 7. Terminal — panel agenta

- [ ] 7.1 `src/data/config.ts` — `VITE_AGENT_HTTP` i domyślny prefiks `/agent-api`; proxy w
      `vite.config.ts`; test porównujący prefiksy z listą zakładek
- [ ] 7.2 `src/agent/agentApi.ts` — DTO agenta pisane ręcznie, wywołania sesji i katalogu,
      token z `Identity`
- [ ] 7.3 `src/agent/stream.ts` — parser ramek SSE nad `fetch` + `ReadableStream`, z testami
      na ramkę rozciętą między porcjami
- [ ] 7.4 `agentChatStore.ts` — stan na sesjach z modułu zamiast zaszytych odpowiedzi;
      zapamiętana ostatnio otwarta rozmowa, zachowany zapis stanu zwinięcia
- [ ] 7.5 Lista rozmów w panelu: wybór rozmowy, nowa rozmowa, porządek od ostatnio używanej
- [ ] 7.6 Wybierak modelu zbudowany z katalogu, z widoczną różnicą stawki; katalog
      niedostępny mówi to wprost i nie podstawia listy z kodu
- [ ] 7.7 Strumień w dymku: oczekiwanie przed pierwszym fragmentem, dopisywanie kolejnych,
      oznaczenie odpowiedzi niepełnej, komunikat o nieosiągalnym module
- [ ] 7.8 Usunąć plakietkę „mockup" i zaszyte `CANNED_REPLY`/`seedMessages`
- [ ] 7.9 Testy panelu: zmiana zakładki nie przerywa strumienia, powrót do rozmowy wczytuje
      transkrypt z modułu, przeładowanie wraca do tej samej rozmowy

## 8. Terminal — zakładka Agents cost

- [ ] 8.1 Wpis w `src/app/tabs.ts` i widok `src/agent/cost/AgentCostView.tsx`
- [ ] 8.2 Wybór zakresu dat; przekroje: model, rozmowa, czas; suma kosztu w jednym miejscu
- [ ] 8.3 Przejście z rozmowy do jej wywołań
- [ ] 8.4 Zużycie nieznane pokazane jako nieznane; pusty zakres mówi, że nic nie zużyto;
      moduł nieosiągalny mówi to wprost
- [ ] 8.5 Testy: liczby biorą się z modułu, terminal niczego nie przelicza

## 9. Środowisko lokalne

- [ ] 9.1 `scripts/dev.sh` i `scripts/dev.ps1` — zakładanie bazy `agent`, jeśli jej nie ma,
      i uruchamianie modułu w kolejności migracje → gateway → market-data → agent → terminal
      (`--no-terminal` / `-NoTerminal` bez zmian)
- [ ] 9.2 Odmowa skryptu, gdy `.env` agenta wskazuje hosta spoza pętli zwrotnej
- [ ] 9.3 `modules/agent/.env.example` uzupełniony o katalog modeli i stawki, gotowy do
      skopiowania bez edycji poza poświadczeniem

## 10. Infrastruktura

- [ ] 10.0 Sprawdzić typ subskrypcji i quotę na modele Azure OpenAI; oferta próbna ma
      quotę 0 i wymaga przejścia na Pay-As-You-Go (kredyt i darmowe usługi zostają)
- [ ] 10.1 `infra/openai.tf` — `azurerm_cognitive_account` (kind OpenAI) i trzy
      `azurerm_cognitive_deployment` (luna/terra/sol), Global Standard
- [ ] 10.2 `infra/variables.tf` — nazwy i wersje modeli jako zmienne z komentarzem, że
      operator weryfikuje je `az cognitiveservices account list-models` przed apply
- [ ] 10.3 `infra/app-service.tf` — czwarta aplikacja na istniejącym planie: tożsamość
      zarządzana, Easy Auth, CORS na adres terminala, ustawienia aplikacji, `lifecycle`
      na obraz kontenera
- [ ] 10.4 Rola **Cognitive Services OpenAI User** dla tożsamości aplikacji agenta
- [ ] 10.5 `infra/database.tf` — baza logiczna `agent` i reguły firewalla na adresy
      wychodzące aplikacji agenta (`for_each` po jej `possible_outbound_ip_address_list`)
- [ ] 10.6 `infra/entra.tf` — rejestracja API agenta i uprawnienie terminala do jego zakresu
- [ ] 10.7 `infra/outputs.tf` — adres agenta i nazwa konta Azure OpenAI
- [ ] 10.8 `terraform fmt` i `terraform validate` przechodzą; plan przejrzany przez
      operatora (apply jest jego, nie CI)

## 11. CI i wdrożenie

- [ ] 11.1 `.github/workflows/checks.yml` — `agent` w filtrze `changes` i czwarty job
      (ruff, pyright, pytest, pytest -m db)
- [ ] 11.2 `.github/workflows/deploy-agent.yml` na wzór pozostałych trzech, zakończony
      sprawdzeniem wdrożonej aplikacji
- [ ] 11.3 Filtr terminala obejmuje zmiany w `modules/agent` wyłącznie tam, gdzie dotyczą
      kształtu wystawianego terminalowi

## 12. Dokumentacja i domknięcie

- [ ] 12.1 `modules/agent/README.md` — co, jak uruchomić, jak przetestować, jaki kontrakt
- [ ] 12.2 `CLAUDE.md` i `README.md` — czwarty moduł, port 8030, komendy, druga baza lokalna
- [ ] 12.3 `docs/architecture.md` — agent na schemacie jako konsument, nie peer
- [ ] 12.4 Uruchomić cały stos lokalnie i przeprowadzić rozmowę na każdym z trzech modeli;
      sprawdzić, że koszt pojawia się w zakładce
- [ ] 12.5 Sprawdzić strumień na wdrożonej aplikacji, nie tylko lokalnie (buforowanie i
      zerwanie po 230 s widać dopiero tam)
- [ ] 12.6 `openspec validate add-agent-chat --strict`
- [ ] 12.7 `review.md` przed archiwizacją
