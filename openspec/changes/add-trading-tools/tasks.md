## 1. Szkielet `trading-mcp`

- [ ] 1.1 Katalog `modules/trading-mcp/` z `pyproject.toml`, `README.md`, `.env.example`, `Dockerfile`
- [ ] 1.2 `config.py` — adres i poświadczenie gatewaya, tożsamość, port 8060, wymóg ustalonej tożsamości wołającego
- [ ] 1.3 Walidatory `Settings()`: tryb dostępu do gatewaya, odmowa startu bez poświadczenia
- [ ] 1.4 `server.py` i `__main__.py` — wyłącznie transport sieciowy, bez `stdio`
- [ ] 1.5 `network_identity.py` — odrzucenie żądania bez ustalonej tożsamości wołającego
- [ ] 1.6 `/health` bez sesji MCP i bez poświadczenia, odpowiadające wyłącznie stanem modułu
- [ ] 1.7 Testy: odmowa startu przy każdej niespójnej konfiguracji z 1.3; `/health` nie ujawnia rachunku ani narzędzi

## 2. Dostęp do `capital-gateway`

- [ ] 2.1 `client.py` — poświadczenie na żądanie, górna granica czasu, brak ponawiania żądań zmieniających stan
- [ ] 2.2 Sprawdzenie środowiska przez `GET /capabilities` przy starcie; odmowa startu poza demo
- [ ] 2.3 Powtórzenie sprawdzenia po odzyskaniu połączenia, przed obsłużeniem narzędzia zapisującego
- [ ] 2.4 `errors.py` — rozdzielenie odmowy narzędzia od awarii dostępu; poświadczenie poza logami i odpowiedziami
- [ ] 2.5 Snapshot kontraktu gatewaya w `contract/` i `scripts/contract.py check` na wzór `market-mcp`
- [ ] 2.6 Testy: odmowa startu przy środowisku innym niż demo, timeout jako awaria dostępu, brak ponowienia po awarii

## 3. Zestaw narzędzi

- [ ] 3.1 Narzędzia czytające rachunek: pozycje, zlecenia oczekujące, saldo
- [ ] 3.2 Narzędzia zapisujące: złożenie zlecenia MARKET/LIMIT/STOP, zamknięcie pozycji, zmiana stopów, anulowanie zlecenia oczekującego
- [ ] 3.3 Adnotacje MCP zgodne z tym, co narzędzie robi — zapisujące oznaczone jako zmieniające stan
- [ ] 3.4 Odmowy przed dotknięciem rachunku: brak poziomu przy LIMIT/STOP, nieznany albo niehandlowalny symbol
- [ ] 3.5 Opis zestawu wskazujący archiwum jako miejsce pytań o rynek; brak narzędzi o cenach i świecach
- [ ] 3.6 Testy: lista narzędzi z adnotacjami, każda odmowa z 3.4, brak narzędzia rynkowego w zestawie

## 4. Wynik zlecenia

- [ ] 4.1 Mapowanie wyniku gatewaya na wynik narzędzia — rozliczony albo jawnie nierozliczony z referencją
- [ ] 4.2 Odrzucenie providera jako wynik odrzucony z jego powodem, nie jako awaria
- [ ] 4.3 Awaria dostępu jako wynik nazywający nieznany skutek
- [ ] 4.4 Testy: nierozliczone potwierdzenie nie jest raportowane jako wykonanie; awaria nie jest raportowana jako odrzucenie

## 5. Dwa serwery narzędzi w `teams`

- [ ] 5.1 `config.py` — `TRADING_MCP_URL` i `TRADING_MCP_SCOPE` obok istniejących, każdy ze swoim sprawdzeniem trybu
- [ ] 5.2 Rejestr serwerów w miejsce jednego `ToolServer`; sesja i `list_tools()` per serwer
- [ ] 5.3 `plan_tools()` rozwiązujący przypisania wobec sumy ogłoszeń, z zapamiętaniem, z którego serwera pochodzi narzędzie
- [ ] 5.4 Odmowa przy kolizji nazw — przy zapisie rewizji i przy uruchomieniu przebiegu, z nazwami obu serwerów
- [ ] 5.5 Pytany jest tylko ten serwer, z którego ktokolwiek w definicji ma narzędzie
- [ ] 5.6 `GET /tools` ogłaszające narzędzia obu serwerów wraz z oznaczeniem zapisujących
- [ ] 5.7 Testy: niespójna konfiguracja drugiego serwera odmawia startu; nieosiągalny serwer zapisu nie zatrzymuje zespołu bez zapisu; kolizja nazw odmawia w obu miejscach

## 6. Granice handlowe

