## Verdict

Wdrożone: operator widzi, po co agent sięgnął i co dostał. Tura niesie czwarty rodzaj
zdarzenia SSE — `tool_call`, wysyłany w chwili, w której wywołanie się rozstrzygnęło, nie
po zakończeniu tury. `MessageOut` niesie `tool_calls`, więc przeładowana sesja pokazuje to
samo, co pokazywała tura na żywo. Panel renderuje wpis w transkrypcie tam, gdzie wywołanie
padło: zwinięty niesie nazwę, sposób zakończenia i czas, rozwinięty argumenty i treść
wyniku.

Jedno miejsce buduje oba kształty (`ToolCallOut`, dwa konstruktory) i jedno miejsce je
odczytuje po stronie terminala (`toolCall.ts`, jeden mapper). To nie jest kosmetyka:
sensem tego podglądu jest móc powiedzieć „model dostał **to**", a dwa kształty tej samej
rzeczy to dwie szanse, żeby panel i transkrypt mówiły co innego. Asercja stoi po obu
stronach — `test_the_stream_and_the_transcript_publish_one_shape` w agencie i
`test_the_transcript_hands_back_what_the_stream_sent` na drucie.

Zmiana wzięła się z sesji z 13 sierpnia 2026, w której cztery narzędzia market-mcp
odrzucały własne odpowiedzi, a operator widział wyłącznie agenta mówiącego, że archiwum
nie ma danych. Przyczynę znalazł dopiero `SELECT` po tabeli `tool_calls`. Ten sam błąd, w
tym panelu, byłby teraz widoczny na pierwszym ekranie: trzy wpisy z czerwonym `refused` i
tekstem `Output validation error: 'from_' is a required property` po rozwinięciu.

Przegląd nie znalazł błędu w tym, co zaimplementowano. Znalazł jedną rzecz, którą warto
zapisać jako obserwację, i jedną lukę, której nie da się domknąć bez uruchomienia —
przebiegu ręcznego przez prawdziwy panel, którego nie wykonano (zadanie 5.3 zostaje
otwarte, świadomie).

## Verified

Windows 11, Docker w tle — testy `db` weszły same, nie zostały pominięte.

- `cd modules/agent && uv run pytest -q` → `159 passed, 2 warnings` (było 146)
- `cd modules/agent && uv run ruff check .` → `All checks passed!`
- `cd modules/agent && uv run pyright` → `0 errors, 0 warnings, 0 informations`
- `cd modules/terminal && pnpm test` → `512 passed` w 38 plikach (było 495)
- `cd modules/terminal && pnpm typecheck` → czysto
- `cd modules/terminal && pnpm lint` → czysto
- `cd modules/terminal && pnpm contract:check` → `Contract is up to date.`
- `openspec validate show-tool-calls-in-chat --strict` → `Change ... is valid`

Co pokrywają nowe testy, w kolejności warstw:

| Warstwa | Asercja |
|---|---|
| `test_graph.py` | trzy wywołania ogłoszone w kolejności rozstrzygnięcia; pozycja restartuje z rundą; odmowa ogłoszona jak każde inne; wywołanie zatrzymane sufitem **nie** ogłoszone |
| `test_sessions_router.py` | `tool_call` przed `complete`; odmowa jako wywołanie, nie jako błąd strumienia; transkrypt równy strumieniowi; tura bez narzędzi zostawia puste listy |
| `test_tool_calls_store.py` | cała sesja jednym zapytaniem, pogrupowana po wypowiedzi; pozycja ogłoszona równa zapisanej |
| `test_transcript_contract.py` | pola drutu wyliczone co do jednego, po obu stronach; brak wywołań to pusta lista, nie `null` |
| `stream.test.ts` | ramka `tool_call` do tego samego kształtu co transkrypt; nieznany `outcome` nie udaje żadnego ze znanych |
| `agentApi.test.ts` | mapowanie wywołań; moduł bez pola `tool_calls` czyta się jak pusta lista |
| `agentChatStore.test.ts` | wywołanie w trakcie `waiting`; zachowane po `complete`; zachowane po zerwaniu, którego nie dało się przeładować |
| `AgentChat.test.tsx` | wpis w trakcie tury i po przeładowaniu; rozwijanie; trzy sposoby zakończenia rozróżnialne; tura bez wywołań bez wpisów |

**Czego nie zweryfikowano uruchomieniem.** Przebiegu przez prawdziwy panel z prawdziwym
modelem i prawdziwym market-mcp — stos jest operatora i to on go uruchamia. Wszystko
poniżej przeglądarki jest przetestowane przeciw prawdziwej bazie (testy `db` stawiają
własny PostgreSQL), ale „widać to na ekranie" jest twierdzeniem, którego jsdom nie
rozstrzyga. Zadanie 5.3 zostaje niezaznaczone i jest to jedyna rzecz dzieląca tę zmianę od
zamknięcia.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **Low** | `modules/agent/agent/graph.py` | `on_tool_call` jest `await`-owane wewnątrz pętli rundy, więc wywołanie zwrotne, które by się zawiesiło, zatrzymałoby turę. Dziś nie może: jedyna implementacja to `queue.put_nowait` na nieograniczonej kolejce, o czym `turn.py` mówi w pierwszym akapicie („`put_nowait` never blocks"). Zapisane, bo to jest dokładnie ta własność, którą druga implementacja tego wywołania zwrotnego mogłaby zepsuć po cichu — i wtedy objawem będzie tura, która stanęła, a nie zdarzenie, które nie doszło. | observation |
| **Low** | `modules/terminal/src/agent/ToolCallEntry.tsx` | Treść wyniku idzie na ekran w całości, ograniczona wyłącznie sufitami market-mcp (~2 kB w największej zmierzonej odpowiedzi) i `max-h-48` z przewijaniem. Świadome — `design.md`, „Wynik w całości, bez własnego sufitu". Do zmierzenia po wdrożeniu: rozmiar transkryptu rozmowy z kilkunastoma turami narzędziowymi. Jeśli zaboli, sufit dokłada się wtedy, z pomiarem, a nie teraz z przeczucia. | accepted |

## Gaps

- **Panelu nikt nie zobaczył.** Testy komponentu przechodzą w jsdom, który nie ma układu,
  nie ma przewijania i nie ma szerokości. Wpis w kolumnie panelu może się okazać za ciasny
  na `get_last_price — no answer — 3 ms` w jednej linii; nazwa jest `truncate`, więc
  najgorszym przypadkiem jest ucięta nazwa, a nie rozjechany układ — ale to jest
  przewidywanie, nie obserwacja.
- **Tura z ośmioma wywołaniami nie została nigdy pokazana.** Sufit to osiem, testy chodzą
  po jednym do trzech. Twierdzenie „zwinięte domyślnie wystarczy" jest z rozumowania, nie z
  ekranu.
- **Zdarzenie w locie przy rozłączeniu.** `turn.py` wkłada zdarzenia do kolejki, której
  nikt nie musi opróżniać, więc wywołanie ogłoszone po tym, jak operator zamknął panel,
  przepada — i jest to zachowanie zamierzone, bo transkrypt je odda przy powrocie. Nie
  przetestowane wprost; test na to musiałby udawać rozłączenie w środku rundy narzędzi.

## Follow-ups

- Zadanie 5.3: przebieg ręczny na uruchomionym stosie — pytanie sięgające po narzędzia, w
  trakcie tury i po przeładowaniu sesji. Do wykonania przez operatora.
- Zmierzyć rozmiar transkryptu rozmowy z kilkunastoma turami narzędziowymi, zanim sufit na
  `result_text` stanie się pytaniem.
