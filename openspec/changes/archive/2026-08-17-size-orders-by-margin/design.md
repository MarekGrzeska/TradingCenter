## Context

Zobacz `proposal.md` — Why. Stan, który kształtuje podejście:

- `capital-gateway` woła `GET /markets/{epic}` w `_market_open` i czyta z odpowiedzi
  `snapshot.marketStatus`. `instrument.marginFactor`, `instrument.marginFactorUnit`,
  `instrument.lotSize`, `instrument.currency` i całe `dealingRules` lecą do kosza.
- `Instrument` w `dtos.py` powstaje z **płaskiej** mapy rynku — tej, którą zwraca
  wyszukiwanie i obchód `marketnavigation`. Provider nie umieszcza w niej ani marży, ani
  zasad rozmiaru; są wyłącznie w opisie pojedynczego instrumentu.
- `trading-mcp` trzyma własny snapshot gatewayowego OpenAPI
  (`contract/capital-gateway.openapi.json`), pilnowany przez `scripts/contract.py check`.
- `teams` publikuje `ToolCallOut` z `arguments` i `result_text` od pierwszej wersji.
  Terminal je gubi w `mapRecordedToolCall` — mapuje pięć pól z dziewięciu. Ramka SSE
  `tool_call` też ich nie niesie.
- Budżet zapytań capital.com to 10/s liczone na rachunek, dzielone przez cały stos.

## Goals / Non-Goals

**Goals:**

- Model ma jak poznać marżę, krok i granice rozmiaru instrumentu, zanim złoży zlecenie.
- Przeliczenie „mam wydać X depozytu" na „wyślij rozmiar Y" jest wykonywane raz, w jednym
  miejscu, z zaokrągleniem zgodnym z tym, co provider i tak zrobi.
- Operator czyta w oknie outputów to samo, co czyta w transkrypcie czatu.

**Non-Goals:**

- Sufit ekspozycji liczony w depozycie po stronie `teams`. `max_order_size` zostaje tym,
  czym jest — liczbą w jednostkach instrumentu. Granica liczona w marży wymaga warunków
  instrumentu w module `teams`, a ten ich dziś nie czyta; to osobna zmiana i osobna decyzja
  operatora.
- Zmiana promptów zespołów. Reguła sizingu jest danymi operatora, nie kodem; ta zmiana daje
  narzędzia, którymi da się ją napisać.
- Cache warunków instrumentu.

## Decisions

**Warunki jako osobna trasa, nie jako pola na `Instrument`.**
`Instrument` jest budowany z płaskiej mapy rynku, w której providera tych pól nie ma.
Doklejenie ich tam znaczyłoby żądanie `GET /markets/{epic}` na każdy element listy — przy
katalogu liczonym w tysiącach i budżecie 10/s to nie jest lista, którą da się wczytać.
Odrzucone również dlatego, że `Instrument` jest kształtem, który czyta `market-data`;
poszerzenie go dotyka modułu, którego ta zmiana nie dotyczy.

**Cena jest argumentem `size_for_margin`, nie odczytem w module.**
Rozważona wersja, w której `trading-mcp` sam pyta gateway o bieżącą cenę — odrzucona, i to
jest najważniejsza decyzja w tej zmianie. Spec `trading-mcp-tools` mówi, że o rynek pyta się
archiwum, bo drugie źródło ceny w jednym przebiegu daje ślad, z którego nie widać, na czym
oparta była decyzja. Cena podana przez model trafia do `arguments` wywołania, więc po fakcie
widać, wobec jakiej ceny liczony był rozmiar — a przy okazji rozmiar i decyzja kierunkowa
opierają się o tę samą liczbę z archiwum.

**Przeliczenie w narzędziu, nie w prompcie.**
Alternatywa — narzędzie podaje same warunki, arytmetykę robi model — jest tańsza i została
odrzucona z pomiaru: model już raz policzył 2% jako wartość kontraktu zamiast jako depozyt,
a zaokrąglenie do kroku jest dokładnie tym miejscem, gdzie odpowiedź providera cicho różni się
od żądania. Narzędzie oddaje trzy liczby naraz — rozmiar, zajęty depozyt, wartość kontraktu —
więc rozbieżność między zamiarem a wynikiem jest widoczna w samej odpowiedzi.

