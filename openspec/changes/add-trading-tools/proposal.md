## Why

Faza 1 dała zespół, który da się złożyć, uruchomić i rozliczyć — i który kończy pracę
**rekomendacją zapisaną w śladzie**. Rekomendacji nie da się ocenić: nie wiadomo, po jakiej
cenie zespół wszedłby, czy jego stop przetrwałby ruch i ile z tego zostałoby po tygodniu.
Bez skutku na rachunku porównywanie wariantów zespołu opiera się na czytaniu ich prozy.

Ta zmiana daje zespołowi rękę: narzędzia, którymi składa zlecenia na koncie demo, i granice,
w których wolno mu tego użyć. Handel wchodzi **osobnym modułem**, nie rozszerzeniem
`market-mcp` — tamten ma w specyfikacji zapisane, że nie publikuje narzędzia zapisującego, i
ta granica zostaje tam, gdzie jest.

## What Changes

- **Nowy moduł `modules/trading-mcp`** — szósty moduł, port 8060, serwer MCP nad
  `capital-gateway`. Publikuje narzędzia czytające rachunek (pozycje, zlecenia oczekujące,
  saldo) i **narzędzia zapisujące**: złożenie zlecenia `MARKET`/`LIMIT`/`STOP`, zamknięcie
  pozycji, zmiana dołączonych stopów, anulowanie zlecenia oczekującego.
- Moduł pracuje **wyłącznie z kontem demo**: pyta gateway o środowisko, zanim wystawi
  narzędzie zapisujące, i odmawia startu, gdy odpowiedź nie mówi „demo".
- **Wynik zlecenia jest rozliczony albo nazwany jako nierozliczony** — nigdy zgadnięty.
  Narzędzie zapisujące nie ponawia zlecenia po własnej awarii: powtórzone zlecenie jest
  drugą pozycją, nie tą samą.
- **`market-mcp` nie zmienia się w niczym.** Zapis dostaje własny moduł, własną tożsamość i
  własną listę wołających, w której jest `teams` i nie ma `agent`.
- **`teams` rozmawia z dwoma serwerami narzędzi**, nie z jednym. Definicja zespołu dalej
  wskazuje narzędzia po nazwie i dalej nie trzyma ich opisów; nazwa ogłoszona przez oba
  serwery naraz jest odmową nazywającą oba, a nie cichym wyborem jednego.
- **Zespół składa zlecenia sam** — narzędzie zapisujące trafia do pętli agenta tą samą drogą
  co czytające, komu definicja je przypisała.
- **Granice handlowe, bliźniaczo do granic kosztu**: liczba zleceń na przebieg i liczba
  zleceń dobowa na zespół, sprawdzane **przed** wywołaniem narzędzia zapisującego, w kodzie,
  nie w prompcie. Przekroczenie zatrzymuje przebieg ze statusem i powodem. Każda z nich jest
  **pomijalna, a pominięta znaczy „bez ograniczenia"** — moduł nie podstawia domyślnych i nie
  trzyma w kodzie sufitu, którego operator nie może podnieść. Przed skutkiem nieodwracalnym
  chroni tu konto demo wymuszone u gatewaya, a nie liczba, której nie da się zmienić.
- **Ślad handlowy w bazie `teams`**: wiersz na każde wywołanie zapisujące — przebieg, agent,
  symbol, kierunek, wielkość, poziom, skutek i identyfikator zlecenia od providera. Jedna
  rewizja Alembica.
- **Terminal**: zlecenia przebiegu widoczne na monitorze przy agencie, który je złożył, oraz
  granice handlowe w panelu zespołu.
- **Infrastruktura**: App Service i rejestracja Entra dla `trading-mcp`, dostęp do
  `gateway-api-key` w Key Vault, adresy wyjściowe modułu w zaporze `capital-gateway`,
  `allowed_applications` modułu ograniczone do tożsamości `teams`, ustawienia
  `TRADING_MCP_URL`/`TRADING_MCP_SCOPE` w `teams`. CI: job w `checks.yml` i
  `deploy-trading-mcp.yml`.

**Poza zakresem tej zmiany, świadomie:** scheduler i triggery (faza 3), analityka porównawcza
rewizji i automatyczne układanie grafu (faza 4), konto rzeczywiste w jakiejkolwiek postaci
oraz dostęp do handlu dla modułu `agent` — rozmowa operatora z modelem zostaje rozmową bez
skutków na rachunku.

