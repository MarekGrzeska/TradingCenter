## Context

Patrz proposal.md — Why. Istnieją dwa spike'y i każdy rozwiązał połowę problemu; ten projekt
składa je w jedną usługę.

Co ustaliły spike'y — wszystko zmierzone na działającym kluczu, nie wyczytane z dokumentacji. Te
liczby kształtują projekt, więc są tu zapisane:

| Ograniczenie | Wartość |
|---|---|
| Świec na żądanie | 1000 (`1001` → `error.invalid.max`) |
| Szerokość okna dat | najwyżej `(liczba − 1) × rozdzielczość` (okno liczy obie krawędzie) |
| Format `from`/`to` | `YYYY-MM-DDTHH:MM:SS`, UTC, bez strefy |
| Kierunek wyników | od `from` w przód, nie od `to` wstecz |
| Poza dnem historii | `error.prices.not-found` |
| Czas życia sesji | ~10 minut bezczynności; tokeny są *nagłówkami* odpowiedzi |
| Uwierzytelnienie strumienia | tokeny idą **w każdej wiadomości**, nie w nagłówkach połączenia |
| Ping strumienia | co najmniej raz na 10 minut |
| Limit zapytań | 10 żądań/sekundę |
| Częstość `ohlc.event` | 0 na 60 s na US100 przy `MINUTE_5` — tylko przy zamknięciu |
| Częstość `quote` | 296 na 60 s na tym samym instrumencie |
| Duplikacja `ohlc.event` | dwa razy na świecę: `priceType` `bid` i `ask` (~1,8 pkt różnicy na US100) |
| Koszt głębokiego odczytu | `OIL_CRUDE` `MINUTE_5` × 20 000 → 30 żądań, 26,2 s |
| Głębokość historii | `DAY` sięga 1991 na US100; `MINUTE_5` około dwóch lat |

Dwa fakty napędzają większość tego, co dalej. Po pierwsze, model poświadczeń streamingu wyklucza
zwykłe reverse proxy — coś musi być właścicielem wychodzącego połączenia i wstrzykiwać tokeny do
każdej wiadomości. Po drugie, `ohlc.event` odpalający się zero razy w ciągu minuty znaczy, że
strumień niosący wyłącznie zamknięte świece wygląda na zepsuty; świeca w budowie musi wziąć się
skądinąd.

## Goals / Non-Goals

**Goals:**

- Jeden proces, jeden kontrakt, trzy sprawy: handel, odczyt historii, strumień.
- Dziwactwa providera zamknięte w adapterze — konsument nigdy nie dowiaduje się, czym jest
  `dealReference` albo `epic`.
- Świeca w budowie zdefiniowana raz, w module, żeby każdy konsument widział tę samą świecę.
- Zła konfiguracja wywala start głośno, a nie przy pierwszym zleceniu.

**Non-Goals:**

- Zero składowania. Ten moduł jest oknem na capital.com, nie jego archiwum. Magazyn to w tym
  ekosystemie robota `market-data`, a powielanie go tutaj dałoby jednej świecy dwa źródła.
- Brak warstwy abstrakcji nad providerem. Jeden provider, jeden adapter.
- Brak UI. Terminal w Reakcie to późniejszy moduł, konsumujący ten po HTTP i WebSockecie.
- Brak konta live, przy jakiejkolwiek konfiguracji.

## Decisions

### Python 3.12 + FastAPI

Wybrane ponad Node/TypeScript i C#/.NET.

Praca to prawie wyłącznie współbieżne I/O: kilkadziesiąt sekwencyjnych stron HTTP, trwałe
wychodzące połączenie WebSocket i rozgłaszanie do subskrybentów. `asyncio` obsługuje wszystkie
trzy jednym modelem, a połowa handlowa już istnieje w Pythonie — adapter, DTO, mapping i testy
mockowane przez `respx` przenoszą się prawie bez zmian. FastAPI publikuje OpenAPI z tych samych
modeli pydantic, które walidują wejście, więc kontrakt nie może rozjechać się z kodem, który go
obsługuje.

Node był alternatywą z mocniejszym prawem do połowy streamingowej: `server/capitalPlugin.js` jest
dziś działającym relayem. Ale wzięcie go oznacza przepisanie połowy handlowej od zera i rozbicie
ekosystemu na dwa języki dla jednego modułu. C# typuje najlepiej i jest językiem, który Marek zna
najlepiej, ale nic z obu spike'ów nie przeżyłoby portu, a jego prawdziwa przewaga — rzeczywista
równoległość — nic nie daje przy pracy, która czeka na sockety.

