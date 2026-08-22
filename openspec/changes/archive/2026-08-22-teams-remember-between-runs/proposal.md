## Why

Zespół kończy przebieg i zapomina wszystko poza śladem: `Briefing` nie niesie historii, agent widzi
wyłącznie wypowiedzi poprzedników, a `ToolRound` żyje tyle co tura. Dwa przebiegi tego samego zespołu
zaczynają więc od zera — ten sam wniosek trzeba wypracować i opłacić drugi raz, a to, czego zespół
nauczył się w poniedziałek, nie istnieje we wtorek.

Ta zmiana daje zespołowi notatki, które przeżywają przebieg, i operatorowi decyzję, **który agent** może
je pisać, a który tylko czytać. Jest to świadome odwrócenie zapisanej własności modułu, nie dopisanie
brakującej funkcji — dlatego idzie przez proposal, a nie przez samą gałąź.

## What Changes

- Nowa tabela `team_memories` w bazie `teams` (migracja `0008`): wpis należy do **zespołu**, nie do
  rewizji i nie do przebiegu, i raz zapisany się nie zmienia.
- Dwa nowe narzędzia — `memory_read` i `memory_write` — ogłaszane przez **lokalne źródło w procesie**,
  trzecie obok `market-mcp` i `trading-mcp`. Bez portu, bez sieci, na wzór narzędzi rysunków w rozmowie.
- Uprawnienia per agent **przez mechanizm, który już jest**: `AgentDefinition.tools`. Agent z przypisanym
  `memory_write` pisze, z `memory_read` czyta, bez żadnego z nich — pamięci nie widzi. Żadnego nowego pola
  w definicji, więc żadna zapisana rewizja nie wymaga przepisania.
- **Domknięcie istniejącej luki**: dziś agent jest ograniczony wyłącznie tym, co mu *podano* — wywołanie
  nieprzypisanej nazwy nie jest odmawiane. Przy „może czytać, nie może pisać" to musi trzymać także
  wtedy, gdy model zgadnie nazwę, więc wywołanie zaczyna sprawdzać przydział. Chroni to również narzędzia
  handlowe.
- Trasy dla operatora: `GET /teams/{team_id}/memory` i `DELETE /teams/{team_id}/memory/{entry_id}`.
  Usuwanie należy do operatora i tylko do niego — agent nie ma narzędzia, które kasuje.
- Panel notatek zespołu w terminalu: odczyt i usunięcie pojedynczego wpisu.
- Trzy sufity zapisane jako stałe modułu, nie ustawienia: długość wpisu, liczba wpisów oddawanych przy
  odczycie, liczba zapisów w jednym przebiegu.

Nie jest to transkrypt i nie ma nim się stać: wpis powstaje wyłącznie decyzją agenta — wywołaniem
narzędzia, widocznym w śladzie jak każde inne. `Briefing` zostaje bez historii.

## Capabilities

### New Capabilities
- `teams-memory`: czym jest pamięć zespołu — do czego należy wpis, dlaczego stoi obok rewizji, co go
  nie zmienia, jakie ma sufity, kto go czyta i kto usuwa.

### Modified Capabilities
- `teams-tool-access`: rejestr narzędzi przestaje być listą wyłącznie serwerów sieciowych — dochodzi
  źródło w tym samym procesie, dla którego warunek „adres zdalny wymaga tożsamości" nie ma sensu i musi
  być powiedziane, że go nie dotyczy. Drugie: przypisanie narzędzia agentowi zaczyna obowiązywać przy
  **wywołaniu**, nie tylko przy doborze.
- `teams-runs`: przebieg dostaje kontekst, którego dziś nie ma — zespół i właściciela — bo narzędzie
  kluczowane zespołem nie ma z czego ich wziąć; oraz zdanie o tym, że pamięć zapisana w przebiegu
  przerwanym zostaje.
- `terminal-teams`: operator czyta notatki zespołu i usuwa pojedynczy wpis.

## Impact

- `modules/workbench`: migracja `migrations/teams/versions/0008_*`, `teams/store/memory.py`,
  `teams/tools/memory.py`, `teams/tools/client.py` i `teams/tools/assignment.py` (źródła lokalne w
  rejestrze i w obu funkcjach `announced_*`), `teams/routers/memory.py`, `teams/surface.py`,
  `teams/runner/{starter,engine,loop}.py` (przewleczenie `team_id` i `owner_principal`), `teams/contract.py`.
- `modules/terminal`: kontrakt teams jest **generowany** — `pnpm contract:generate` po zmianie tras,
  inaczej `contract:check` wywraca CI; nowy panel w `src/teams/`.
- Bez zmian: `agent/`, `teams_tools/`, `packages/`, `infra/`. Pamięć nie wchodzi w tej zmianie do
  rozmowy operatora z modelem — to osobna decyzja z własnym kosztem sufitu powierzchni narzędzi.
- `review.md` powstaje przy zamknięciu zmiany, nie teraz.
