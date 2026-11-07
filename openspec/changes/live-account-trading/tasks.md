## 1. Brama: tryb konta realnego

- [x] 1.1 `CAPITAL_ENVIRONMENT` (`demo`|`live`, domyślnie `demo`); walidator demo bez zmian, walidator `live`: dokładny host realny, `GATEWAY_ENV=production` i `SERVER_MODE`; `environment_of` zna host realny; testy odmów startu w obie strony
- [x] 1.2 `LIVE_ACCOUNT_ID` i `LIVE_ORDER_LIMITS` wymagane w `live`, odmowa startu z nazwą brakującej albo błędnej pozycji; testy
- [x] 1.3 Pula sesji w `live`: sesja domyślna na `LIVE_ACCOUNT_ID`, inne konto w `X-Capital-Account` to 400 przed dostawcą, konto nieznane dostawcy to odmowa każdego żądania rachunku
- [x] 1.4 Sprawdzenie granic na `POST /orders` (symbol z mapy, wielkość ≤ granica, wszystkie typy) przed dostawcą; zamknięcie, stopy i anulowanie bez granic; odmowa odróżnialna od odmowy dostawcy
- [x] 1.5 Trasy w `live`: tylko rachunek, wykonanie i warunki instrumentu; katalog, świece, historia, `/ws/stream`, `top-up`, `PUT /accounts/active` nieobecne (404); bez strumienia w lifespanie
- [x] 1.6 `POST /positions/close-all` tylko w `live`: każda pozycja i każde zlecenie oczekujące, skutek per element, niepowodzenie jednego nie zatrzymuje reszty
- [x] 1.7 Przeglądarka w `live`: odczyt rachunku i `close-all`, nic więcej; testy dostępu
- [x] 1.8 Ślad zapisów w `live`: wiersz przed i po (aplikacja wołającego, konto, rodzaj, symbol, kierunek, wielkość, typ, skutek; odmowa z nazwą granicy), bez poświadczeń; test, że klucze nie trafiają do logu
- [x] 1.9 `contract-sync`: migawka OpenAPI bramy w `trading-mcp` z nową trasą; README bramy (tryb realny, granice, wstrzymanie klucza u dostawcy)

## 2. trading-mcp: oczekiwane środowisko

- [x] 2.1 `EXPECTED_ENVIRONMENT` (`demo`|`live`, domyślnie `demo`), porównanie z `/capabilities` w obie strony przed portem; `test_demo_guard.py` rozszerzony, przypadek demo bez zmian
- [x] 2.2 Instancja `live` nie rejestruje `switch_active_account` ani `top_up_demo_account`; instrukcje serwera i opisy narzędzi zapisujących nazywają środowisko
- [x] 2.3 Odmowa granic z bramy jako odmowa narzędzia nazywająca granicę; sufit powierzchni narzędzi obejmuje oba warianty

## 3. Workbench: zespoły na koncie realnym

- [ ] 3.1 `trading.environment` w kontrakcie rewizji (domyślnie `demo`, stare rewizje czytają się jako demo); walidacja: realna bez konta odrzucona, realna z narzędziem spoza instancji realnej odrzucona z nazwą narzędzia i agenta
- [ ] 3.2 `TEAMS_LIVE_TRADING_MCP_URL` i `_API_KEY` w `teams/config.py` (+ `PRIVATE_HOSTS`, `.env.example`); drugi klient MCP; zespół realny bierze narzędzia rachunku tylko z niego
- [ ] 3.3 Przebieg realny bez skonfigurowanego serwera odmówiony przed pierwszym agentem; konto rewizji sprawdzane na liście kont instancji realnej
- [ ] 3.4 Środowisko w wierszu śladu wywołania zapisującego (migracja `teams`, jeśli kolumna) i w odczycie przebiegu
- [ ] 3.5 Test warstw: pakiet `agent` nie czyta ustawień serwera konta realnego; test, że narzędzia rozmowy pochodzą wyłącznie z instancji demo
- [ ] 3.6 `contract-sync` dla kontraktu zespołów; terminal: wybór środowiska w edytorze rewizji i środowisko w widoku przebiegu

## 4. Terminal: konto realne

- [ ] 4.1 `VITE_LIVE_GATEWAY_HTTP` (brak = brak sekcji), klient odczytu konta realnego, proxy w dev
- [ ] 4.2 Sekcja konta realnego na ekranie rachunku: saldo, pozycje, zlecenia oczekujące, odświeżanie, błąd odczytu powiedziany wprost, wyraźne odróżnienie od demo
- [ ] 4.3 „Zamknij wszystko” z potwierdzeniem (liczba pozycji i zleceń) i skutkiem per element; trzy testy widoku (zamknięcie, rezygnacja, częściowa odmowa)

## 5. Claude Code i agent z Telegrama

- [ ] 5.1 `scripts/claude-mcp.sh`: serwer `tc-trading-live` pod `/trading-live/mcp`; README: nie dodawać jego narzędzi zapisujących do listy dozwolonych bez pytania
- [ ] 5.2 `claude-agent`: serwer `tc-trading-live`, `AGENT_LIVE_ACCOUNT_WRITES` (domyślnie wyłączone, niezależne od `AGENT_ACCOUNT_WRITES`); `CLAUDE.md` agenta: potwierdzenie z kontem realnym, instrumentem, kierunkiem i wielkością; testy renderowania uprawnień

## 6. Wdrożenie

- [ ] 6.1 `docker-compose.yml`: `gateway-live` i `trading-mcp-live` w profilu `live`, sieci `live-core` i `live-tools` (workbench tylko w `live-tools`); test compose: żadna z nich nie ma `ports:`, workbench nie jest w `live-core`
- [ ] 6.2 `Caddyfile`: `/trading-live/*` na hoście API, `/live/*` na hoście bramy (bez `/ws/stream`), nagłówki krawędzi
- [ ] 6.3 `assemble_env.py` i `env.required`: przy `LIVE_TRADING=on` komplet sekretów realnych i `COMPOSE_PROFILES=live`, odmowa przy kluczu bramy realnej równym demo; bez `on` nic nie wymagane; testy
- [ ] 6.4 `docs/architecture.md` („The order path”): druga para procesów; CLAUDE.md: wiersz o konto realnym w tabeli modułów i w „Things that will bite you”

## 7. Uruchomienie na serwerze (operator i próba)

- [ ] 7.1 Operator: klucz API na koncie realnym (2FA, data ważności), `LIVE_ACCOUNT_ID`, `LIVE_ORDER_LIMITS` z najmniejszą wielkością, sekrety w `vps`, `LIVE_TRADING=on`
- [ ] 7.2 Wdrożenie i `deploy-watch`; terminal pokazuje konto realne; Claude Code czyta pozycje przez `/trading-live/mcp`
- [ ] 7.3 Odczyt `/accounts/preferences` konta realnego i demo (hedging, dźwignie), wynik w README bramy; sprawdzenie, czy klucz demo loguje się na host realny
- [ ] 7.4 Jedno zlecenie o najmniejszej wielkości z Claude Code, zlecenie ponad granicę (odmowa), zamknięcie przez „zamknij wszystko”; wiersze logu przed i po; obserwacja 429 przy pracy archiwum
- [ ] 7.5 `review.md`; archiwizacja po `operator-agent-on-telegram` (inaczej `claude-agent-access` powstanie bez `## Purpose`)
