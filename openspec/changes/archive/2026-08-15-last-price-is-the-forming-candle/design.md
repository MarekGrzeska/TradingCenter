## Context

Powód jest w `proposal.md` — „Why". Stan, który ta zmiana zastaje:

- `candle_sink` (`app.py`) dostaje z ingestu **każdą** świecę, w toku i zamkniętą. Zamkniętą
  zapisuje wewnątrz uchwytu pokoju; tę w toku wyłącznie publikuje.
- `Hub.publish` woła `self._room(...)`, a `_room` to `setdefault` — pokój powstaje przy
  pierwszej publikacji, bez subskrybentów. `Room.forming` żyje więc dla każdej śledzonej
  pary z działającym feedem, także wtedy, gdy nikt nie patrzy.
- `Hub.unsubscribe` usuwa pokój tylko wtedy, gdy nie ma ani subskrybentów, **ani** świecy w
  toku. Pokój z żywym feedem nie znika.
- `ingest/live.py` prowadzi jedną subskrypcję na śledzoną parę — czyli na (symbol,
  rozdzielczość). US100 jest śledzony na HOUR, HOUR_4 i DAY, i każda z nich ma własną świecę
  w toku. MINUTE nie jest śledzony wcale.
- `MarketStatus.of(instruments, symbol)` zwraca `(status, open?)` z minutowym cache. Istnieje
  dla listy par i nie zmienia się tutaj.
- `deps.hub` bierze `WebSocket`, nie `Request` — WebSocket nie jest requestem i FastAPI nie
  ma czego wstrzyknąć w drugą stronę.

## Goals / Non-Goals

**Goals**

- Cena bieżąca jednym żądaniem HTTP, bez uścisku dłoni WebSocketa i bez biletu.
- Model pytający „ile teraz kosztuje" nie musi wiedzieć, na jakiej rozdzielczości para jest
  śledzona.
- Brak ceny bieżącej niesie swój powód, rozróżnialny.

**Non-Goals**

- Utrwalanie świecy w toku. Zmienia się przy każdym kwotowaniu i zaniża własny zakres —
  powód, dla którego nie ma jej w bazie, nie zmienia się tutaj.
- Strumień dla agenta. MCP jest pytaniem i odpowiedzią; ciąg zmian to inna zdolność i inny
  transport.
- Nowe narzędzie w market-mcp. Rozstrzygnięte z operatorem: jedno miejsce na „ile teraz
  kosztuje", nie dwa podobne.
- Terminal. Ma świecę w toku ze strumienia, którym rysuje wykres; druga droga do tej samej
  rzeczy nic mu nie daje.

## Decisions

### Wybór rozdzielczości należy do archiwum, nie do wołającego

Bez wskazanej rozdzielczości moduł odpowiada z najdrobniejszej śledzonej, która świecę w
toku **ma** — nie z najdrobniejszej śledzonej w ogóle. Różnica jest cała: para śledzona na
MINUTE i HOUR, której minutowy feed stoi, ma cenę na HOUR, a wybór po samej liście par
oddałby „brak".

Rozważane było zostawienie wyboru wołającemu, tak jak w `get_candles` i `summarize_range`.
Odrzucone: to jedyne narzędzie, którego pytanie brzmi „ile teraz", a nie „co się działo w
oknie". Model musiałby najpierw wołać `list_tracked_pairs`, żeby nie trafić w rozdzielczość,
której dla tej pary nikt nie zbiera — jedna tura i jedno wywołanie więcej za wybór, który na
cenę nie wpływa: zamknięcie świecy w toku to ostatnie kwotowanie, niezależnie od tego, w
jakim koszyku siedzi.

Wskazana rozdzielczość jest honorowana. To ta sama trasa dla konsumenta, który wie, czego
chce — a taki ma prawo dostać dokładnie ten koszyk.

### Trasa czyta pamięć huba, nie bazę

Świeca w toku nie jest nigdzie zapisana, więc trasa czyta `Room.forming` wprost.
Rozważane alternatywy:

- **Zapisywać świecę w toku do osobnej tabeli i czytać ją stamtąd** — zamienia zapis raz na
  okres na zapis raz na kwotowanie, dla danych, które i tak są nieprawdziwe do zamknięcia
  okresu. Odrzucone jako odwrócenie decyzji, którą ta zmiana ma zostawić w spokoju.
- **Wystawić klienta WebSocketowego w market-mcp** — narzędzie MCP jest pytaniem i
  odpowiedzią; subskrypcja na czas jednego wywołania to uścisk dłoni i bilet za jedną liczbę,
  a wynik i tak byłby pierwszym snapshotem.

