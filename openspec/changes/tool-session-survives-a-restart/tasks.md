## 1. teams: ponowienie po odtworzonej sesji

- [x] 1.1 `tools/client.py`: predykat rozpoznający odrzucenie z powodu nieznanej sesji —
      `McpError` o `code == 32600` i komunikacie `"Session terminated"`, ze stałą nazwaną
      w jednym miejscu
- [x] 1.2 `ToolServer.call()`: po takim niepowodzeniu `_disconnect()`, otwarcie sesji
      i **jedno** powtórzenie tego samego wywołania; drugie niepowodzenie zwraca
      `UNAVAILABLE` tak jak dziś
- [x] 1.3 Każda inna awaria bez zmian — `TimeoutError` i pozostałe wyjątki nie przechodzą
      przez ścieżkę ponowienia
- [x] 1.4 `log.info` nazywający odtworzenie sesji i ponowienie, z nazwą narzędzia i etykietą
      serwera
- [x] 1.5 `ToolServer.list_tools()`: ta sama ścieżka, żeby odczyt katalogu po restarcie nie
      wywracał startu przebiegu
- [x] 1.6 Testy: ponowienie kończy się wynikiem narzędzia; drugie niepowodzenie to
      `unavailable`; timeout nie jest ponawiany; wywołanie zapisujące jest ponawiane tak
      samo jak czytające
- [x] 1.7 Test przeciwko prawdziwemu klientowi MCP i serwerowi odpowiadającemu `404` na
      `POST /mcp` — dowód, że predykat z 1.1 nadal łapie to, co SDK produkuje
- [x] 1.8 Test śladu: ponowione wywołanie zwraca jeden `ToolOutcome` — a wiersz w
      `tool_calls` pisze `engine.py` z tego, co `call()` zwróciło
- [x] 1.9 `uv run ruff check .` · `uv run pyright` · `uv run pytest`

## 2. terminal: treść wywołań po zakończeniu przebiegu

- [x] 2.1 `useRunMonitor.ts`: po `runFinished` ponowny odczyt `api.runToolCalls`, wynik
      **zastępuje** listę wywołań zamiast się do niej dokleić
- [x] 2.2 Odczyt korzysta z kroków znanych w tym momencie i nie wywraca monitora, gdy się
      nie uda — tak jak pierwszy odczyt dziś
- [x] 2.3 Testy: wywołanie ze strumienia ma treść po zakończeniu przebiegu; to samo
      wywołanie nie pojawia się dwa razy; nieudany odczyt zostawia listę taką, jaka była
- [x] 2.4 `pnpm lint` · `pnpm typecheck` · `pnpm test`

## 3. Domknięcie

- [x] 3.1 README `teams` — kiedy moduł ponawia wywołanie i dlaczego tylko wtedy
- [ ] 3.2 `openspec validate tool-session-survives-a-restart --strict`
- [ ] 3.3 `review.md`