**Równoległość z fazą 3 jest wymogiem tej zmiany, nie życzeniem.** Obie fazy wychodzą z
`feat/teams-module` i wracają do niego. Punkty styku są dwa i są znane: `teams/contract.py`
(obie dokładają modele, żadna nie zmienia istniejących) oraz łańcuch rewizji Alembica w
`teams` — ta zmiana bierze najbliższą wolną rewizję, faza 3 dokłada swoją za nią.

## Capabilities

### New Capabilities
- `trading-mcp-tools`: co moduł publikuje — narzędzia czytające rachunek i zapisujące,
  czego w zestawie nie ma, i czym różni się odmowa narzędzia od awarii dostępu.
- `trading-mcp-execution`: rozliczanie skutku zlecenia, zakaz ponawiania po własnej awarii i
  to, co narzędzie oddaje modelowi, gdy potwierdzenie nie przyszło na czas.
- `trading-mcp-upstream-access`: jak moduł przedstawia się `capital-gateway`, dlaczego bez
  poświadczenia nie wstaje i skąd wie, że pracuje na koncie demo.
- `trading-mcp-transport`: kto ma prawo wołać moduł, jak sprawdza się jego zdrowie bez sesji
  MCP i dlaczego lista wołających jest imienna.
- `teams-trading`: granice handlowe zespołu, ich sprawdzanie przed wywołaniem zapisującym i
  ślad złożonych zleceń.

### Modified Capabilities
- `teams-tool-access`: moduł łączy się z więcej niż jednym serwerem narzędzi; kolizja nazw
  między serwerami jest odmową; nieosiągalny serwer zapisu zatrzymuje przebieg tak samo jak
  serwer odczytu.
- `teams-catalogue`: definicja zespołu niesie granice handlowe, a zapis rewizji nigdy nie
  jest odmawiany z powodu granicy pominiętej — także przy narzędziu zapisującym.
- `teams-runs`: przebieg zatrzymany granicą zleceń ma własny powód zatrzymania, odróżnialny
  od granicy kosztu.
- `terminal-teams`: monitor przebiegu pokazuje złożone zlecenia przy agencie, a panel zespołu
  pozwala ustawić granice handlowe.

Nie zmieniają się — i to jest sprawdzone, nie założone: `market-mcp-tools` (zapis nigdy nie
trafia do tamtego zestawu, więc jego granica zostaje literalnie ta sama), `capital-trading` i
`capital-access-control` (drugi wołający gatewaya to wpis w zaporze i poświadczenie, a nie
inne zachowanie modułu — tak samo jak drugi wołający `market-mcp` w fazie 1).

## Impact

**Nowy kod:** `modules/trading-mcp/` w całości — pakiet, `pyproject.toml`, `Dockerfile`,
`.env.example`, testy, snapshot kontraktu gatewaya na wzór `market-mcp/contract/`. Bliźniaki
kopiowane z `market-mcp`, nie importowane: `config.py`, `client.py`, `errors.py`,
`network_identity.py`, `server.py`, `__main__.py`.

**Zmieniany kod:** `modules/teams` — `config.py` (drugi serwer narzędzi), `tools/`
(rejestr dwóch sesji, kolizja nazw, narzędzia zapisujące), `runner/` (granica zleceń jako hak
przed wywołaniem, zapis wiersza po nim), `contract.py`, `store.py`, `validation.py`, jedna
rewizja `migrations/`. `modules/terminal` — widok przebiegu i panel zespołu, przegenerowany
`contract.teams.generated.ts`.

**Infrastruktura:** `infra/app-service.tf` (szósta aplikacja na planie B2 — pomiar pamięci
zrobiono przy czterech, alarm `plan_memory` jest tym, co to wyłapie), `infra/entra.tf`,
zapora `capital-gateway`, polityka Key Vault.

**CI i dokumentacja:** `.github/workflows/checks.yml`, nowy `deploy-trading-mcp.yml`,
`scripts/dev.sh` i `scripts/dev.ps1` (moduł w kolejności startu, port 8060), `README.md`,
`docs/architecture.md`, `CLAUDE.md`.
