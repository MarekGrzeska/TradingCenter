## 1. Schemat i store

- [x] 1.1 Migracja `migrations/teams/versions/0008_team_memories.py`: tabela `team_memories`
      (`id`, `team_id` FK `ON DELETE CASCADE`, `author_agent_key`, `run_id` FK nullable, `content`,
      `created_at`), CHECK na długość `content`, indeks po `(team_id, created_at DESC)`, działający
      `downgrade`, docstring prozą mówiący, dlaczego tabela stoi obok rewizji
- [x] 1.2 `teams/store/memory.py`: `add_memory`, `list_memories` (najnowsze pierwsze, z licznikiem
      całości), `count_memories_for_run`, `delete_memory` — każde z filtrem właściciela w zdaniu SQL
- [x] 1.3 Re-eksport w `teams/store/__init__.py` (blok `from .memory import …` i `__all__`)
- [x] 1.4 `team_memories` dopisane do `TABLES` w `tests/teams/conftest.py`, przed `teams` i `runs`
- [x] 1.5 Testy store `@pytest.mark.db`: zapis i odczyt, kolejność, filtr właściciela, usunięcie,
      zachowanie wpisów po archiwizacji zespołu

## 2. Kontrakt

- [x] 2.1 `teams/contract.py`: `MemoryEntry` i odpowiedź odczytu (wpisy + informacja, że jest ich
      więcej niż oddano)
- [x] 2.2 Stałe sufitów `MEMORY_ENTRY_MAX_CHARS`, `MEMORY_READ_LIMIT`, `MEMORY_WRITES_PER_RUN`
      w jednym miejscu, obok siebie
- [x] 2.3 Testy kontraktu na kształt odpowiedzi i na spójność sufitu znaków z CHECK-iem migracji

## 3. Źródło narzędzi w procesie

- [x] 3.1 `teams/tools/memory.py`: stałe deskryptory `memory_read` i `memory_write` (opisy niosą
      sufity i warunki odmowy) oraz `MemoryToolSource` z interfejsem `ToolServer` — `label`,
      `configured`, `list_tools`, `call`, `moves_the_account`, `aclose`
- [x] 3.2 `list_tools()` nie dotyka bazy — test, że ogłasza obie nazwy przy `pool=None`
- [x] 3.3 `ToolServerRegistry.from_settings(settings, *, pool=None)` konstruuje źródło pamięci obok
      dwóch serwerów; `workbench/app.py` podaje pulę bazy `teams`
- [x] 3.4 `plan_tools`: warunek „żaden serwer nie jest skonfigurowany" pyta o serwery **sieciowe**,
      żeby odmowa nadal nazywała `market-mcp`/`trading-mcp`; test na nieskonfigurowany serwer przy
      obecnym źródle pamięci
- [x] 3.5 Testy: zespół z samą pamięcią rusza bez serwerów; kolizja nazwy pamięci z nazwą serwera
      odmawia przy zapisie i przy uruchomieniu; `GET /tools` i zapis rewizji widzą nazwy pamięci

## 4. Egzekwowanie przypisania przy wywołaniu

- [x] 4.1 `ToolPlan.call(name, arguments, *, agent_key)` — nazwa spoza `per_agent[agent_key]` oddaje
      `ToolOutcome(REFUSED, …)` nazywający brak przypisania, bez sięgania do źródła
- [x] 4.2 `_StepRunner` podaje `call_tool` związany kluczem agenta; sygnatura `run_agent` w `loop.py`
      bez zmian
- [x] 4.3 Testy na `scripted_provider`: model woła nazwę nieprzypisaną (odmowa, źródło nietknięte),
      woła nazwę nieznaną nikomu, a odmowa ląduje w `tool_calls` i przebieg pracuje dalej

## 5. Kontekst przebiegu

- [x] 5.1 `start_run_on_revision` przekazuje `team_id` i `owner_principal` do `execute_run`, dalej do
      `_Run` i `_StepRunner`
- [x] 5.2 Wywołania pamięci dostają zespół, właściciela, przebieg i klucz agenta; licznik zapisów
      per przebieg egzekwuje `MEMORY_WRITES_PER_RUN`
- [x] 5.3 Test przebiegu z zegara: wpis należy do właściciela harmonogramu, nie do procesu
- [x] 5.4 Test dwóch przebiegów: pierwszy zapisuje, drugi odczytuje; wpis przeżywa przebieg
      zakończony błędem

## 6. Trasy operatora

- [x] 6.1 `teams/routers/memory.py`: `GET /teams/{team_id}/memory`,
      `DELETE /teams/{team_id}/memory/{entry_id}` (204), oba z `Depends(current_principal)`
- [x] 6.2 Router w `teams/surface.py` we właściwej kolejności; `tests/test_route_collisions.py` zielony
- [x] 6.3 Trzy testy tras: ścieżka szczęśliwa, błąd, odmowa (cudzy zespół nieodróżnialny od
      nieistniejącego)
- [x] 6.4 `python -m teams.openapi` i `pnpm contract:generate` w terminalu — `contract:check` zielony

## 7. Terminal

- [x] 7.1 Odczyt i usunięcie w `src/teams/teamsApi.ts` z mapowaniem na camelCase
- [x] 7.2 Panel pamięci zespołu: lista od najnowszego (treść, agent, moment, przebieg), usunięcie
      z potwierdzeniem, stan „nic jeszcze nie zapamiętano"
- [x] 7.3 Testy panelu wedle reguły dla widoku CRUD: ścieżka szczęśliwa, jeden błąd, jedna odmowa

## 8. Domknięcie

- [ ] 8.1 `.env.example` bez zmian — potwierdzić, że zmiana nie dokłada ustawienia
- [ ] 8.2 `modules/workbench/README.md`: pamięć w opisie powierzchni teams
- [ ] 8.3 Pełne bramki: `uv run pytest`, `ruff check .`, `pyright` w workbenchu; `pnpm test`, `lint`,
      `typecheck`, `contract:check` w terminalu
- [ ] 8.4 `openspec validate teams-remember-between-runs --strict`
