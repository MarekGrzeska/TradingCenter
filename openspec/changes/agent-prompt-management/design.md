## Context

`modules/agent/agent/prompt.py` dziś trzyma dwa teksty jako stałe Pythona,
`SYSTEM_PROMPT_WITH_TOOLS` i `SYSTEM_PROMPT_WITHOUT_TOOLS`, złożone ze wspólnych
fragmentów (`_INTRO`, `_LIMITS`) i jednego różniącego się akapitu każdy. `PROMPT_VERSION`
to jedna etykieta ("v4") na CAŁY plik — dokstring modułu nazywa to wprost: "Two texts, one
version". Każda wiadomość w transkrypcie zapisuje tę etykietę w momencie odpowiedzi
(`agent/turn.py`), więc transkrypt sprzed zmiany zostaje odróżnialny od transkryptu po
niej. `test_prompt.py` pilnuje dokładnej treści obu tekstów i tego, że różnią się tylko
jednym akapitem.

Zmiana ta zastępuje stałe w kodzie trwałym magazynem w bazie `agent`, zachowując "jedną
wersję na dwa teksty" jako kształt danych, ale przenosząc źródło prawdy z pliku `.py` do
tabeli, żeby operator mógł je nadpisać z terminala.

## Goals / Non-Goals

**Goals:**
- Operator czyta aktualną treść obu wariantów promptu i jego wersję z terminala.
- Operator nadpisuje oba warianty naraz; zapis tworzy nową wersję, nie edytuje poprzedniej
  w miejscu — historia zostaje, nawet jeśli dziś nic jej nie czyta.
- Transkrypty sprzed edycji pozostają poprawnie przypisane do wersji, pod jaką faktycznie
  odpowiedziano — inwariant, który `add-agent-chat` już ustaliło, ta zmiana go dziedziczy
  zamiast renegocjować.

**Non-Goals:**
- Przywracanie (rollback) starszej wersji z UI — historia jest zapisywana, ale odczyt
  poza "aktualna wersja" zostaje poza zakresem.
- Walidacja treści promptu pod kątem sensu (np. wykrywanie usuniętej klauzuli o poradach
  inwestycyjnych) — operator jest jedynym użytkownikiem terminala i jedynym, kto go
  edytuje; to świadome zaufanie, nie przeoczenie.
- Edycja fragmentów współdzielonych (`_INTRO`/`_LIMITS`) osobno od reszty — patrz Decyzja
  niżej.

## Decisions

**Jedna wersja na dwa teksty, tak jak dziś.** `PUT` nadpisuje oba warianty jednym
wywołaniem i tworzy jeden nowy wiersz `(version, with_tools_body, without_tools_body,
created_at)`, nawet jeśli operator faktycznie zmienił tylko jeden z dwóch tekstów.
Alternatywa — osobna wersja per wariant — rozjeżdżałaby się z tym, co `agent/turn.py` już
zapisuje na wiadomości (jedna etykieta), i wymagałaby zmiany tego mechanizmu, którego ta
zmiana ma nie dotykać.

**Operator edytuje pełny tekst każdego wariantu, nie fragmenty składowe.** `_INTRO` i
`_LIMITS` przestają być wspólnym źródłem egzekwowanym w czasie edycji — to, że oba warianty
dziś dzielą je słowo w słowo, jest własnością tekstu-ziarna (seed), nie regułą, którą baza
dalej pilnuje. Alternatywa — cztery osobne pola (`_INTRO`, `_LIMITS`,
akapit-z-narzędziami, akapit-bez-narzędzi) składane w dwa teksty w locie — dałaby
mniejsze ryzyko rozjazdu, ale to złożoność UI i backendu bez proszonej funkcji: operator
poprosił o edycję promptu, nie o edytor szablonów. Odrzucone.

**Zapis tworzy nowy wiersz, nigdy nie nadpisuje istniejącego.** Append-only zamiast
`UPDATE` — ta sama zasada co `tool_calls` (`CLAUDE.md`, "rows in `tool_calls` still
recording what happened"). Koszt jest jedną tabelą, która rośnie bez czyszczenia; przy
skali jednego operatora edytującego prompt od czasu do czasu to nie jest problem wart
rozwiązywania teraz.

**Migracja zasiewa wiersz `"v4"` treścią dzisiejszych stałych.** Transkrypty już
oznaczone `"v4"` mają wtedy z czym się zgadzać w bazie, nie tylko w historii gita. Bez
tego pierwsza wersja w bazie zaczynałaby się od `"v5"` i `"v4"` zostałoby wersją, której
treści nikt już nie może odczytać poza kodem sprzed tej zmiany.

**`GET`/`PUT` idą przez ten sam `current_principal`, co `/usage`, ale bez `owner`.**
Prompt jest jeden, globalny dla modułu — nie na sesję ani operatora — więc tabela nie ma
kolumny właściciela. Uwierzytelnienie zostaje (żeby nieautoryzowane wywołanie nie mogło
nadpisać promptu), ale nie ma sensu filtrować po nim.

## Risks / Trade-offs

[Operator wpisuje pusty lub bardzo krótki tekst i agent zaczyna odpowiadać bez żadnych
ograniczeń z `_LIMITS`] → `PUT` odrzuca pusty tekst (400), ale nie egzekwuje nic ponad to
— zgodne z Non-Goals.

[Tabela rośnie bez ograniczenia przy częstych edycjach] → zaakceptowane przy obecnej
skali (jeden operator); rewizja, jeśli kiedyś stanie się realnym kosztem.

[Odczyt aktualnego promptu na każdą turę dokłada zapytanie do bazy] → jeden dodatkowy
indeksowany `SELECT ... ORDER BY id DESC LIMIT 1` na turę; ten sam rząd wielkości co
zapis usage, który już tam jest.

## Migration Plan

1. Migracja alembic: tabela `prompt_revisions` + wiersz startowy `"v4"` z treścią
   dzisiejszych `SYSTEM_PROMPT_WITH_TOOLS`/`SYSTEM_PROMPT_WITHOUT_TOOLS`.
2. `agent/prompt.py`: `system_prompt()` czyta z bazy zamiast stałych; stałe zostają jako
   `_SEED_*`, użyte wyłącznie przez migrację.
3. Nowy router (`GET`/`PUT /prompt`), nowe modele w `agent/contract.py`.
4. Terminal: `agentApi.ts` (typy + wywołania), nowa sekcja `PromptManagementView.tsx`
   pod `AgentSettingsView.tsx`, wzorcem `CollapsibleSection` obok "Agent cost".

Rollback: usunięcie sekcji z terminala i przywrócenie `system_prompt()` do stałych w
kodzie jest niezależne od tabeli — tabela może zostać nietknięta, kolejna migracja w dół
ją usuwa, jeśli zajdzie potrzeba.
