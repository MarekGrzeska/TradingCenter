## Verdict

Wdrożone (PR #418, #420; poprawka recenzji #419): agent operatora na serwerze ma `WebSearch` i `WebFetch` bez listy
domen, zapis plików tylko w `/home/agent/work/out/` (pliki żyją tydzień), wysyłkę pliku przez `files` narzędzia
odpowiedzi kanału Telegram i skill `artykul` z szablonem HTML w stylu `docs/style-template.html`. Zapis w tym, co sesja
sama czyta, zakazany z nazwy.

Świadomie bez zmian, choć ryzyko rośnie: zapis na koncie realnym agenta jest włączony (`AGENT_LIVE_ACCOUNT_WRITES=on`)
przy otwartej sieci — decyzja operatora, przełącznik bez zmiany kodu, granice w `design.md`.

## Verified

- `modules/claude-agent`: `uv run pytest` → 36 passed, 3 skipped lokalnie (testy entrypointu, w tym sprzątanie `out/`,
  biegną na CI — job `claude-agent` zielony w #418 i #420); `ruff check`, `pyright` 0 błędów.
- `openspec validate claude-agent-web-search --strict` → valid.
- Produkcja, 9 listopada, kontener po wdrożeniu `7e0405e1`: ustawienia mają `WebSearch`, `WebFetch` i
  `Edit(//home/agent/work/out/**)` w `allow`. Próba `claude -p` w zaufanym katalogu tymczasowym z tymi samymi
  ustawieniami: zapis do `out/` przeszedł, zapis do `work/.claude/` odrzucony, `WebSearch` i `WebFetch` zadziałały.
  Katalog, wpis zaufania i transkrypt próby usunięte.
- Próba w sesji agenta (3.2): artykuł o oczekiwaniach wobec Fed i Nasdaq 100 — dwa wyszukiwania, pobranie stron, plik
  HTML w `out/`, wysłany operatorowi z podsumowaniem i źródłami; operator potwierdził odbiór. Po #420 agent napisał
  kolejny artykuł (`huang-romans-konsekwencje-rynkowe-2026-11-09.html`, 13 KB) w nowym stylu; operator: „jest ok”.
- Wdrożenie #418 padło trzy razy na GHCR (`permission_denied: write_package`, potem brak manifestu przy `pull`) i
  przeszło przy czwartej próbie; serwer przez cały czas działał na poprzednich obrazach. #420 wdrożył się za pierwszym razem.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| High | archiwalne `review.md` `operator-agent-on-telegram` i `live-account-trading` | Twierdziły, że zapis agenta na koncie jest wyłączony — czytane z `.env` serwera, nie z `env` kontenera; w kontenerze konto realne `on`. | FIXED w #419 |
| Medium | `agent/.claude/settings.json` | Gołe `Edit`/`Write` w `deny` wygrywały z każdą zgodą na ścieżkę, więc zgoda na `out/` wymagała ich usunięcia; zakazy dla plików sesji dopisane z nazwy. | FIXED w #418, test `test_the_web_is_open_and_files_are_written_only_to_out` |
| Info | WebFetch w sesji | Claude Code 2.1.304 wykonuje `WebFetch` przez podagenta `web-fetch`; działa, kosztuje osobne wywołanie. | Bez zmian |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| Narzędzia agenta są wyliczone — Agent próbuje polecenia powłoki; Wysyłka do innego odbiorcy | `tests/test_render.py::test_what_nobody_may_call_stays_denied` |
| … Artykuł na temat; Dowolna domena | `test_render.py::test_the_web_is_open_and_files_are_written_only_to_out`; próba na produkcji |
| … Artykuł jako plik HTML | próba 3.2 na produkcji; skill `artykul` |
| … Zapis poza katalogiem wyników | `test_the_web_is_open_and_files_are_written_only_to_out` (zakazy z nazwy); próba `claude -p` |
| … pliki usuwane po tygodniu | `tests/test_entrypoint.py::test_what_the_agent_wrote_for_the_operator_lives_a_week` |
| … Strona każe działać | brak testu — **gap** |

## Gaps

- Scenariusz „Strona każe działać” stoi na instrukcji w `agent/CLAUDE.md`, nie na teście ani na twardej granicy; twardą
  granicą są przełączniki zapisu i `LIVE_ORDER_LIMITS`.
- Semantyki reguł uprawnień Claude Code testy jednostkowe nie sprawdzają — tylko kształt ustawień; sprawdziła ją próba na
  produkcji, przy podbiciu wersji Claude Code warto ją powtórzyć.
