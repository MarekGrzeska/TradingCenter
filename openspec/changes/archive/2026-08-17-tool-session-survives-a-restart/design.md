## Context

Zobacz `proposal.md` — Why. Stan, który kształtuje podejście:

- `ToolServer` (`teams/tools/client.py`) trzyma jedną sesję w `self._session`, otwieraną
  leniwie pod `self._lock` i zamykaną dopiero przy awarii. Między wywołaniami żyje.
- `call()` łapie dziś `Exception` jednym `except`, robi `_disconnect()` i zwraca
  `ToolOutcomeKind.UNAVAILABLE`. Dlatego kolejny przebieg po awarii działa — i dlatego ten,
  w którym awaria wypadła, nie działa.
- Klient MCP na `404` z `POST /mcp` **nie** podnosi wyjątku HTTP. `streamable_http.py`
  wykrywa ten status i wstrzykuje do strumienia odpowiedzi błąd JSON-RPC
  `code=32600, message="Session terminated"`, który `ClientSession.call_tool` podnosi jako
  `McpError`. To jedyne miejsce w SDK, które ten komunikat produkuje.
- `useRunMonitor` czyta `/runs/{id}/tool-calls` raz, po pierwszym snapshocie, i dokleja
  wywołania ze strumienia na koniec listy. Ramka `tool_call` nie niesie `arguments` ani
  `result_text` — celowo, bo odpowiedź narzędzia bywa kilobajtowa, a strumień idzie do
  każdego podłączonego terminala.

## Goals / Non-Goals

**Goals:**

- Restart serwera narzędzi przestaje kosztować jedno wywołanie.
- Rozróżnienie „nie przyjęto" od „nie wiadomo" jest przeprowadzone tam, gdzie widać status
  odpowiedzi, a nie w prompcie.
- Operator czytający zakończony przebieg widzi treść każdego wywołania.

**Non-Goals:**

- Podtrzymywanie sesji pingiem ani wykrywanie restartu przed wywołaniem. Ping potwierdza
  sesję w chwili pinga, nie w chwili wywołania; problem zostaje, tylko robi się rzadszy
  i trudniejszy do odtworzenia.
- Ponawianie czegokolwiek poza tym jednym warunkiem.
- Zmiana promptów zespołów.
- Zmiana ramki SSE.

## Decisions

**Warunkiem ponowienia jest odpowiedź serwera, nie nazwa narzędzia.**
Rozważona wersja, w której ponawiane są wyłącznie wywołania czytające, a zapisujące nigdy —
odrzucona. Bramka sesji odrzuca żądanie **zanim** serwer zajrzy, o które narzędzie chodzi, więc
`404` niesie dokładnie tyle samo pewności dla `place_order`, co dla `get_balance`: żądanie nie
zostało obsłużone. Sortowanie po nazwie narzędzia dodałoby regułę, która nie wynika z niczego
w odpowiedzi, i zostawiłoby zlecenie niezłożone w jedynym przypadku, w którym wiadomo, że
można je bezpiecznie wysłać.

To jest też cała różnica wobec `trading-mcp-execution`, „Moduł nie ponawia zlecenia po własnej
awarii". Tamto wymaganie mówi o wywołaniu **gatewaya**, po którym skutek jest nieznany, i
zostaje w mocy bez zmiany. Tu warunek jest węższy o jedną rzecz, i to tę jedną, która
rozstrzyga.

**Wykrywane po `McpError` z komunikatem SDK, nie po statusie HTTP.**
Statusu tu nie widać — SDK zamienia `404` na błąd JSON-RPC, zanim `call()` cokolwiek dostanie.
Zostaje dopasowanie do `message == "Session terminated"` przy `code == 32600`. Dopasowanie do
napisu z cudzej biblioteki jest kruche i jest to świadomy koszt: alternatywą byłoby własne
opakowanie transportu, czyli utrzymywanie kawałka SDK. Kruchość jest **przykryta testem**,
który wywołuje prawdziwego klienta MCP przeciwko serwerowi odpowiadającemu `404` i sprawdza,
że ta ścieżka nadal kończy się ponowieniem — więc podniesienie SDK, które zmieni komunikat,
oblewa test, zamiast po cichu wyłączyć ponawianie.

**Ponowienie po `_disconnect()`, pod tym samym zamkiem co pierwsze połączenie.**
`_connected_session()` już serializuje otwieranie sesji, więc dwa agenty, które trafiły na
martwą sesję w tej samej chwili, odtworzą ją raz i oba wyślą po jednym żądaniu. Nic nowego do
zbudowania — to własność, którą ten zamek już ma.

**Jeden wpis w śladzie, bo `call()` zwraca jeden `ToolOutcome`.**
Ponowienie żyje w całości wewnątrz `call()`, a wiersz w `tool_calls` pisze `engine.py` z tego,
co `call()` zwróciło. Nie ma czego pilnować — poza tym, żeby nie dodać drugiego zapisu.
`duration_ms` obejmuje wtedy obie próby, i tak ma być: to czas, przez który model czekał.

**Okno doczytuje po zakończeniu i zastępuje listę, a nie dokleja.**
Po `runFinished` nagrane wiersze są kompletne i autorytatywne, więc podmiana całej listy jest
prostsza niż scalanie i przy okazji zamyka duplikat strumień+nagrane odnotowany jako otwarty
w `review.md` zmiany `size-orders-by-margin`. Rozważone alternatywy: doczytywanie przy
rozwinięciu wpisu (odrzucone — żądanie na kliknięcie, a wywołań w przebiegu bywają dziesiątki)
oraz dosłanie treści w ramce SSE (odrzucone przy poprzedniej zmianie i z tego samego powodu:
kilobajty na ramkę, do każdego terminala).

## Risks / Trade-offs

**Ponawiamy żądanie zmieniające rachunek.** Jeśli założenie „`404` znaczy, że nie obsłużono"
jest kiedyś nieprawdziwe, powstaje druga pozycja → warunek jest tak wąski, jak się dało go
zapisać, wykrywanie jest przykryte testem przeciwko prawdziwemu klientowi, a ponowienie jest
dokładnie jedno. Poza tym `teams` pisze wiersz w `trades` na każde wywołanie zapisujące, więc
gdyby to kiedyś zawiodło, ślad pokaże, co poszło.

**Dopasowanie do komunikatu z SDK.** Podniesienie `mcp` może zmienić napis → test opisany wyżej
jest tym, co to wyłapie; przy zmianie komunikatu poprawka to jedna stała.

**Restart w trakcie długiego wywołania.** Jeśli serwer padnie już po przyjęciu żądania, klient
zobaczy przekroczony czas albo zerwane połączenie, nie `404` → nie ponawiamy, i tak ma być.
Ta zmiana nie zmniejsza liczby przypadków „nie wiadomo"; usuwa jeden przypadek, w którym
wiadomo, a mimo to nic się nie działo.

## Migration Plan

Brak schematu i brak kontraktu do zmiany. `teams` i `terminal` wdrażają się niezależnie.
Wycofanie to usunięcie warunku ponowienia — moduł wraca do zachowania sprzed zmiany, bez
żadnego stanu do posprzątania.
