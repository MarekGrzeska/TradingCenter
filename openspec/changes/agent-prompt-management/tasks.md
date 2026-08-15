## 1. Magazyn i migracja

- [x] 1.1 `migrations/versions/0003_prompt_revisions.py` — tabela `prompt_revisions`
      (`id serial`, `version text`, `with_tools_body text`, `without_tools_body text`,
      `created_at timestamptz`)
- [x] 1.2 Ta sama migracja zasiewa wiersz `version="v4"` treścią dzisiejszych
      `SYSTEM_PROMPT_WITH_TOOLS`/`SYSTEM_PROMPT_WITHOUT_TOOLS` (skopiowaną, nie
      zaimportowaną — migracja MUST NOT zależeć od treści `prompt.py` zmieniającej się
      w przyszłości). Zweryfikowane bajt-w-bajt przez `repr()` obu stałych przed edycją
      `prompt.py`.

## 2. `agent/prompt.py`

- [x] 2.1 Uproszczone względem planu: stałe usunięte całkiem, nie przeniesione do
      `_SEED_*` — migracja (1.2) trzyma własną, niezależną kopię, więc nic w
      `prompt.py` już ich nie potrzebowało; trzymanie nieużywanych stałych byłoby
      martwym kodem. `prompt.py` zostaje z jedną czystą funkcją, `prompt_text()`.
- [x] 2.2 `store.py`: `latest_prompt_revision(conn)`, `create_prompt_revision(conn,
      with_tools_body, without_tools_body)` — wersja następnej rewizji liczona jako
      `v{N+1}` z najwyższej istniejącej
- [x] 2.3 Przeniesione do kontraktu: odmowa pustego tekstu w `PromptUpdateIn`
      (`field_validator`), tym samym wzorcem co `PatchSessionIn._title_is_a_name` —
      `create_prompt_revision` sam nie waliduje, ufa temu co dostaje, jak reszta
      `store.py`
- [x] 2.4 `turn.py` czyta `store.latest_prompt_revision(conn)` przy okazji odczytu
      historii (jedno połączenie, jeden spójny odczyt tekstu i wersji) i wybiera
      wariant przez `prompt_text(revision, has_tools=...)`

## 3. Kontrakt i router agenta

- [x] 3.1 `agent/contract.py`: `PromptOut` (version, with_tools, without_tools,
      updated_at), `PromptUpdateIn` (with_tools, without_tools)
- [x] 3.2 `agent/routers/prompt.py`: `GET /prompt`, `PUT /prompt`, oba za
      `current_principal` (bez `owner` w zapytaniu — magazyn jest globalny)
- [x] 3.3 `agent/app.py`: `app.include_router(prompt.router)`

## 4. Testy backendu

- [x] 4.1 `tests/test_prompt.py` — przepisane na `prompt_text()`, jedyną funkcję jaka
      tam została
- [x] 4.2 `tests/test_prompt_store.py` — `latest_prompt_revision`,
      `create_prompt_revision`, numeracja wersji, append-only (poprzedni wiersz
      nietknięty po zapisie) + treść seeda `"v4"` (dawne asercje ze starego
      `test_prompt.py`, teraz przeniesione tutaj). Wymagało poprawki w
      `conftest.py`: `prompt_revisions` nie było w `TABLES`, więc wersje rosły bez
      resetu między testami w tej samej sesji — teraz `db` fixture zostawia wiersz
      `id=1` (seed migracji) i kasuje resztę.
- [x] 4.3 `tests/test_prompt_router.py` (`-m db`) — `GET`/`PUT /prompt` end-to-end,
      422 na pusty wariant, 401 bez uwierzytelnienia
- [x] 4.4 `test_turn.py`: inwariant "dwa teksty, jedna wersja" — tura odpowiedziana
      przed edycją zachowuje starą wersję na swojej wiadomości po edycji promptu

## 5. Terminal — API i typy

- [x] 5.1 `agentApi.ts`: `AgentPrompt` (with_tools → camelCase), `getPrompt()`,
      `updatePrompt(withTools, withoutTools)`. Dodatkowo: `JsonRequest["method"]` w
      `data/http.ts` nie znał `"PUT"` — dodane.
- [x] 5.2 `agentApi.test.ts`: pokrycie obu wywołań, w tym odmowy (422 → `refused`) i
      nieosiągalności

## 6. Terminal — sekcja Prompt management

- [x] 6.1 `agent/settings/PromptManagementView.tsx` — odczyt przy rozwinięciu (przez
      nowy `usePrompt.ts`, ten sam kształt co `useUsage`), dwa pola tekstowe
      (with-tools, without-tools), wersja, przycisk zapisu
- [x] 6.2 Zapis: jeden `PUT` na oba pola, stan po sukcesie pokazuje wersję i treść
      zwróconą przez moduł — nic policzonego lokalnie
- [x] 6.3 Nieosiągalny moduł przy odczycie: sekcja mówi to wprost, bez treści jako
      aktualnej (ten sam wzorzec co `AgentCostView`'s `unreachable`)
- [x] 6.4 `AgentSettingsView.tsx`: druga `CollapsibleSection`, "Prompt management", pod
      "Agent cost"
- [x] 6.5 `PromptManagementView.test.tsx` — odczyt, zapis, odmowa pustego tekstu,
      nieosiągalność, treść nie znika po nieudanym zapisie. Dodatkowo trzeba było
      dopisać `getPrompt`/`updatePrompt` do trzech istniejących fake'ów `AgentApi`
      (`AgentChat.test.tsx`, `agentChatStore.test.ts`, `AgentCostView.test.tsx`) —
      typ jest teraz szerszy, każdy pełny fake musi go spełniać.

## 7. Weryfikacja end-to-end

- [x] 7.1 Lokalny stos: edycja promptu z terminala, nowa rozmowa odpowiada pod nową
      wersją, stara rozmowa w `sessions`/`messages` zachowuje starą wersję na swoich
      wcześniejszych wiadomościach — zweryfikowane przez operatora na jego własnym
      dev stosie (2026-08-15)
- [x] 7.2 `uv run pytest` (164 passed, real `-m db` tests ran — Docker był dostępny),
      `uv run ruff check .`, `uv run pyright` (agent) — zielone
- [x] 7.3 `pnpm test` (528 passed), `pnpm lint`, `pnpm typecheck` (terminal) — zielone
