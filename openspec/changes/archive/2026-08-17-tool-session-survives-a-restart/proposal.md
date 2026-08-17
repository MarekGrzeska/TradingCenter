## Why

17 sierpnia 2026, 13:10 UTC, produkcja. Zespół miał złożyć jedno zlecenie MARKET na US100.
Nie złożył żadnego — i nie dlatego, że coś było nie tak ze zleceniem:

```
13:03:22  trading-mcp: Site stopped manually or container terminated   ← deploy
13:04:48  trading-mcp: Site started (8cbd54d)                          ← nowa pamięć sesji
13:10:34  teams: POST /mcp → 404 Not Found
          WARNI [teams.tools.client] tool call place_order failed: Session terminated
13:11:37  teams: Received session ID: 673a16f2… → 9 tools → następny przebieg działa
```

`teams` trzyma sesję MCP otwartą między wywołaniami i nie dowiaduje się, że serwer po
drugiej stronie wstał od nowa. Sesja umarła razem ze starym kontenerem, a dowiedziało się
o tym pierwsze wywołanie po deployu — którym akurat było zlecenie.

**Agent zachował się poprawnie i nie jest tu do naprawy.** Prompt operatora mówi mu wprost:
„nie składaj drugiej próby, jeśli wywołanie nie zwróci czystego potwierdzenia". Ta reguła
jest dobra i ma zostać: model nie odróżnia `404` od przekroczonego czasu, a ponawianie
w prompcie na każdą awarię dostępu kupuje podwójne pozycje w zamian za ten jeden przypadek.
Odróżnić jedno od drugiego potrafi warstwa, która widziała status HTTP — i tam należy
naprawa.

Drugi brak wyszedł przy tej samej awarii: okno outputów pokazało przy tym wywołaniu „treść
nie została jeszcze odczytana", czyli nie pokazało ani argumentów, ani odpowiedzi —
dokładnie przy tym jednym wywołaniu, przy którym były potrzebne. To luka zapisana wprost
w `review.md` zmiany `size-orders-by-margin`, która ugryzła przy pierwszym prawdziwym użyciu.

## What Changes

- `teams` ponawia wywołanie **raz**, po ponownym otwarciu sesji, wyłącznie gdy serwer
  odrzucił żądanie z powodu nieznanej sesji. Każda inna awaria — przekroczony czas, `5xx`,
  zerwane połączenie — zostaje tym, czym jest dzisiaj: `unavailable`, bez powtórzenia.
- Ślad zostaje jednym wierszem na wywołanie: ponowienie transportu nie jest drugim
  wywołaniem modelu i nie ma powodu, żeby wyglądało w śladzie na dwa.
- Okno outputów doczytuje nagrane wywołania po zakończeniu przebiegu, więc operator czytający
  zakończony przebieg widzi argumenty i odpowiedź każdego wywołania — także tych, które
  przyszły strumieniem już po podłączeniu.

Czego ta zmiana **nie** robi: nie rusza wymagania `trading-mcp-execution` „Moduł nie ponawia
zlecenia po własnej awarii". To wymaganie mówi o `trading-mcp` i o awarii wywołania gatewaya,
po której skutek żądania jest nieznany. Tu chodzi o warstwę wyżej i o warunek węższy —
o odpowiedź, która **dowodzi**, że żądanie nie zostało obsłużone. Ramka SSE `tool_call`
zostaje bez zmian.

## Capabilities

### New Capabilities
- brak

### Modified Capabilities
- `teams-tool-access`: wywołanie odrzucone z powodu nieznanej sesji jest ponawiane raz po
  jej odtworzeniu; każda inna awaria dostępu nadal nie jest ponawiana
- `terminal-teams`: okno outputów doczytuje treść wywołań po zakończeniu przebiegu

## Impact

Kod: `teams` (`teams/tools/client.py`), `terminal` (`src/teams/useRunMonitor.ts`).

Kontrakty: żaden. Trasa `/runs/{id}/tool-calls` i `ToolCallOut` już niosą wszystko, czego
okno potrzebuje; ramka SSE zostaje szczupła celowo, bo to ona jest powodem, dla którego
doczytanie w ogóle jest potrzebne.

Ryzyko, które ta zmiana świadomie bierze na siebie: ponowienie żądania zmieniającego rachunek.
Bierze je tylko tam, gdzie serwer sam powiedział, że żądania nie przyjął — i `design.md`
nazywa, na czym ta pewność stoi oraz co ją może podważyć przy zmianie SDK.

Obie dotknięte zdolności — `teams-tool-access` i `terminal-teams` — nie leżą jeszcze
w `openspec/specs/`, tylko w deltach niezarchiwizowanych zmian (`add-teams-module`,
`add-trading-tools`, `size-orders-by-margin`). Delty tej zmiany są pisane jako `ADDED`, a przy
archiwizacji kolejność jest: tamte przed tą.
