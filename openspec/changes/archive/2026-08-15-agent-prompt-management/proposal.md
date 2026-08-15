## Why

Prompt systemowy agenta jest dziś twardym tekstem w kodzie (`modules/agent/agent/prompt.py`) —
jedyny sposób, żeby go zmienić, to commit i deploy. Terminal ma świeżo dodaną stronę Agent
Settings ze zwijanymi sekcjami (`AgentSettingsView.tsx`), a operator poprosił wprost o
kolejną: podgląd i edycja promptu, którego agent faktycznie używa, bez przechodzenia przez
repozytorium.

## What Changes

- Nowy endpoint odczytu w module agent: aktualny prompt systemowy (oba warianty — z
  narzędziami i bez), jego wersja i kiedy był ostatnio zmieniony.
- Nowy endpoint zapisu: operator nadpisuje treść promptu. Zapis jest trwały (tabela w bazie
  `agent`) i wersjonowany — nadpisanie bumpuje `PROMPT_VERSION` automatycznie, tak że
  transkrypty sprzed edycji zostają przypisane do wersji, pod jaką faktycznie odpowiedziano
  (ta sama zasada, jaką `agent/prompt.py` dziś opisuje dla ręcznego bumpa w kodzie).
- `system_prompt()` czyta aktualną treść z bazy; stałe w `prompt.py` stają się wartością
  startową (seed) przy pustej bazie, nie jedynym źródłem prawdy.
- Nowa sekcja **Prompt management** na stronie Agent Settings w terminalu, obok istniejącej
  **Agent cost**, tym samym wzorcem `CollapsibleSection`: podgląd aktualnej treści i wersji,
  formularz edycji z zapisem.
- Terminal: nowe typy i wywołania w `agentApi.ts` dla odczytu i zapisu promptu.

## Capabilities

### New Capabilities

- `agent-prompt-management`: moduł agent — trwały, wersjonowany magazyn promptu
  systemowego, API do odczytu i nadpisania go.
- `terminal-agent-prompt-management`: terminal — sekcja Prompt management na stronie Agent
  Settings, podgląd i edycja.

### Modified Capabilities

(brak — mechanizm `PROMPT_VERSION` i jego znaczenie dla transkryptów opisuje wciąż otwarta,
niezarchiwizowana zmiana `add-agent-chat`; ta zmiana buduje na nim, ale nie ma jeszcze
czego formalnie modyfikować pod `openspec/specs/`. Zależność opisana w design.md.)

## Impact

- `modules/agent/agent/prompt.py`, nowa migracja i tabela w bazie `agent`, nowy router,
  `agent/contract.py`.
- `modules/terminal/src/agent/agentApi.ts`, nowy komponent sekcji, `AgentSettingsView.tsx`.
- Zależność od wciąż otwartej `add-agent-chat` (mechanizm `PROMPT_VERSION`) — patrz
  design.md.
