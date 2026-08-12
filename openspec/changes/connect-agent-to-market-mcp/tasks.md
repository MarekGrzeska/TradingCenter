Kolejność grup jest kolejnością zależności, nie tylko porządkiem czytania: klient bez
konfiguracji nie ma dokąd pójść, węzeł narzędzi bez klienta nie ma czego zawołać, a zapis
bez pętli nie ma czego zapisać. Grupy 1–3 dają agenta, który woła narzędzia lokalnie;
dopiero grupa 5 wpuszcza go tam w produkcji.

**Zanim grupa 6 (archiwizacja) będzie w ogóle możliwa**: `add-agent-chat` MUST być
zarchiwizowane, bo `agent-chat` i `agent-usage` żyją dziś w jego katalogu zmiany, a nie w
`openspec/specs/` — delty MODIFIED tej zmiany nie mają się do czego przyłożyć. Sama
implementacja tego nie potrzebuje.

## 1. Dostęp do serwera narzędzi

- [x] 1.1 `agent/config.py` — `market_mcp_url` (domyślnie puste: brak narzędzi) i
  `market_mcp_scope`, z przełącznikiem trybu w kształcie, jaki ma `market-mcp/config.py`
  wobec archiwum: adres zdalny bez scope'u odmawia startu, scope przy pętli zwrotnej
  odmawia startu
- [x] 1.2 Testy `config.py`: adres zdalny bez tożsamości, pętla zwrotna bez tożsamości,
  oba naraz, adres nieustawiony jako poprawny stan „bez narzędzi"
- [x] 1.3 Zależność `mcp` w `pyproject.toml` (klient; ta sama biblioteka, której
  `market-mcp` używa po stronie serwera), `uv lock`
- [x] 1.4 `agent/tools/client.py` — sesja streamable http z serwerem narzędzi: nawiązanie,
  `tools/list`, wywołanie narzędzia, zamknięcie. Token z `DefaultAzureCredential` dla
  `market_mcp_scope`, gdy ustawiony; jeden log przy starcie nazywający fakt i scope, nigdy
  token
