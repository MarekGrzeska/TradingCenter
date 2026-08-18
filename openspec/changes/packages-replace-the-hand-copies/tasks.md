## 1. Workspace i mechanizm, na jednym konsumencie

Cel tej grupy: udowodnić całą drogę — workspace, pakiet, obraz, CI, dokumentacja — zanim
dojdzie drugi moduł. Po niej `agent` bierze `tc-runtime`, a reszta repo stoi nietknięta.

- [x] 1.1 ~~`[tool.uv.workspace]` w katalogu głównym~~ → **`[tool.uv.sources]` w module.**
      Workspace zwija wszystkich członków do jednego `uv.lock` w rootcie; siedem modułów ma
      dziś siedem własnych locków, a wspólny znaczyłby, że bump zależności w jednym
      re-rozwiązuje pozostałe — wprost przeciwko celowi tej zmiany. Zależność ścieżkowa
      (`tc-runtime = { path = "../../packages/tc-runtime", editable = true }`) daje to samo
      dzielenie kodu, zostawiając każdemu modułowi jego lock. Zapisane w `design.md`, D3
- [x] 1.2 Utworzyć `packages/tc-runtime/` (pyproject, pakiet `tc_runtime`, README na jeden
      ekran mówiący, co jest kryterium wejścia do tego pakietu — próg z `design.md`, D2)
- [x] 1.3 Przenieść `agent/db.py` do `tc_runtime/db.py`, zamieniając stałą klucza advisory
      locka na argument; `agent/db.py` znika, wywołania podają `MIGRATION_LOCK_KEY` z modułu
- [x] 1.4 Przenieść `agent/migrate.py` i `agent/schema_version.py` do `tc_runtime`
- [x] 1.5 Przenieść `agent/auth.py` i `agent/routers/models.py` do `tc_runtime`
- [x] 1.6 Przenieść testy tych plików z `modules/agent/tests/` do `packages/tc-runtime/tests/`;
      w agencie zostają tylko te, które sprawdzają jego użycie pakietu, nie sam pakiet
- [x] 1.7 Test regresyjny w agencie: klucz advisory locka, którym woła pakiet, jest wciąż
      **8030** — sparametryzowanie klucza to dokładnie ten tryb awarii, w którym dwa moduły
      zaczynają blokować sobie migracje (`design.md`, Risks)
- [x] 1.8 `agent/pyproject.toml` deklaruje `tc-runtime` jako zależność ścieżkową
- [x] 1.9 `modules/agent/Dockerfile`: `COPY packages/ ./packages/` przed `uv sync`; zbudować
      obraz lokalnie i potwierdzić, że wstaje
- [x] 1.10 `checks.yml`: job `packages` uruchamiający testy pakietów, oraz filtr, który przy
      zmianie w `packages/tc-runtime/` ustawia `true` dla każdego modułu deklarującego tę
      zależność (na tym etapie: `agent`)
- [x] 1.11 `docs/architecture.md`: „Why no shared library" zastąpione nową regułą — co wolno
      dzielić, pod jakim warunkiem, i co to znaczy dla kasowania modułu (`design.md`, Risks,
      trzeci punkt)
- [x] 1.12 `CLAUDE.md`: nagłówek o braku wspólnej biblioteki i sekcja o modułach zgodne z nową
      regułą; wymienić `packages/` w mapie repozytorium
- [x] 1.13 `uv run pytest`, `ruff check .`, `pyright` zielone w `agent` i w `tc-runtime`

## 2. `teams` dochodzi do `tc-runtime`

- [x] 2.1 `teams/db.py` zastąpione pakietem; klucz **8050** przekazywany z modułu, z testem
      regresyjnym jak 1.7
- [x] 2.2 `teams/migrate.py`, `teams/schema_version.py` zastąpione pakietem — **wersja teams
      jest tą, która została przeniesiona w 1.4**, więc agent dostaje przy okazji jej fix na
      puste `heads`; potwierdzić testem, że komunikat agenta nie jest już urwany