**`Decimal`, i zaokrąglanie w dół.**
Krok rozmiaru bywa `0.001`; `float` zamienia oczywiste dzielenie w `0.0629999…`. Zaokrąglanie
do najbliższego kroku odrzucone: w górę zajmuje więcej depozytu, niż zadano, a granica, którą
da się przekroczyć zaokrągleniem, nie jest granicą.

**Nieznana jednostka wymogu depozytu to odmowa.**
Gateway podaje `margin_factor` razem z `margin_factor_unit` i nie przelicza. `trading-mcp`
umie `PERCENTAGE` i odmawia przy każdej innej, nazywając ją. Alternatywa — założyć procent,
bo w praktyce zawsze jest procent — daje przy pomyłce rozmiar o rząd wielkości nie ten,
i to bez żadnego objawu.

**Okno outputów doczytuje wywołania, SSE zostaje szczupłe.**
Trasa `/runs/{id}/tool-calls` istnieje i niesie `arguments` oraz `result_text`; terminal ma
już `teamsApi.runToolCalls`. Wystarczy, że `mapRecordedToolCall` przestanie te pola gubić,
a okno zawoła tę trasę przy otwarciu. Dołożenie `result_text` do ramki SSE odrzucone: wynik
`get_candles` z archiwum to kilobajty, a przebieg wysyła ramkę na każde wywołanie każdego
agenta — okno, które i tak może doczytać, nie jest powodem, żeby to wszystko przepychać przez
strumień do każdego podłączonego terminala.

**Kontrakt `teams` nie jest ruszany, więc `pnpm contract:generate` nie jest potrzebne.**
`ToolCallOut` ma te pola od początku, a wygenerowany `Wire["ToolCallOut"]` też — gubi je
dopiero ręczny mapper. Regeneracja jest potrzebna po stronie `trading-mcp`, ale to nie ten
generator: tam odświeża się snapshot gatewayowego OpenAPI, inaczej `contract.py check`
zaczerwieni CI przy pierwszej zmianie w `dtos.py`.

## Risks / Trade-offs

**Wyliczony depozyt jest wyliczeniem, nie kwotą z rachunku.** Provider może stosować marżę
schodkową rosnącą z ekspozycją, a wtedy faktycznie zajęta kwota będzie wyższa od podanej przez
narzędzie → odpowiedź nazywa liczbę tym, czym jest — wyliczoną z opublikowanego `marginFactor`
— a prawdą o rachunku pozostaje `get_balance`, wołane po złożeniu zlecenia.

**Jedno żądanie do providera więcej na każde wyliczenie rozmiaru.** Budżet 10/s jest wspólny
dla całego stosu → bez cache, bo marża potrafi się zmienić w ciągu dnia, a jedno wywołanie na
zlecenie to koszt tego samego rzędu co samo zlecenie. Gdyby to zaczęło uwierać, cache z krótkim
TTL jest zmianą lokalną w `trading-mcp` i nie rusza żadnego kontraktu.

**`marginFactor` z rachunku demo nie musi być tym samym, co na rachunku rzeczywistym** →
`trading-mcp` i tak odmawia startu poza demo, więc dziś nie ma gdzie się rozjechać; przy
rachunku rzeczywistym liczba i tak przychodzi od providera dla tego rachunku, nie z konfiguracji.

**Model może dalej liczyć rozmiar sam, ignorując narzędzie.** Nic go nie zmusza → sufit
`max_order_size` w `teams` zostaje ostatnią granicą, a ślad wywołań pokazuje, czy narzędzie
w ogóle padło. Wymuszanie go byłoby decyzją handlową w module, który ich nie podejmuje.

## Migration Plan

Brak schematu i brak migracji bazy. Kolejność wdrożenia wymuszona snapshotem kontraktu:
`capital-gateway` (nowa trasa) → odświeżony `contract/capital-gateway.openapi.json` →
narzędzia w `trading-mcp`. Terminal jest niezależny i może iść osobno.

Wycofanie: usunięcie dwóch narzędzi z `trading-mcp` wraca do stanu sprzed zmiany — trasa
w gatewayu jest dodatkiem, którego nikt inny nie czyta, a zespoły, które sizingu nie zmieniły,
działają tak samo przez cały czas.
