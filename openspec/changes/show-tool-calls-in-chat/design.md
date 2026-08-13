## Context

Motywacja jest w `proposal.md` — „Why". Stan, który ta zmiana zastaje:

- Tura płynie jednym `asyncio.Queue` z `turn.py` do `_sse` w `routers/sessions.py`, w trzech
  kształtach: `Fragment`, `Complete`, `Failed`. Terminal zna dokładnie te trzy i pomija
  każde zdarzenie, którego nie zna (`parseSseFrame`, gałąź `default`).
- Graf ma jedno wywołanie zwrotne — `on_delta`, niesione w stanie i wołane przy każdym
  fragmencie tekstu. Runda narzędzi (`run_tools`) nie woła niczego; jej wynik trafia do
  stanu i wraca do `turn.py` dopiero po zakończeniu całej tury.
- Zapis jest kompletny: `store.record_tool_calls` pisze wiersze z `round_index`, `position`,
  argumentami, wynikiem i czasem, a `store.get_tool_calls(message_id=...)` już je czyta.
  Kontrakt o nich nie wie — `MessageOut` niesie `content`, `model_id`, `incomplete`.

Trzy fakty z sesji 8 i 10 z 13 sierpnia 2026, na których opierają się decyzje poniżej:
wywołania trwały **18–69 ms**; jedno `list_tracked_pairs` odpowiedziało ~2 kB tekstu; a
odmowa wracała jako `outcome = 'refused'` z jednozdaniowym powodem.

## Goals / Non-Goals

**Goals**

- Operator widzi wywołanie w chwili, w której się rozstrzygnęło, bez czekania na koniec tury.
- Ten sam obraz po przeładowaniu sesji, z transkryptu.
- Odmowa narzędzia jest widoczna jako odmowa, a nie jako awaria odpowiedzi.

**Non-Goals**

- Ponowienie wywołania z panelu, edycja argumentów, „uruchom jeszcze raz". Podgląd czyta.
- Widok wywołań w zakładce kosztów — to inna zdolność i inne przekroje.
- Zmiana czegokolwiek w market-mcp. Ta zmiana pokazuje, co narzędzie odpowiedziało; tego,
  co odpowiada, nie dotyka.

## Decisions

### Jedno zdarzenie na rozstrzygnięte wywołanie, bez zdarzenia startu

Rozważane było parowanie „zaczęło się" / „skończyło się", żeby panel mógł pokazać wywołanie
w trakcie oczekiwania. Odrzucone przez pomiar: zapisane wywołania trwały 18–69 ms. Znacznik
oczekiwania żyłby przez czas krótszy niż jedna klatka i wymagałby identyfikatora do
sparowania obu zdarzeń po stronie terminala — złożoność płacona za mruganie.

