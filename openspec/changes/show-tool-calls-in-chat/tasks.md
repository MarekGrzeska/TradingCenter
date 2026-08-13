## 1. Agent — zdarzenie w turze

- [x] 1.1 `ConversationState` niesie `on_tool_call` obok `on_delta`; `initial_state` przyjmuje je z tym samym domyślnym zachowaniem co reszta pól
- [x] 1.2 `run_tools` woła `on_tool_call` po każdym rozstrzygniętym wywołaniu, przekazując `RecordedCall`
- [x] 1.3 Wywołanie pominięte przez sufit tury nie woła `on_tool_call` — nic nie padło, więc nie ma czego pokazać
- [x] 1.4 Nowy kształt zdarzenia w `turn.py` obok `Fragment`/`Complete`/`Failed`, wkładany do kolejki przez `on_tool_call`
- [x] 1.5 `_sse` w `routers/sessions.py` wysyła go jako czwarty rodzaj zdarzenia
- [x] 1.6 Testy: tura z trzema wywołaniami wysyła trzy zdarzenia przed `complete`; odmowa dociera z powodem; zdarzenia zachowują kolejność rund

## 2. Agent — kontrakt transkryptu

- [x] 2.1 `ToolCallOut` w `agent/contract.py` — nazwa, argumenty, wynik, sposób zakończenia, czas trwania, pozycja w turze
- [x] 2.2 `tool_calls` na `MessageOut`, pusta lista dla wypowiedzi bez wywołań i dla wypowiedzi operatora
- [x] 2.3 Odczyt wywołań po `session_id` w `store.py`, grupowany po `message_id`
- [x] 2.4 `GET /sessions/{id}/messages` woła go raz na transkrypt i nie odpytuje bazy raz na wypowiedź
- [x] 2.5 Testy: transkrypt niesie wywołania przy właściwej wypowiedzi, w kolejności rund i pozycji; wypowiedź operatora ma pustą listę
- [x] 2.6 Test: to, co dotarło strumieniem w turze, zgadza się z tym, co zwraca transkrypt po jej zakończeniu

## 3. Terminal — strumień i stan

- [x] 3.1 `AgentStreamEvent` w `stream.ts` uczy się czwartego rodzaju; nieznane zdarzenia dalej wpadają w `default`
- [x] 3.2 `agentApi.ts` — DTO wywołania i `toolCalls` na wypowiedzi transkryptu, z pustą listą gdy pola nie ma
- [x] 3.3 `agentChatStore` gromadzi wywołania przy powstającej wypowiedzi i zachowuje je po `complete`
- [x] 3.4 Wywołania z transkryptu trafiają do tego samego kształtu co te ze strumienia
- [x] 3.5 Testy sklepu: wywołanie w trakcie tury, wywołanie po zerwaniu strumienia, przeładowanie sesji

## 4. Terminal — wpis w oknie czatu

- [x] 4.1 Komponent wpisu: zwinięty niesie nazwę i sposób zakończenia, rozwinięty argumenty i treść wyniku
- [x] 4.2 Odmowa, błąd serwera narzędzi i wywołanie udane są od siebie odróżnialne
- [x] 4.3 `AgentChat.tsx` renderuje wpisy w transkrypcie, w miejscu, w którym padły
- [x] 4.4 Odmowa narzędzia nie oznacza odpowiedzi agenta jako niepełnej
- [x] 4.5 Testy komponentu: rozwijanie, trzy sposoby zakończenia, tura bez wywołań

## 5. Domknięcie

- [x] 5.1 `uv run pytest`, `ruff check .`, `pyright` w `modules/agent`
- [x] 5.2 `pnpm test`, `pnpm lint`, `pnpm typecheck` w `modules/terminal`
- [ ] 5.3 Przejście ręczne na żywym stosie: pytanie, które sięga po narzędzia, w trakcie tury i po przeładowaniu sesji
- [x] 5.4 `openspec validate show-tool-calls-in-chat --strict`
- [x] 5.5 `review.md`
- [ ] 5.6 Pull request