- [ ] 6.1 Granice handlowe w `TeamDefinition` — maksymalna wielkość zlecenia, liczba zleceń na przebieg, liczba dobowa
- [ ] 6.2 `validation.py` — odmowa zapisu rewizji z narzędziem zapisującym i bez granic, nazywająca agenta
- [ ] 6.3 Hak w pętli agenta sprawdzający granice przed wywołaniem narzędzia zapisującego
- [ ] 6.4 Wyczerpana liczba zleceń zatrzymuje przebieg statusem odróżnialnym od kosztu
- [ ] 6.5 Zlecenie ponad maksymalną wielkość jako odmowa wywołania, bez zatrzymania przebiegu
- [ ] 6.6 Sprawdzenie granicy dobowej przed utworzeniem przebiegu, liczone od północy UTC
- [ ] 6.7 Testy: rewizja sprzed tej zmiany pozostaje uruchamialna; zespół dobijający do granicy zostawia ślad; granica dobowa odmawia przed wywołaniem kogokolwiek

## 7. Ślad handlowy

- [ ] 7.1 Rewizja Alembica w `teams` z tabelą śladu handlowego (numer rewizji brany przy implementacji — patrz nota o fazie 3 na końcu)
- [ ] 7.2 Zapis wiersza przed wysłaniem wywołania; uzupełnienie o skutek po odpowiedzi
- [ ] 7.3 Skutek nieznany zapisany jako nieznany, nie jako nieudany
- [ ] 7.4 `contract.py` — kształt wiersza śladu handlowego i granic handlowych (wyłącznie dodanie modeli)
- [ ] 7.5 Trasa odczytu zleceń przebiegu, z filtrem właściciela jak reszta modułu
- [ ] 7.6 Testy `-m db`: migracja od zera dochodzi do rewizji czołowej; wiersz przeżywa przerwanie przebiegu

## 8. Terminal

- [ ] 8.1 `pnpm contract:generate` po zmianach w `teams/contract.py`
- [ ] 8.2 Granice handlowe w panelu zespołu; odmowa zapisu pokazana przy agencie
- [ ] 8.3 Narzędzia zapisujące odróżnione od czytających w wybieraku narzędzi
- [ ] 8.4 Zlecenia przebiegu przy agencie, który je złożył — symbol, kierunek, wielkość, skutek
- [ ] 8.5 Zlecenie o nieznanym skutku pokazane jako nieznane
- [ ] 8.6 Granica zleceń jako przyczyna zatrzymania, odróżniona od kosztu
- [ ] 8.7 `pnpm lint`, `typecheck`, `test`, `contract:check` przechodzą

## 9. Infrastruktura

- [ ] 9.1 Rejestracja Entra dla `trading-mcp` w `infra/entra.tf`
- [ ] 9.2 App Service w `infra/app-service.tf` — tożsamość, obraz, Easy Auth z `/health` poza wymaganiem
- [ ] 9.3 `allowed_applications` modułu ograniczone do tożsamości `teams`
- [ ] 9.4 Polityka Key Vault i odwołanie do `gateway-api-key` w ustawieniach aplikacji
- [ ] 9.5 Adresy wyjściowe `trading-mcp` w zaporze `capital-gateway`
- [ ] 9.6 `TRADING_MCP_URL` i `TRADING_MCP_SCOPE` w ustawieniach `teams`
- [ ] 9.7 Instrukcja dla operatora w `modules/trading-mcp/README.md` — `apply -target`, pełny `apply`, kolejność wdrożenia

## 10. CI i wdrożenie

- [ ] 10.1 Filtr i job modułu w `.github/workflows/checks.yml`
- [ ] 10.2 `.github/workflows/deploy-trading-mcp.yml` — obraz do GHCR, wdrożenie, smoke check pytający `/health`
- [ ] 10.3 `scripts/dev.sh` i `scripts/dev.ps1` — moduł w kolejności startu, port 8060
- [ ] 10.4 `README.md`, `docs/architecture.md` i `CLAUDE.md` — moduł w tabeli, na rysunku i w mapie

## 11. Domknięcie

- [ ] 11.1 Przykładowy zespół handlowy w katalogu jako punkt wyjścia dla operatora
- [ ] 11.2 Przebieg od końca do końca na uruchomionym stosie, zakończony zleceniem na koncie demo
- [ ] 11.3 `review.md`

## Nota o równoległości z fazą 3

Ta zmiana i faza 3 wychodzą z `feat/teams-module` i wracają do niego. Punkty styku są dwa:
`teams/contract.py` (7.4 — wyłącznie dodanie modeli) i łańcuch rewizji Alembica w `teams`
(7.1). Ta, która wyląduje w `feat/teams-module` druga, ustawia `down_revision` swojej migracji
na czoło zastane po merge'u pierwszej — bez `alembic merge`.
