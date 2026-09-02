## 1. Szósta para w workbenchu

- [x] 1.1 `strategy_mcp_url` / `_scope` / `_request_timeout_seconds` w trzech `config.py`, z walidatorami i przekazaniem do obu powierzchni
- [x] 1.2 `ToolServer(settings, prefix="strategy_mcp")` w obu rejestrach
- [x] 1.3 `.env.example`, README workbencha, `dev.py` (advisory i „pięć" → „sześć")
- [x] 1.4 Dwa komunikaty nazywające dwa serwery — `clock.py`, `validation.py` — wyprowadzone z rejestru

## 2. Testy

- [x] 2.1 Listy serwerów w `test_config_common.py`, `test_tool_registry.py`, `test_tool_assignment.py`
- [x] 2.2 Jeden test przez pętlę: `pending_setups` ze stand-inu budzi zespół dokładnie raz, zero wierszy zużycia przed wyzwoleniem

## 3. Infrastruktura

- [x] 3.1 `STRATEGY_MCP_URL` / `_SCOPE` w bloku workbencha, `terraform fmt` i `validate`
- [ ] 3.2 `apply` operatora i restart workbencha

## 4. Dokumenty

- [x] 4.1 `CLAUDE.md` i `README.md`: pięć serwerów narzędzi → sześć