GIL nie jest tu ograniczeniem z tego samego powodu: żaden krok nie jest CPU-bound.

Zależności, każda zasługująca na swoją linię: `fastapi`, `uvicorn[standard]`, `httpx`
(asynchroniczny REST), `websockets` (wychodzący strumień), `pydantic-settings` (konfiguracja).
Deweloperskie: `pytest`, `pytest-asyncio`, `respx` (mockowanie HTTP), `ruff`. Narzędzie to `uv`.

### Układ

```
modules/capital-gateway/
  capital_gateway/
    app.py            złożenie FastAPI, lifespan, obsługa błędów
    config.py         ustawienia + bezpiecznik demo-only
    dtos.py           kontrakt: Instrument, Candle, Account, Position, Order, …
    errors.py         typ błędu modułu → status HTTP
    client.py         cienki asynchroniczny klient REST: auth, tokeny, jeden retry na 401
    adapter.py        surowe payloady capital.com ⇄ DTO; asynchroniczne rozliczenie
    mapping.py        funkcje czyste, zero I/O — testowalne samymi fixture'ami
    history.py        stronicowanie wstecz poza limit 1000 wierszy
    stream/
      upstream.py     jedno wychodzące połączenie na (epic, resolution): subskrypcje, ping, reconnect
      forming.py      kwotowania → świeca w budowie. Czyste, zero I/O
      hub.py          pokoje, rozgłaszanie, cykl życia
      messages.py     publikowane kształty wiadomości WebSocketa
  tests/
    fixtures/         nagrane payloady providera
  pyproject.toml
  README.md
```

`mapping.py` i `stream/forming.py` celowo nie mają I/O: dwa miejsca, w których najłatwiej pomylić
się co do semantyki providera, to dwa, które da się przetestować bez socketu.

### Świeca w budowie mieszka po stronie serwera

Dziś ta logika jest hookiem Reacta, więc jest osiągalna wyłącznie z przeglądarki. Przeniesienie
jej do `stream/forming.py` sprawia, że agent, backtest i przyszły terminal dzielą jedną definicję
bieżącej świecy, zamiast pisać trzy.

Reguła: znacznik czasu kwotowania jest zaokrąglany w dół do rozdzielczości, żeby znaleźć jego
okres. Kwotowanie w bieżącym okresie rozciąga maksimum i minimum oraz przesuwa zamknięcie;
kwotowanie w okresie późniejszym otwiera nową świecę. Gdy w końcu przyjdzie `ohlc.event`,
nadpisuje — widział cały okres, a moduł widział go dopiero od chwili podłączenia.

Kubełkowanie arytmetyczne jest poprawne tylko wewnątrz dnia. Granice `DAY` i `WEEK` idą za sesją
rynku, nie za północą UTC, więc przy tych rozdzielczościach kwotowania rozciągają ostatnią znaną
świecę, a granicę przesuwa dopiero zamknięta świeca od providera. Zgadywanie dałoby tam świecę,
która wygląda poprawnie i jest błędna.

### Strumień niesie `candle` i `quote`, nie kształty providera

`{kind: "candle", forming: true|false, …}` to jest to, co konsumuje wykres — jeden rodzaj
wiadomości, upsert po znaczniku czasu. `{kind: "quote", bid, ask, …}` zostaje obok, bo spread jest
potrzebny przy egzekucji i nie może czekać na zamknięcie świecy. `{kind: "status"}` i
`{kind: "error"}` niosą informację o żywotności.

Surowy `ohlc.event` providera nie jest przepuszczany dalej: przychodzi dwa razy na świecę, po
razie na stronę ceny, a przepuszczenie obu jest dokładnie tym, co sprawia, że wykres skacze przez
spread.

### Strona bid, wszędzie

Historia REST wystawia obie strony na każdej krawędzi świecy; strumień w trybie `classic` wystawia
jedną. Wzięcie bid w obu miejscach jest tym, co sprawia, że historia i dane na żywo łączą się bez
skoku. To konwencja, nie prawda — zapisana tutaj, bo szew jest niewidoczny, dopóki nie jest zły.

### Głębokie stronicowanie kotwiczy na danych, nie na zegarze

Każde kolejne okno jest kotwiczone na najstarszej faktycznie pobranej świecy. Kursor liczony
kalendarzowo dryfuje przez weekend albo święto, bo provider zwraca wtedy grubo mniej świec, niż
sugeruje okno; kotwiczenie na danych kosztuje jedno żądanie więcej zamiast dziury. Pętla kończy
się na `error.prices.not-found`, na oknie niedającym nic starszego albo na żądanej liczbie.

