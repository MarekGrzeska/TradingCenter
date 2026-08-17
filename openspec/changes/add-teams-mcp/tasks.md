## 1. Rozstrzygnięcie, na którym stoi reszta

- [x] 1.1 Sprawdzić na działającym `agent` w Azure, czy Easy Auth przepuszcza do procesu
  oryginalny nagłówek `Authorization` — tymczasowa trasa diagnostyczna albo odczyt z logu,
  usuwana zaraz po pomiarze

  **Świadomie odłożone, nie zrobione.** Wymaga wdrożenia trasy diagnostycznej na produkcję,
  a to jest czynność wychodząca na zewnątrz, której agent nie wykonuje bez operatora.
  Zamiast tego droga główna z D2 jest zaimplementowana, a jej awaria degraduje się do jawnej
  odmowy z powodem — czego i tak wymaga `teams-mcp-authorship` („Brak tożsamości operatora
  zatrzymuje zapis"). Nic nie zapisze się na złego właściciela; w najgorszym razie nie zapisze
  się nic. Do wykonania przed wdrożeniem grupy 7, opisane w `review.md`.
- [x] 1.2 Zapisać wynik w `design.md` jako pomiar z datą; przy wyniku negatywnym przejść na
  alternatywę A z D2 i poprawić `design.md` oraz zadania grupy 5, zanim ruszy grupa 2

  Pomiaru nie ma, więc `design.md` dostaje adnotację o tym, że D2 stoi na założeniu
  nieprzetestowanym w Azure, z gotowym wariantem awaryjnym.

## 2. Szkielet modułu

- [x] 2.1 `modules/teams-mcp/` — `pyproject.toml`, `uv.lock`, `ruff`, `pyright`, układ pakietu
  wzorem `modules/trading-mcp`
- [x] 2.2 `config.py` — `TEAMS_URL`, `TEAMS_SCOPE`, `TEAMS_REQUEST_TIMEOUT_SECONDS`, port
  **8070**, host, `REQUIRE_AUTHENTICATED_PRINCIPAL`
- [x] 2.3 Odmowa startu przy adresie zdalnym bez tożsamości i przy obu trybach naraz
  (`teams-mcp-upstream-access`)
- [x] 2.4 Transport wyłącznie sieciowy, bez wariantu uruchamianego jako proces potomny
  (`teams-mcp-transport`)
- [x] 2.5 `/health` bez poświadczenia, nieujawniające niczego o katalogu
- [x] 2.6 Testy na 2.3–2.5

## 3. Rozmowa z `teams`

- [x] 3.1 Klient HTTP do `teams` z granicą czasu i bez ponawiania zapisu
- [x] 3.2 Trzy wyniki, nie dwa: odpowiedź, odmowa `teams` z jego własnym powodem,
  niedostępność
- [x] 3.3 Migawka kontraktu `teams` w `contract/teams.openapi.json` i `scripts/contract.py
  check`, wzorem obu istniejących serwerów MCP
- [x] 3.4 Testy przeciw dublerowi `teams`: odmowa, przekroczenie czasu, brak ponowienia zapisu

## 4. Katalog narzędzi

- [x] 4.1 Narzędzia czytające: `list_teams`, `read_team`, `list_runs`, `read_run`,
  `list_schedules` — oznaczone jako czytające
- [x] 4.2 Narzędzia zapisujące: `create_team`, `revise_team`, `run_team`, `schedule_team` —
  oznaczone jako zmieniające stan
- [x] 4.3 `create_team` zakłada zespół wraz z pierwszą rewizją jednym wywołaniem
- [x] 4.4 `revise_team` przyjmuje poprawkę bez przepisywania niezmienionych ról
- [x] 4.5 `read_run` odpowiada także dla przebiegu trwającego, mówiąc że nie jest zakończony
- [x] 4.6 `schedule_team` **nie** przyjmuje `unattended_ack` jako argumentu (D4)
- [x] 4.7 `schedule_team` mówi, gdy zegar `teams` jest wyłączony ustawieniem, i mimo to zapisuje
- [x] 4.8 Opisy narzędzi niosą warunki odmowy — granicę dobową kosztu i granice handlowe —
  oraz katalog modeli i nazwy narzędzi, które wolno wpisać w definicję
- [x] 4.9 Testy: każde narzędzie ma test odpowiedzi i test odmowy; katalog rozróżnia odczyt
  od zapisu

## 5. Tożsamość operatora

- [x] 5.1 Przyjęcie przeniesionego tokenu operatora osobnym nagłówkiem i przedstawienie go
  jako `Authorization` w wywołaniu do `teams`
- [x] 5.2 Odmowa każdego narzędzia — czytającego i zapisującego — gdy tożsamości operatora
  nie da się ustalić, z powodem nazywającym ten brak
- [x] 5.3 Tożsamość z argumentu narzędzia zignorowana albo odrzucona; nigdy użyta
- [x] 5.4 Token operatora nie trafia do logu, do śladu narzędzia ani do treści oddawanej
  modelowi — test przy `LOG_LEVEL=DEBUG`
- [x] 5.5 Wygasły token operatora daje niedostępność nazywającą wygasłe poświadczenie, nie
  puste odpowiedzi
- [x] 5.6 Testy `teams-mcp-authorship`: zespół powstaje na tożsamości operatora, cudzy jest
  nieodróżnialny od nieistniejącego, odmowa `teams` dociera jego słowami

## 6. `agent` uczy się drugiego serwera

- [x] 6.1 Rejestr serwerów narzędzi w `agent/tools/client.py`, kształt przeniesiony z
  `teams/tools/client.py` — kopiowany, nie importowany
- [x] 6.2 Ustawienia `TEAMS_MCP_URL`, `TEAMS_MCP_SCOPE`, `TEAMS_MCP_REQUEST_TIMEOUT_SECONDS`
  w `config.py` i `.env.example`; brak `TEAMS_MCP_URL` zostaje stanem wspieranym
- [x] 6.3 Konfiguracja i niedostępność każdego serwera niezależnie od drugiego; komunikat
  nazywa serwer, którego dotyczy (`agent-tool-access`)
- [x] 6.4 Przeniesienie tokenu wołającego do wywołań serwera zespołów
- [x] 6.5 Prompt wie, że te narzędzia istnieją i po co są — nowa rewizja promptu
- [x] 6.6 Agent mówi „nie mam teraz dostępu do katalogu zespołów", zamiast twierdzić, że
  zespół powstał, gdy serwer jest nieosiągalny
- [x] 6.7 Testy grupy 6, w tym jeden serwer odpowiadający przy drugim nieosiągalnym

## 7. Infrastruktura

- [x] 7.1 SKU planu na **B3**, `apply` operatora, odczyt pamięci po zmianie zapisany w
  `review.md` — **przed** zadaniem 7.2

  Kod napisany, `apply` **nie wykonany** — w tym repo `apply` jest robotą operatora, nigdy
  CI ani agenta. `plan` przechodzi: 5 do dodania, 6 do zmiany, 0 do usunięcia. Odczyt
  pamięci po zmianie SKU dopisze operator; kolejność „B3 przed wdrożeniem modułu" zostaje
  w `review.md` jako pierwszy krok wdrożenia.
- [x] 7.2 App Service `teams-mcp`, tożsamość zarządzana, Easy Auth z `agent` jako jedynym
  wołającym, `/health` poza uwierzytelnieniem
- [x] 7.3 Tożsamość `teams-mcp` w `allowed_applications` po stronie `teams`
- [x] 7.4 `TEAMS_MCP_URL` i `TEAMS_MCP_SCOPE` w ustawieniach `agent` — jako **ostatni** krok
  wdrożenia (Migration Plan, punkt 5)
- [x] 7.5 `terraform fmt`, `validate`, `plan` bez `azuread_*` poza tym, co operator stosuje sam

## 8. CI i wdrożenie

- [x] 8.1 Job `teams-mcp` w `checks.yml` z filtrem po katalogu modułu
- [x] 8.2 Zmiana `teams/contract.py` wciąga job `teams-mcp` — migawka jest tam po to, żeby
  łapać rozjazd
- [x] 8.3 `deploy-teams-mcp.yml` — obraz do GHCR, wdrożenie, smoke check sięgający procesu
  przez `/health`, nie warstwy sterującej

## 9. Stos deweloperski i dokumentacja

- [x] 9.1 `teams-mcp` w `scripts/dev.sh` i `dev.ps1` — po `teams`, przed `agent`, z czekaniem
  na odpowiedź
- [x] 9.2 Ostrzeżenie przy starcie, gdy `agent` nie ma `TEAMS_MCP_URL`, wzorem istniejącego
  dla `MARKET_MCP_URL`
- [x] 9.3 `modules/teams-mcp/README.md`
- [x] 9.4 `CLAUDE.md`, `README.md`, `docs/architecture.md` — siódmy moduł, port 8070, nowa
  krawędź `agent` → `teams-mcp` → `teams`

## 10. Domknięcie

- [x] 10.1 Przebieg od końca do końca lokalnie: z czatu założyć zespół, zobaczyć go w zakładce
  Teams, uruchomić, przeczytać ślad, poprawić rolę na podstawie śladu, uruchomić ponownie

  Przejście przez prawdziwą sesję MCP do `teams-mcp` i dalej do `teams` z prawdziwą bazą,
  skryptem odgrywającym to, co zrobi agent, minus model: 12 narzędzi, katalog modeli,
  założenie zespołu dwóch ról z krawędzią i granicą dobową, odczyt katalogu, poprawka
  jednej roli (rewizja 2, druga rola i granica nietknięte), harmonogram z ostrzeżeniem o
  zegarze. **Bez uruchomienia przebiegu** — kosztowałoby prawdziwe pieniądze na kluczu
  OpenAI, a operator śpi; ścieżka `run_team`/`read_run` jest pokryta testami przeciw
  dublerowi `teams`.
- [x] 10.2 Przebieg dowodzący własności: zespół założony z czatu jest widoczny i edytowalny w
  terminalu jako zespół tego samego operatora

  **Dowiedzione tylko w sensie lokalnym, i różnica jest istotna.** Lokalnie przed `teams`
  nie stoi Easy Auth, więc `teams` nie ma z czego wyprowadzić tożsamości z przeniesionego
  tokenu i zapisuje `anonymous` — dokładnie to samo, co zapisuje dla lokalnego terminala.
  Zespół założony przez narzędzia **jest** więc widoczny w lokalnym terminalu, i to
  dowodzi, że instalacja hydrauliczna działa: token jedzie, nagłówki się nie mieszają, nic
  nie ginie po drodze. Nie dowodzi kroku, na którym stoi cała decyzja D2 — że Easy Auth
  zamieni przeniesiony token na tożsamość operatora. To zostaje niesprawdzone razem z 1.1
  i jest opisane w `review.md`.
- [x] 10.3 `uv run pytest`, `ruff`, `pyright` w `teams-mcp` i w `agent`; `pnpm test` w
  terminalu, jeśli cokolwiek go dotknęło
- [x] 10.4 `review.md`
