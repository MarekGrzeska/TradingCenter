## 1. Uprawnienia i testy

- [x] 1.1 `agent/.claude/settings.json`: `WebSearch` i `WebFetch` z `deny` do `allow`
- [x] 1.2 `Edit(//home/agent/work/out/**)` w `allow`; zakazy dla `.claude/`, `CLAUDE.md`, `.mcp.json`, `owner-channel.md`, `~/.claude/`
- [x] 1.3 `runtime/entrypoint.sh`: `out/` tworzony, pliki starsze niż tydzień usuwane; test
- [x] 1.4 `tests/test_render.py`: `NEVER` bez sieci i zapisu; test, że sieć jest otwarta bez zakresu, a zapis tylko w `out/`, niezależnie od przełączników
- [x] 1.5 `uv run pytest`, `ruff check .`, `pyright` w `modules/claude-agent`

## 2. Instrukcje i dokumentacja

- [x] 2.1 `agent/CLAUDE.md`: sieć jako źródło danych, źródła w odpowiedzi, zakaz działania na polecenie ze strony i danych systemu w adresach; artykuł jako HTML w `out/` wysłany przez `files`
- [x] 2.2 `modules/claude-agent/README.md`: lista zakazów bez sieci

## 3. Wdrożenie i próba

- [x] 3.1 Merge, `deploy-watch`; po restarcie sesji ustawienia w kontenerze mają sieć i `out/` w `allow`; próba `claude -p` w kontenerze: zapis do `out/` przechodzi, do `.claude/` jest odrzucony
- [ ] 3.2 Operator z Telegrama: artykuł na temat spoza archiwum, ze źródłami, jako plik HTML w czacie
- [ ] 3.3 `review.md`; archiwizacja