Głęboki odczyt to długie żądanie HTTP — 26 s w najgorszym zmierzonym przypadku. Zostaje zwykłym
żądaniem, a nie zadaniem z endpointem do odpytywania: zadanie potrzebuje stanu, a ten moduł stanu
nie ma. Odpowiedź podaje liczbę żądań, więc koszt jest widoczny.

### `BrokerPort` znika

`typing.Protocol` jest strukturalny: nic nie deklaruje, że implementuje port, i dopiero adnotacja
typu `BrokerPort` każe checkerowi je porównać. `broker-gateway` takiej adnotacji nie ma — `app.py`
typuje swoją zależność jako konkretny adapter — więc port jest dziś sprawdzany przez nic. Jest
komentarzem w kształcie typu. DTO zostają, bo one *są* kontraktem HTTP. Drugi broker, jeśli
kiedykolwiek się pojawi, dostanie interfejs wyciągnięty z działającego adaptera, co jest robotą
mechaniczną.

*(W kategoriach C#: `interface` jest nominalny i kompilator go wymusza; `Protocol` jest
strukturalny i nie wymusza niczego, dopóki nie skieruje się na pasującą adnotację type checkera.)*

### Demo-only jest sprawdzane przy starcie

`config.py` odrzuca każdy adres bazowy i adres strumienia, który nie jest hostem demo, zanim
powstanie obiekt aplikacji. Bezpiecznik działający dopiero na endpointach handlowych zostawiłby
uwierzytelnioną i czytelną sesję live; odmowa startu nie zostawia niczego, czego dałoby się użyć.

## Risks / Trade-offs

**Głęboki odczyt może przeżyć timeout klienta (zmierzone 26 s, możliwe gorsze instrumenty)** →
odpowiedź podaje liczbę żądań i pokrycie; konsument potrzebujący większej głębokości pyta
o węższy zakres. Jeśli stanie się to normą, odpowiedzią jest zadanie z endpointem do odpytywania,
a to osobna zmiana.

**Równoległe głębokie odczyty mogą wyczerpać budżet 10 żądań/s** → wywołania do providera idą
przez jedną ograniczoną bramkę, więc drugi głęboki odczyt czeka w kolejce, zamiast wywołać odmowę
z limitu, która wyglądałaby jak błąd danych.

**Świeca w budowie po restarcie zaniża swój zakres** → jest oznaczona `forming: true` i spec mówi
to wprost. Wskaźnik policzony na niej przemalowuje się; jest do patrzenia, nie do backtestu.

**Brak składowania znaczy brak historii poza tym, co trzyma provider** → `MINUTE_5` to około dwóch
lat i nic nie odzyska tego, co jest dalej. Przyjęte: archiwizacja to robota innego modułu.

**Odnawianie sesji przy współbieżności mogłoby wywołać stampede** → jedno trwające logowanie jest
dzielone przez wszystkich czekających, a 401 wywołuje dokładnie jedno ponowne logowanie i jedno
ponowienie.

**Połączenie z providerem może paść po cichu** → moduł pinguje z dużym zapasem wobec tolerancji
providera, publikuje `status: reconnecting` przy zerwaniu i wznawia, dopóki są subskrybenci.

**Handel na koncie demo dowodzi mniej, niż się wydaje** → wykonania są symulowane, a płynność demo
nie jest prawdziwą płynnością. Moduł twierdzi coś o poprawności kontraktu, nie o jakości
egzekucji.

## Migration Plan

Nie ma czego migrować: TradingCenter jest pusty, a ta zmiana ustanawia jego układ. TradingHub
działa nietknięty; tamtejszy `broker-gateway` jest zastąpiony, ale jego wygaszenie to osobna
decyzja.

Wycofanie to skasowanie katalogu modułu — trwała własność, dla której zachowania istnieją reguły
modułów w tym ekosystemie.

## Open Questions

- Czy kształty wiadomości WebSocketa są publikowane jako plik JSON Schema w repozytorium, czy
  tylko udokumentowane w README. Dotyczy możliwości wygenerowania typów po stronie konsumenta,
  nie zachowania, więc może poczekać do pojawienia się pierwszego konsumenta.
- Co mówi konstytucja samego repozytorium — plik, który określałby konwencje, zasady i kontrakt
  modułów dla TradingCenter, nie jest jeszcze napisany i został świadomie odłożony, a nie
  skopiowany z TradingHub.