- [x] 1.5 Górna granica czasu wywołania, odróżnialna w wyniku od odmowy narzędzia
  (`agent-tool-access`, „Wołanie serwera narzędzi ma skończony czas")
- [x] 1.6 Katalog narzędzi pobierany raz na sesję z serwerem i trzymany w procesie, nie
  per tura — ten sam wybór, jaki `market-mcp` zrobił dla katalogu wskaźników
- [x] 1.7 Testy klienta przeciw podstawionemu serwerowi MCP: lista narzędzi, udane
  wywołanie, odmowa narzędzia, przekroczenie czasu, serwer nieosiągalny
- [x] 1.8 Test: moduł startuje i odpowiada, gdy adres serwera nie jest ustawiony i gdy
  serwer nie odpowiada (`agent-tool-access`, „Brak serwera narzędzi nie odbiera agentowi
  mowy")
- [x] 1.9 `.env.example` i `README.md` modułu — oba ustawienia i to, co znaczy ich brak

## 2. Pętla narzędzi w grafie

- [ ] 2.1 `provider.py` — własne kształty żądania wywołania i jego wyniku, obok
  `TextDelta` i `UsageReport`; klasy langchaina zostają tam, gdzie były, i nie wychodzą
  poza ten plik
- [ ] 2.2 `provider.py` — narzędzia przekazane modelowi przy wywołaniu (`bind_tools` ze
  schematów z `tools/list`, nie z listy wpisanej tutaj) i rozpoznanie prośby o wywołanie
  w strumieniu
- [ ] 2.3 `graph.py` — węzeł `tools`, krawędź warunkowa z `model` (`tools` albo `END`) i
  krawędź powrotna `tools → model`
- [ ] 2.4 Sufit ośmiu wywołań na turę, liczbą w kodzie; po jego osiągnięciu model dostaje
  to jako wynik i ma jeszcze obrót na odpowiedź (`agent-tools`, „Tura ma sufit wywołań
  narzędzi")
- [ ] 2.5 Odmowa narzędzia wraca do modelu jako wynik ze zdaniem serwera; awaria dostępu
  wraca jako wynik nazywający awarię; ani jedna, ani druga nie kończy tury błędem
- [ ] 2.6 Wynik narzędzia żyje w stanie grafu przez turę i nie wchodzi do historii tury
  następnej (design.md, „Wynik narzędzia żyje jedną turę")
- [ ] 2.7 Testy grafu przeciw podstawionemu dostawcy i podstawionemu klientowi: tura bez
  narzędzia, tura z jednym, tura z trzema, tura wchodząca w sufit, tura z odmową i
  poprawionym żądaniem, tura z niedostępnym serwerem

## 3. Zapis wywołań i zużycia

- [ ] 3.1 Migracja: tabela wywołań narzędzi — sesja, wiadomość agenta, numer obrotu,
  nazwa, argumenty, powodzenie, wynik albo powód odmowy, czas trwania, moment
- [ ] 3.2 `store.py` — zapis wywołań po `append_agent_message`, w tym samym miejscu co
  wiersze zużycia i z tego samego powodu: identyfikator wiadomości powstaje na końcu tury
- [ ] 3.3 `turn.py` — wiersz zużycia na każde wywołanie modelu w turze, wszystkie
  wskazujące tę samą wypowiedź agenta (`agent-usage`, „Tura z wywołaniem narzędzia")
- [ ] 3.4 Testy `db`: trzy wywołania w turze dają trzy zapisy o odtwarzalnej kolejności;
  wywołanie zakończone odmową też zostawia zapis; tura niepełna zapisuje to, co zdążyła
- [ ] 3.5 Test `db`: dwa wywołania modelu w turze dają dwa wiersze zużycia i sumę kosztu
  równą ich sumie — sprawdzone przez istniejące agregaty, nie przez nowy odczyt
- [ ] 3.6 Sprawdzić i zapisać w teście, że `agent/contract.py` nie zmienia się ani o pole:
  transkrypt czytany przez terminal jest ten sam co przed zmianą

## 4. Prompt

- [ ] 4.1 `prompt.py` — `v3`: agent ma narzędzia, dane pochodzą z archiwum zbierającego
  wybrane pary, brak świec nie jest ciszą rynku, cena bez momentu nic nie znaczy
- [ ] 4.2 Zakaz rekomendacji i zakaz podawania liczby, której agent nie dostał, przepisane
  wprost pod nowy stan rzeczy — ten drugi jest teraz sprawdzalny, bo agent liczby dostaje
- [ ] 4.3 Wariant promptu na turę bez narzędzi (serwer niedostępny), mówiący to, co prompt
  mówił zawsze (`agent-chat`, „Agent bez narzędzi mówi, że ich nie ma")
- [ ] 4.4 Test: `PROMPT_VERSION` podbite, a wiadomości sprzed zmiany dalej niosą swoją
  wersję

## 5. Wdrożenie i uruchomienie

- [ ] 5.1 `infra/app-service.tf` — client id tożsamości agenta w `allowed_applications`
  Easy Auth `market-mcp`, w miejsce zaślepki (`data.azuread_service_principal` po
  `principal_id`, ten sam wzór, którym market-mcp wchodzi do market-daty)
- [ ] 5.2 `infra/app-service.tf` — `MARKET_MCP_URL` i `MARKET_MCP_SCOPE` w
  `app_settings` aplikacji agenta; `terraform validate` i `fmt`
- [ ] 5.3 `scripts/dev.sh` i `dev.ps1` — agent dostaje `MARKET_MCP_URL` wskazujący na
  lokalny serwer; kolejność startu bez zmian, ale czekanie na `/health` market-mcp
  przestaje być formalnością
- [ ] 5.4 `CLAUDE.md`, `README.md`, `docs/architecture.md` — krawędź `agent → market-mcp`
  na diagramie, „No tools yet" usunięte z trzech miejsc, kolejność apply u operatora
  zapisana tam, gdzie ktoś jej poszuka
- [ ] 5.5 Przebieg całego stosu lokalnie: pytanie o cenę pary zbieranej, pytanie o parę
  niezbieraną, pytanie wymagające wskaźnika, pytanie przy zatrzymanym market-mcp

## 6. Domknięcie

- [ ] 6.1 `uv run ruff check .`, `uv run pyright`, `uv run pytest` w `modules/agent`
- [ ] 6.2 `review.md` — werdykt, uruchomione komendy, pokrycie wymagań, luki
- [ ] 6.3 `openspec validate connect-agent-to-market-mcp --strict`
- [ ] 6.4 Pull request; archiwizacja dopiero po zarchiwizowaniu `add-agent-chat` (patrz
  nota na górze tego pliku)
