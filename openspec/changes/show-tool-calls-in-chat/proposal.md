## Why

13 sierpnia 2026 operator trzykrotnie zapytał agenta o US100 i trzykrotnie usłyszał, że
archiwum nie ma danych. Archiwum miało pełne trzy miesiące świec dziennych. Cztery
narzędzia market-mcp odrzucały własne odpowiedzi na walidacji schematu wyjściowego, a z
okna czatu nie dało się tego zobaczyć — agent odpowiadał uczciwie, bo tak wyglądały jego
wyniki, i to była jedyna widoczna warstwa. Przyczynę znaleziono dopiero zapytaniem `SELECT`
po tabeli `tool_calls` w bazie agenta.

Ślad wywołań istnieje i jest kompletny. Nikt go nie czyta: nie ma go ani na kontrakcie
modułu, ani w strumieniu tury. Operator patrzy na rozmowę, w której narzędzia albo działają,
albo nie, i nie ma z czego odróżnić jednego od drugiego.

## What Changes

- Strumień tury zyskuje **czwarty rodzaj zdarzenia**, obok `fragment`, `complete` i `error`:
  wywołanie narzędzia, wysyłane w chwili, w której się kończy, z nazwą, argumentami,
  wynikiem albo powodem odmowy oraz czasem trwania.
- Graf dostaje wywołanie zwrotne na zakończone wywołanie narzędzia — dziś ma je tylko na
  fragment tekstu (`on_delta`), więc runda narzędzi jest dla wołającego ciszą.
- `agent/contract.py` publikuje ślad wywołań przy wypowiedzi agenta, tak by przeładowana
  sesja pokazywała to samo, co pokazywała tura na żywo. Dane są w tabeli od pierwszego dnia
  — brakuje wyłącznie drogi na drut.
- Terminal renderuje wpis na wywołanie: zwinięty niesie nazwę i wynik, rozwinięty argumenty
  i treść odpowiedzi narzędzia.
- Wpis jest częścią transkryptu, a nie osobnym panelem diagnostycznym: stoi tam, gdzie padł,
  między wypowiedzią operatora a odpowiedzią agenta.

Nie jest to zmiana łamiąca: wołający, który nowego zdarzenia nie zna, pomija je tak samo jak
dowolne inne nieznane zdarzenie SSE, a `tool_calls` na wypowiedzi agenta jest polem
dodanym.

## Capabilities

### New Capabilities

Żadnej. Zmiana rozszerza to, co trzy istniejące zdolności już opisują.

### Modified Capabilities

- `agent-chat`: „Odpowiedź płynie strumieniem" — strumień niesie nie tylko powstający tekst,
  ale też wywołania narzędzi, którymi agent doszedł do odpowiedzi.
- `agent-tools`: „Wywołanie narzędzia zostawia ślad" — ślad przestaje być wyłącznie zapisem
  w bazie i MUST być czytelny dla wołającego, w turze i po niej.
- `terminal-agent-chat`: „Widać, że odpowiedź powstaje" — widać także, po co agent sięgnął i
  co dostał, zarówno w trakcie tury, jak i po powrocie do sesji.

## Impact

**agent** — `graph.py` (wywołanie zwrotne po rundzie narzędzi), `turn.py` (przełożenie go na
zdarzenie kolejki), `routers/sessions.py` (`_sse` dla nowego rodzaju), `contract.py` (kształt
wywołania na `MessageOut`), `store.py` (odczyt `tool_calls` dla transkryptu — dziś istnieje
wyłącznie zapis).

**terminal** — `stream.ts` (czwarty rodzaj zdarzenia), `agentChatStore.ts` (gromadzenie
wywołań przy powstającej wypowiedzi), `AgentChat.tsx` i nowy komponent wpisu, `agentApi.ts`
(ręcznie pisane DTO transkryptu).

**market-mcp, market-data, capital-gateway, infra** — bez zmian.

Kontrakt agenta nie przechodzi przez `pnpm contract:generate`; jego połową po stronie
terminala są ręcznie pisane DTO i testy terminala, i CI uruchamia zadanie terminala właśnie
dlatego, że `agent/contract.py` się zmienia.