- [x] 2.3 `teams/auth.py` i `teams/routers/models.py` zastąpione pakietem
- [x] 2.4 `teams/pyproject.toml`, `modules/teams/Dockerfile` i filtr w `checks.yml` jak w 1.8–1.10
- [x] 2.5 Testy `teams` i `tc-runtime` zielone; różnice, których nie dało się sparametryzować,
      wypisane w `review.md` albo w README pakietu

## 3. `market-data` dochodzi częściowo

- [x] 3.1 `market_data/migrate.py` i `market_data/schema_version.py` zastąpione pakietem
- [x] 3.2 `market_data/db.py` **zostaje u siebie** (`design.md`, D4); w jego docstringu
      wskazać, czym różni się od pakietowego i dlaczego — trzydziestominutowe okno migracji
- [x] 3.3 `market-data`: pyproject, Dockerfile, filtr CI; pełne `pytest -m db` zielone
- [x] 3.4 Odpowiedzieć na pytanie otwarte z `design.md`: czy okno migracji da się wyrazić
      parametrem. Odpowiedź „nie" jest wynikiem, nie porażką — zapisać ją w README pakietu

## 4. `tc-openai`

- [x] 4.1 Utworzyć `packages/tc-openai/` z README mówiącym, co jest wspólne, a co jest
      wariantem wejścia
- [x] 4.2 Zaprojektować i przenieść `provider.py` z dwoma wariantami wejścia: historia rozmowy
      (`agent`) i briefing (`teams`) — 79,4% wspólnych linii znaczy, że ~20% to jest ta
      różnica, i ona ma być jawna w sygnaturze, nie w gałęzi
- [x] 4.3 Testy providera z obu modułów przeniesione do pakietu; w modułach zostają te o ich
      własnym użyciu
- [x] 4.4 `agent` i `teams`: pyproject, Dockerfile, filtr CI; oba zestawy testów zielone
- [x] 4.5 Potwierdzić, że **osobne klucze OpenAI zostają osobne** — pakiet nie czyta żadnej
      zmiennej środowiskowej sam, klucz przychodzi z modułu

## 5. Trzy moduły MCP biorą to, co u nich jest kopią

- [x] 5.1 `network_identity.py` do `tc_runtime` jako pod-moduł; różnice trzech kopii
      (76,9–86,2%) wyrażone parametrami, nie gałęziami
- [x] 5.2 Wspólny `_detail` ze spłaszczaniem listy walidacyjnej do `tc_runtime`; trzy kopie
      są od iteracji 0 identyczne modulo dwie stałe, więc obie stałe stają się argumentami
- [x] 5.3 `market-mcp`, `teams-mcp`, `trading-mcp`: pyproject, Dockerfile, filtr CI
- [x] 5.4 `server.py`, `client.py`, `config.py`, `errors.py` **zostają nietknięte** — w README
      `tc-runtime` zapisać, dlaczego, z liczbami (`design.md`, D1), żeby następny czytelnik nie
      zaczynał tej analizy od zera
- [x] 5.5 Trzy zestawy testów zielone, w tym `scripts/contract.py check` w każdym z trzech

## 6. Domknięcie

- [x] 6.1 Wstawić do repo skrypt pomiaru identyczności — **zrobione w grupie 1**, bo
      `docs/architecture.md` powołuje się na niego jako na sposób sprawdzenia warunku 1,
      a dokument nie może wskazywać pliku, którego nie ma (`scripts/measure-duplication.py`)
- [ ] 6.2 Zmierzyć ponownie: ile linii ręcznej kopii zostało. Cel to znaczący spadek z ~959;
      liczba końcowa wchodzi do `review.md` albo do README pakietu
- [ ] 6.3 Przejrzeć README modułów pod kątem zdań tłumaczących duplikację regułą, która już
      nie obowiązuje
- [ ] 6.4 Zbudować wszystkie siedem obrazów lokalnie i potwierdzić, że każdy wstaje
- [ ] 6.5 Zdecydować o `review.md` (od 18 sierpnia 2026 opcjonalny) i zapisać decyzję —
      `proposal.md` wskazuje tę zmianę jako kandydata, który go zasługuje
