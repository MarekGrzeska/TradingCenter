## 1. Zapis: kolumna i kontrakt

- [x] 1.1 Migracja `agent`: `stopped boolean not null default false` na `messages` (D4)
- [x] 1.2 `agent/models.py` i `agent/store/messages.py`: `stopped` w domenie i w
      `append_agent_message`, obok istniejącego `incomplete`
- [x] 1.3 `agent/contract.py`: `stopped` na wypowiedzi publikowanej w transkrypcie
- [x] 1.4 Test `-m db`: wypowiedź zapisana jako zatrzymana odczytuje się jako zatrzymana i
      nie jest tym samym co urwana błędem

## 2. Granica zatrzymania w grafie

- [x] 2.1 `agent/graph.py`: sygnał zatrzymania w stanie tury i `stopped` w wyniku węzła
      `model`
- [x] 2.2 Przerwanie pętli `async for chunk in provider.stream(...)` po ustawieniu sygnału,
      ze zwrotem tego, co zdążyło się nazbierać (D3)
- [x] 2.3 Sprawdzenie sygnału na wejściu `call_model`, żeby runda po narzędziach nie
      zaczęła nowego wywołania modelu
- [x] 2.4 `after_model`: `stopped` prowadzi do `END` tak samo jak `failed`
- [x] 2.5 Testy grafu: zatrzymanie w połowie strumienia zwraca fragmenty sprzed sygnału;
      zatrzymanie w trakcie rundy narzędzi pozwala jej się rozstrzygnąć i nie woła modelu
      po raz kolejny

## 3. Tura i jej zapis

- [x] 3.1 `agent/turn.py`: `Stopped` obok `Complete` i `Failed`, wkładane do kolejki na
      końcu tury zatrzymanej
- [x] 3.2 `run_turn` przekazuje `stopped` do `append_agent_message`; zużycie i wywołania
      zapisują się tą samą ścieżką co zawsze (D6)
- [x] 3.3 Test: tura zatrzymana zapisuje wiersze zużycia; tura zatrzymana przed pierwszym
      fragmentem zapisuje pustą wypowiedź oznaczoną jako zatrzymana

## 4. Trasa zatrzymania

- [x] 4.1 Rejestr trwających tur na `app.state.agent` — wpis przy starcie, zdjęcie w
      `done_callback`, z komentarzem nazywającym założenie o jednym workerze (D2)
- [x] 4.2 `POST /sessions/{session_id}/stop`: filtr właściciela, `404` dla cudzej i
      nieistniejącej rozmowy, `204` gdy nic nie biegnie (D1)
- [x] 4.3 Zdarzenie `stopped` w strumieniu SSE, domykające generator (D5)
- [x] 4.4 Testy trasy: zatrzymanie kończy strumień zdarzeniem `stopped`; cudza rozmowa
      odpowiada jak nieistniejąca; zatrzymanie bez trwającej tury nie zmienia transkryptu;
      dwa kliknięcia pod rząd nie zapisują dwóch wypowiedzi

## 5. Terminal

- [x] 5.1 `agent/stream.ts`: zdarzenie `stopped` w typie strumienia
- [x] 5.2 `agent/agentApi.ts`: wywołanie trasy zatrzymania
- [x] 5.3 `agent/agentChatStore.ts`: `stop()`, stan tury po zatrzymaniu, przeładowanie
      transkryptu jak po każdej turze; odmowa trasy w toast bez oznaczania tury (D7)
- [x] 5.4 `agent/AgentChat.tsx`: Stop w miejscu przycisku wysyłania, widoczny wyłącznie gdy
      tura trwa
- [x] 5.5 Transkrypt odróżnia wypowiedź zatrzymaną od niepełnej i od błędu — w trakcie i po
      powrocie do sesji
- [x] 5.6 Testy terminala: kliknięcie woła trasę i nie oznacza tury samo; zdarzenie
      `stopped` oznacza wypowiedź; odmowa trasy mówi to wprost; po zatrzymaniu da się
      napisać następną wiadomość

## 6. Domknięcie

- [x] 6.1 `uv run pytest`, `uv run pytest -m db`, `ruff`, `pyright` w `workbench`
- [x] 6.2 `pnpm test`, `pnpm lint`, `pnpm typecheck` w `terminal`
- [x] 6.3 `openspec validate stop-a-turn-mid-answer --strict`
- [x] 6.4 `review.md` — co się okazało nieoczywiste przy granicy zatrzymania i przy
      wyścigu z końcem tury
