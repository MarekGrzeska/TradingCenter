## Verdict

System prompt moved from hard-coded constants to a versioned, operator-editable
database table (`prompt_revisions`), with `GET`/`PUT /prompt` and a new "Prompt
management" section in the terminal. All 23 tasks are done, including 7.1 (live-stack
end-to-end check), which the operator ran themselves and confirmed working
(2026-08-15) — not something this review could verify on its own, and not to be
mistaken for an unverified claim. One real defect surfaced during this review's own
diff pass and was fixed before archiving, on `main` directly (`cd15af7`), not folded
into the change's original commits.

## Verified

- `modules/agent`: `uv run pytest` — 164 passed (includes real `-m db` tests against a
  throwaway PostgreSQL container; Docker was available). `uv run ruff check .` — all
  checks passed. `uv run pyright` — 0 errors.
- `modules/terminal`: `pnpm test` — 529 passed (was 528 before the fix below added one
  regression test). `pnpm lint` — clean. `pnpm typecheck` — clean.
- Live dev stack (operator, 2026-08-15): edited the prompt from the terminal, a new
  turn answered under the new version, an earlier reply kept the old one on reload.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Medium | `terminal/src/agent/settings/PromptManagementView.tsx` (pre-fix) | Neither prompt `<textarea>` was disabled while a save was in flight. A keystroke typed in the window between clicking Save and the response landing was silently overwritten by `setDraft(draftOf(updated))` once the response arrived — the edit is lost with no warning. | FIXED in `cd15af7`: both fields now take `disabled={saving}`; regression test `PromptManagementView.test.tsx :: "locks the fields while a save is in flight, so a keystroke cannot land between submit and response"` added. |
| Low (accepted) | `agent/store.py`, `create_prompt_revision` | Read-latest-then-insert-next-version has no row lock (`SELECT ... FOR UPDATE`) and `prompt_revisions.version` has no unique constraint. Two concurrent `PUT /prompt` calls under READ COMMITTED could both compute the same next version with different bodies. | Not fixed — `design.md`'s Decisions section already scopes this change to a single-operator terminal with no concurrent-edit protection anywhere else either; the terminal's own Save button prevents same-tab double-submission. Flagged here so a future multi-operator change doesn't rediscover it from scratch. |

No other findings survived scrutiny — reviewed `turn.py`'s revision fetch (text and
stamped version come from one read, so they cannot disagree within a turn),
`tests/conftest.py`'s `id > 1` cleanup (safe: the table is append-only, so the seed
row's content is never mutated by test code), and `PromptUpdateIn`'s blank-text
validation.

## Spec coverage

### `agent-prompt-management`

| Requirement / Scenario | Proven by |
|---|---|
| Odczyt aktualnego promptu / Odczyt bez wcześniejszej edycji przez API | `test_prompt_router.py::test_get_prompt_reads_the_seeded_revision` |
| Odczyt aktualnego promptu / Odczyt po edycji | `test_prompt_router.py::test_put_prompt_creates_a_new_version_and_get_reflects_it` |
| Zapis tworzy nową wersję, nigdy nie nadpisuje istniejącej / Zapis nowej treści | `test_prompt_store.py::test_create_prompt_revision_bumps_the_version`, `test_prompt_store.py::test_create_prompt_revision_is_append_only` |
| Zapis tworzy nową wersję, nigdy nie nadpisuje istniejącej / Pusty tekst odrzucony | `test_prompt_router.py::test_put_prompt_refuses_a_blank_variant` |
| Odpowiedź niesie wersję, pod jaką faktycznie padła / Edycja w trakcie trwania rozmowy | `test_turn.py::test_a_reply_keeps_its_version_after_the_prompt_is_later_edited` |

### `terminal-agent-prompt-management`

| Requirement / Scenario | Proven by |
|---|---|
| Sekcja pokazuje aktualną treść i wersję z modułu / Rozwinięcie sekcji | `PromptManagementView.test.tsx :: "reads the current version and both variants from the module"` |
| Zapis wysyła oba warianty i pokazuje wersję zwróconą przez moduł / Zapis zmiany | `PromptManagementView.test.tsx :: "sends both variants on save and shows the version the module returns"` |
| Zapis wysyła oba warianty i pokazuje wersję zwróconą przez moduł / Moduł odrzuca pusty tekst | `PromptManagementView.test.tsx :: "keeps the last confirmed content on screen when a save is refused"` |
| Moduł nieosiągalny nie pokazuje żadnej treści jako aktualnej / Moduł agenta nie odpowiada na odczyt | `PromptManagementView.test.tsx :: "says the module is unreachable and shows no content as current"` |

Every requirement and scenario in both delta specs has a named test. No gaps.