**Bez uchwytu pokoju** — pisane w propozycji odwrotnie i poprawione przy implementacji.
`publish` przypisuje `room.forming` między dwoma `await`-ami, więc czytelnik widzi świecę
sprzed albo sprzed po, nigdy połowy jednej z nich; asyncio nie wywłaszcza między
instrukcjami. Wzięcie zamka nie dokłada niczego do tej gwarancji, a każe odczytowi
przeczekać zapis do bazy i rozgłoszenie do wszystkich subskrybentów, które ten sam zamek
trzymają.

Odczyt MUST NOT używać `_room` — to `setdefault`, a `unsubscribe` sprząta wyłącznie pokoje,
na które trafi. Pokój utworzony przez odczyt symbolu, którego nikt nie subskrybuje, nie
zostałby usunięty nigdy. Stąd `.get` i test na `room_count`.

`deps.hub` bierze `WebSocket`, więc trasa HTTP potrzebuje własnej zależności czytającej
`request.app.state.hub`. Dwie funkcje, jedno źródło — FastAPI rozstrzyga zależność po
adnotacji, a `Request | WebSocket` nie jest czymś, co umie podać na którymkolwiek
transporcie.

### Odpowiedź niesie stan rynku, a nie tylko świecę

Trzy „nie ma ceny" prowadzą operatora gdzie indziej: para nieśledzona (dodaj ją), rynek
zamknięty (wróć w poniedziałek), rynek otwarty i cisza (zbieranie stoi — to awaria). Trzeci
jest jedynym, który wymaga czegoś od operatora **teraz**, i jedynym, który bez nazwania
czyta się jak dwa pozostałe.

`MarketStatus` już to wie i już jest wołany raz na minutę na parę przy liście — ten sam cache
obsługuje tę trasę bez dokładania ruchu do gatewaya.

### `get_last_price` zmienia zachowanie, nie kształt wywołania

Rozważane było `get_live_price` obok istniejącego. Odrzucone z operatorem: dwa narzędzia o
niemal tym samym opisie to tury, w których model sięga po drugie, a pytanie „ile teraz
kosztuje" ma jedną poprawną odpowiedź, nie dwie do wyboru.

`resolution` przestaje mieć wartość domyślną `MINUTE` i staje się opcjonalne — pominięte
znaczy „wybierz sam". Odpowiedź nazywa rozdzielczość, której użyto, bo może się różnić od
żądanej i model nie ma innej drogi, żeby to zauważyć.

## Risks / Trade-offs

- **Świeca w toku żyje w pamięci procesu** → jeden proces w produkcji dziś; przy dwóch
  instancjach odpowiedź zależałaby od tego, która odebrała żądanie, a każda ma własny feed i
  własny pokój. Do nazwania, gdy skalowanie stanie się pytaniem — nie jest nim teraz.
- **Model poda maksimum okresu w toku jako maksimum dnia** → znacznik „w toku" jest polem
  odpowiedzi, nie zdaniem w notatce, a prompt agenta już mówi, czego dane nie znaczą.
  Zostaje ryzykiem modelu, nie kontraktu.
- **`MarketStatus` woła gateway** → cache minutowy istnieje właśnie po to; przy gatewayu
  niedostępnym status jest nieznany i odpowiedź MUST to nazwać zamiast zgadywać otwarcie.
- **Snapshot schematu w market-mcp i wygenerowany kontrakt terminala pójdą w rozjazd** →
  `pnpm contract:generate` i `scripts/contract.py check` są tym, co to wyłapuje, i oba są w
  zadaniach.

## Migration Plan

Migracji bazy nie ma i nie będzie — ta zmiana istnieje po to, żeby świeca w toku dalej nie
była zapisywana.

Kolejność: market-data, potem market-mcp. Między jednym a drugim `get_last_price` odpowiada
tak jak dzisiaj, bo pyta o zakres świec zamkniętych i nic w tym nie przestaje działać.

Wycofanie: rewert po stronie market-mcp wystarcza, żeby wrócić do ostatniej świecy
zamkniętej; trasa w market-data zostaje wtedy nieużywana, a nie zepsuta.

## Open Questions

Brak. Nazwa trasy i to, czy świeca w toku jedzie osobnym polem, czy tym samym kształtem co
`CandleOut` ze znacznikiem, są decyzjami implementacyjnymi — kontrakt wymaga, żeby dało się
je odróżnić, i nie przesądza, którą literą.