Przypadek długi to nie wolne narzędzie, tylko serwer, który nie odpowiada; ten kończy się
`unavailable` po własnym limicie czasu (`agent-tool-access`, „Wołanie serwera narzędzi ma
skończony czas") i dociera jako zwykłe zdarzenie z tym wynikiem. Czekanie, które operator
naprawdę widzi w turze, jest czekaniem na model, a nie na narzędzie — i na nie panel ma już
swój wskaźnik.

### Wywołanie zwrotne w stanie grafu, tak jak `on_delta`

`run_tools` dostaje `on_tool_call`, niesione w `ConversationState` obok `on_delta` i wołane
po każdym rozstrzygniętym wywołaniu, zanim pętla przejdzie do następnego. Rozważane
alternatywy:

- **Emisja z `turn.py` po powrocie grafu** — prosta, ale zdarzenia docierałyby po całej
  turze, czyli po `complete`. To jest dokładnie ta funkcja, której nie ma dzisiaj.
- **Opakowanie `ToolServer.call`** — kusi, bo to jedno miejsce dla wszystkich wywołań, ale
  klient narzędzi nie wie, w której rundzie ani na której pozycji stoi wywołanie, a bez tego
  kolejność w panelu jest kolejnością przybycia, nie kolejnością w turze.

Stan grafu nie jest checkpointowany (`design.md` zmiany `add-agent-chat`), więc domknięcie w
stanie jest bezpieczne — to samo założenie, na którym stoi `on_delta`.

### `tool_calls` jako pole na `MessageOut`, nie osobna trasa

Rozważane było `GET /sessions/{id}/tool-calls`. Odrzucone: terminal i tak musiałby sparować
wywołania z wypowiedziami po `message_id`, czyli odtworzyć po stronie przeglądarki grupowanie,
które moduł ma za darmo. Pole na wypowiedzi to jedno żądanie zamiast dwóch i jedno miejsce, w
którym kolejność jest już ustalona.

Dla wypowiedzi operatora pole jest **pustą listą**, nie `null` — spec wymaga, by „bez
wywołań" i „wywołania odpadły po drodze" nie dały się pomylić, a `null` to właśnie ta pomyłka.

### Jedno zapytanie na transkrypt, nie jedno na wypowiedź

`store.get_tool_calls` czyta po `message_id`. Transkrypt czyta całą sesję, więc dochodzi
odczyt po `session_id`, grupowany w Pythonie. Sesja z czterdziestoma wypowiedziami to
inaczej czterdzieści zapytań na jedno żądanie HTTP — koszt bez powodu, w module, który ma
jedną trasę transkryptu.

### Wynik w całości, bez własnego sufitu

Spec wymaga, by wołający dostał tę treść, którą dostał model — streszczenie nie pozwala
stwierdzić, że model dostał co innego, a to jest cała wartość tego podglądu. Sufit i tak
istnieje, tylko po stronie market-mcp: ~2000 świec na odpowiedź, 200 punktów serii, 20
zakresów pokrycia. Największa zmierzona odpowiedź to ~2 kB.

Rozważane było przycinanie z flagą „obcięto". Odrzucone jako sufit nałożony na sufit —
gdyby transkrypty urosły na tyle, że to boli, dokłada się go wtedy, z pomiarem w ręku.

## Risks / Trade-offs

- **Transkrypt rośnie o treść wyników** → renderowany zwinięty, więc koszt jest w bajtach,
  nie na ekranie; rozmiar ograniczony sufitami market-mcp, do zmierzenia po wdrożeniu.
- **Argumenty i wynik idą prosto na ekran** → to treść z archiwum i z modelu, nie z
  przeglądarki, a panel renderuje ją jako tekst, nie jako znaczniki. Ten sam warunek, który
  już obowiązuje wypowiedź agenta.
- **Terminal sprzed zmiany wobec agenta po zmianie** → nieznane zdarzenie SSE wpada w gałąź
  `default` i jest pomijane, nowe pole na wypowiedzi jest ignorowane przez ręcznie pisane
  DTO. Rozjazd wersji nie psuje rozmowy.
- **Agent sprzed zmiany wobec terminala po zmianie** → brak pola `tool_calls` MUST czytać
  się jak pusta lista, inaczej panel wywraca się na starszym module. Do pokrycia testem
  terminala.

## Migration Plan

Migracji bazy nie ma — tabela `tool_calls` istnieje od `connect-agent-to-market-mcp` i ma
wszystkie potrzebne kolumny.

Kolejność: agent, potem terminal. Między jednym a drugim agent wysyła zdarzenie, którego
terminal nie zna i pomija — stan przejściowy jest tym samym stanem, co terminal sprzed
zmiany.

Wycofanie: rewert po stronie terminala wystarcza, żeby wrócić do panelu bez podglądu;
wiersze w `tool_calls` zostają, a strumień znów niesie zdarzenie, którego nikt nie czyta.

## Open Questions

Brak. Kształt wpisu w panelu — ikona, kolor, układ zwiniętej linii — jest decyzją
implementacyjną, a nie wymaganiem, i nie zmienia ani specyfikacji, ani podziału zadań.
