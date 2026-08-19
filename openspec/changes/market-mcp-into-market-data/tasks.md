## 1. Zależności i miejsce na narzędzia

- [x] 1.1 Dodać `mcp==1.27.0` i `tc-mcp-kit` do `modules/market-data/pyproject.toml`, przeliczyć lock, sprawdzić rozwiązanie wobec istniejących zależności
- [x] 1.2 Dodać `market-data` do tabeli konsumentów w `packages/tc-mcp-kit/README.md`
- [x] 1.3 Utworzyć `market_data/tools/` i przenieść `reduce.py`, `uncertainty.py`, `errors.py` wraz z ich testami — bez zmian w treści

## 2. Narzędzia sięgają po dane wywołaniem funkcji

- [x] 2.1 Przenieść `tools/_shared.py` — zastąpić `raise_for_status` podnoszeniem odmowy z warstwy domenowej, zachować `resolve_window`, `PERIOD_SECONDS` i adnotacje `READ_ONLY`
- [x] 2.2 Przenieść `tools/pairs.py` i `tools/instruments.py` na odczyt ze `store` i katalogu instrumentów zamiast `GET /pairs` i `GET /instruments/search`
- [x] 2.3 Przenieść `tools/candles.py` na odczyt ze `store` zamiast `GET /candles/{symbol}`, `/forming` i `/coverage/{symbol}`
- [x] 2.4 Przenieść `tools/indicators.py` na katalog i komputery wskaźników zamiast `GET /indicators` i `POST /indicators/{symbol}`
- [x] 2.5 Wziąć w narzędziach wskaźnikowych ten sam semafor `indicator_limiter`, którego używa router — z testem, że sufit równoczesności obowiązuje obiema drogami
- [x] 2.6 Przenieść `resources.py` (trzy zasoby MCP i prompt `analyze-symbol`)
- [x] 2.7 Przenieść testy narzędzi wraz z `conftest.py` dokładającym walidację odpowiedzi wobec `outputSchema`
- [x] 2.8 Przenieść `test_tool_surface.py` z sufitem 19 700 znaków bez zmiany wartości; potwierdzić zmierzoną wielkość po przeprowadzce

## 3. Montaż `/mcp`

- [x] 3.1 Dodać `market_data/mcp_app.py` budujący serwer MCP, rejestrujący narzędzia i wołający `slim_tool_schemas`
- [x] 3.2 Zamontować aplikację MCP pod `/mcp` w `create_app()`, poniżej `telemetry.configure()`; test, że import FastAPI nie wywędrował powyżej linii konfigurującej telemetrię
- [x] 3.3 Test, że lista narzędzi pod `/mcp` zawiera dokładnie te same nazwy co dotąd

## 4. Autoryzacja per wołający

- [x] 4.1 Dodać warstwę ASGI z zapisem trasa → uprawnieni wołający; surowy ASGI, nie `BaseHTTPMiddleware`, z testem sprawdzającym tę formę
- [x] 4.2 Ustawienia z identyfikatorami aplikacji wołających narzędzia i wołających REST; puste lokalnie, gdy wymóg tożsamości jest wyłączony
- [x] 4.3 Wypisać trasy wyjęte spod wymogu tożsamości (`/ping`, `/ws/candles`) jako pozycję zapisu; obsłużyć scope `websocket` jawnie
- [x] 4.4 Test odmowy dla każdej pary „tożsamość — powierzchnia, do której nie ma prawa", w tym wołający narzędzi na `POST /pairs` i `DELETE /pairs/{symbol}`
- [x] 4.5 Test, że trasa nieznana zapisowi jest odmawiana, nie przepuszczana
- [x] 4.6 Test, że trasa niosąca dane dopisana do listy wyjętych spod tożsamości wywraca testy

## 5. Konsumenci i runner dev

- [ ] 5.1 `scripts/dev.py`: usunąć `market-mcp` z tabeli usług i port 8040, przestawić doradę o `MARKET_MCP_URL` na nowy adres; testy `scripts/` zielone
- [ ] 5.2 `.env.example` w `agent` i `teams` — nowy adres i zakres, reguła „oba albo żaden" bez zmian
- [ ] 5.3 Uruchomić stack lokalnie i potwierdzić, że agent widzi narzędzia bez `market-mcp`

## 6. Infrastruktura i CI

- [ ] 6.1 `infra/app-service.tf`: dopisać `agent` i `teams` do `allowed_applications` archiwum; przestawić `MARKET_MCP_URL` i `MARKET_MCP_SCOPE` u obu modułów
- [ ] 6.2 `.github/workflows/checks.yml`: usunąć job `market-mcp` i jego filtr; potwierdzić 13 → 12 jobów
- [ ] 6.3 `terraform fmt` i `validate` na obu rootach

## 7. Usunięcie modułu — dopiero po działającej nowej drodze

- [ ] 7.1 Usunąć `modules/market-mcp/` w całości
- [ ] 7.2 Usunąć `.github/workflows/deploy-market-mcp.yml`
- [ ] 7.3 `infra/app-service.tf`: usunąć `azurerm_linux_web_app.market_mcp`, `module.market_mcp_easy_auth`, `data.azuread_service_principal.market_mcp_managed_identity`, `output market_mcp_hostname` i lokalne `market_mcp_*`

## 8. Dokumentacja

- [ ] 8.1 `CLAUDE.md`: mapa modułów, tabela komend, porty, ustawienia — oraz przepisane uzasadnienie istnienia `tc-mcp-kit`, które dziś opiera się na tym, że biorą go wyłącznie moduły bez bazy danych
- [ ] 8.2 `docs/architecture.md`: `market-mcp` znika z diagramu i z akapitu o kopiach kontraktu; opisać, że agent sięga po narzędzia archiwum wprost
- [ ] 8.3 `README.md` i `modules/market-data/README.md`: nowa powierzchnia narzędziowa i jej autoryzacja
- [ ] 8.4 `docs/rachunek-po-refactorze.html`: A(market) jako wykonane, z liczbami zmierzonymi po fakcie zamiast deklarowanych
