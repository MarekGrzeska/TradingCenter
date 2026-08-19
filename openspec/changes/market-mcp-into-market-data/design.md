## Context

Stan wyjściowy i pomiary: `proposal.md`. Wymagania: delty w `specs/`.

Trzy ograniczenia zastanego kodu kształtują całą resztę tego dokumentu:

1. **Kolejność importów w `market_data/app.py`.** `telemetry.configure()` stoi w linii 36,
   **przed** `from fastapi import FastAPI` w linii 38, bo autoinstrumentacja OpenTelemetry
   łata atrybut klasy `fastapi.FastAPI`, a `from ... import` wiąże nazwę w momencie importu.
   Cokolwiek importującego FastAPI albo Starlette wchodzi **poniżej** linii 36.
2. **`RequireCallerIdentity` nie jest `BaseHTTPMiddleware`** i jest to zapisana decyzja:
   `BaseHTTPMiddleware` buforuje ciało odpowiedzi w części wersji Starlette, co zabiłoby
   streamable HTTP. Dwa testy w repozytorium sprawdzają to przez `inspect.getsource`.
   Każdy mechanizm dokładany przed aplikacją musi trzymać tę samą formę — surowy ASGI.
3. **Easy Auth stoi przed aplikacją i autoryzuje aplikację, nie trasę.** Aplikacja dostaje
   tożsamość w nagłówkach `X-MS-CLIENT-PRINCIPAL-*` i to jest jedyne, co o wołającym wie.

## Goals / Non-Goals

**Goals:**

- Narzędzia sięgają po dane wywołaniem funkcji, nie po sieci — jeden hop zamiast dwóch.
- Wpuszczenie `agent` i `teams` do archiwum **nie** daje im dostępu do tras zapisujących.
- Kolejność wdrożenia taka, że w żadnej chwili nie istnieje produkcja, w której moduły mają
  prawo wejścia, a zapis tras jeszcze go nie ogranicza.

**Non-Goals:**

- `teams-mcp` — osobna zmiana, po tej.
- `trading-mcp` — kierunek C, świadomie nierozstrzygnięty.
- Zmiana kontraktu REST archiwum, terminala i czegokolwiek w danych.
- Scalanie `agent` z `teams` (kierunek B) — nic tutaj tego nie przesądza.

## Decisions

### D1. Narzędzia wołają warstwę domenową, nie routery i nie samych siebie po HTTP

Klient HTTP wołał sześć tras REST. W jednym procesie są trzy drogi:

- **(a) wołać funkcje routerów** — one przyjmują `Request` i zależności FastAPI, więc
  narzędzia związałyby się z frameworkiem i z kształtem HTTP, którego nie potrzebują;
- **(b) zostawić klienta i wołać `127.0.0.1`** — najmniejszy diff, zachowuje serializację,
  drugą pętlę zdarzeń i **cały snapshot kontraktu**, bo dwie kopie kształtów wciąż istnieją.
  To jest zmiana, która wygląda jak zysk i nie oddaje żadnego z kosztów, po które się szło;
- **(c) wołać tę samą warstwę domenową, którą wołają routery** — `store`, katalog
  wskaźników i ich komputery.

**Wybrane (c).** Narzędzia i routery stają się dwoma konsumentami jednej warstwy, co jest
dokładnie tym układem, który market-data ma już dziś między routerem a `store`. Cena:
tam, gdzie router robi coś ponad odczyt (limiter obliczeń wskaźników na `app.state`),
narzędzie musi wziąć to samo — inaczej powstaje druga droga do obliczeń bez sufitu
równoczesności. Wymienione w zadaniach jako osobna pozycja, bo to jest miejsce, w którym ta
migracja może cicho zgubić obronę.

### D2. `/mcp` jest montowane jako aplikacja ASGI, poniżej linii 36

`mcp.streamable_http_app()` jest aplikacją Starlette, nie routerem FastAPI, więc wchodzi
przez `app.mount("/mcp", ...)`. Import `mcp` i budowa serwera muszą stać poniżej
`telemetry.configure()` — patrz ograniczenie 1. Montaż odbywa się w `create_app()`, tam
gdzie dziś dołączane są routery.

Rozważane i odrzucone: przepisanie narzędzi na trasy FastAPI i wystawienie MCP „ręcznie".
Odrzucone, bo `outputSchema`, walidacja odpowiedzi i lista narzędzi to właśnie to, co daje
biblioteka, i to ona wykryła w tym repozytorium realną awarię odpowiedzi.

### D3. Autoryzacja per wołający: jeden zapis, jedno miejsce, surowy ASGI

Rozważane:

- **(a) `dependencies=` na routerach** — sprawdzenie rozsypane po siedmiu routerach, a
  `/mcp` nie jest routerem, więc i tak potrzebuje drugiego mechanizmu. Dwa mechanizmy dla
  jednej reguły to reguła, która rozjedzie się w jedną stronę;
- **(b) jedna warstwa ASGI przed całą aplikacją, z tabelą trasa → wołający.**

**Wybrane (b).** Jest to jedyne miejsce widzące obie powierzchnie naraz, więc regułę da się
przeczytać w całości i przetestować jako jedną rzecz. Forma jak w `RequireCallerIdentity` —
surowy ASGI, nie `BaseHTTPMiddleware` (ograniczenie 2).

Zapis rozróżnia trzy klasy: wołający narzędzi (`agent`, `teams`) → wyłącznie `/mcp`;
wołający REST (`terminal`) → REST bez `/mcp`; trasy bez tożsamości (`/ping`, `/ws/candles`)
→ przepuszczane, bo Easy Auth ich nie zasłania i mają własną obronę (bilet jednorazowy).

**Tożsamością jest identyfikator aplikacji wołającej**, ten sam, który stoi w
`allowed_applications`. Konfiguracja wymienia identyfikatory, nie nazwy: nazwa jest opisem,
identyfikator jest tym, co przyjeżdża w nagłówku.

**Trasa nieznana zapisowi jest odmawiana, nie przepuszczana.** Domyślne przepuszczenie
znaczyłoby, że nowa trasa REST jest otwarta dla agenta w dniu, w którym powstaje, i nikt
się o tym nie dowie.

### D4. WebSocket nie jest wyjątkiem przez przeoczenie, tylko przez zapis

`RequireCallerIdentity` przepuszcza scope `websocket` w całości — dla modułu MCP bez
WebSocketów jest to bez znaczenia, dla archiwum nie jest. `/ws/candles` **musi** zostać
osiągalne bez tożsamości, bo Easy Auth go nie zasłania, a broni go bilet jednorazowy
(`market-data-browser-access`). Nowa warstwa wypisuje to jako pozycję zapisu, nie
odziedzicza jako lukę. Wymaganie „trasa niosąca dane nie trafia na listę wyjętych spod
tożsamości" ma dla tego własny test.

### D5. `market-data` bierze `tc-mcp-kit`, a `CLAUDE.md` dostaje nowe uzasadnienie

Dziś `CLAUDE.md` uzasadnia istnienie osobnego `tc-mcp-kit` tym, że biorą go trzy moduły
MCP, **żaden z bazą danych** — i dlatego nie jest częścią `tc-runtime`. `market-data` bazę
ma, więc to zdanie przestaje być prawdziwe w dniu tej zmiany.

Rozważane: przenieść trzy pomocniki do `tc-runtime`. Odrzucone — rusza cztery moduły i trzy
locki, żeby uratować jedno zdanie. **Wybrane: `market-data` bierze `tc-mcp-kit`, a zdanie
w `CLAUDE.md` zostaje przepisane** na to, czym ten pakiet naprawdę jest: rzeczami
potrzebnymi temu, kto mówi MCP. Zapis jest częścią tej zmiany, nie sprzątaniem po niej —
uzasadnienie, które przestało być prawdziwe i zostało, jest dokładnie tym rodzajem dryfu
prozy, który rachunek nazywa drugim kodebase'em bez CI.

### D6. Wdrożenie w trzech krokach, i kolejność jest obroną, nie porządkiem

Ta zmiana ma połowę w kodzie i połowę w `terraform apply`, który jest operatora. Kolejność:

1. **Kod**: `market-data` serwuje `/mcp` i ma zapis autoryzacji; `market-mcp` stoi
   nietknięty. Produkcja działa jak dotąd — nikt jeszcze nie woła nowej trasy.
2. **`terraform apply`**: `agent` i `teams` wchodzą do `allowed_applications` archiwum,
   `MARKET_MCP_URL` i `MARKET_MCP_SCOPE` wskazują na archiwum. Dopiero tu narzędzia
   zaczynają iść nową drogą.
3. **Usunięcie**: moduł, App Service, workflow, triplet Entra, port w runnerze dev.

Krok 1 **musi** poprzedzać krok 2 i to jest własność bezpieczeństwa, nie estetyka: między
nimi nie istnieje chwila, w której moduły mają prawo wejścia do archiwum, a zapis tras
jeszcze ich nie ogranicza.

**Wycofanie** z kroku 2 to przywrócenie dwóch ustawień — `market-mcp` wtedy jeszcze stoi.
Po kroku 3 wycofaniem jest rewert zmiany, i dlatego krok 3 jest osobny.

## Risks / Trade-offs

- **Zapis autoryzacji jest jedyną rzeczą stojącą między agentem a `DELETE /pairs/{symbol}`.**
  Wcześniej agent nie miał do archiwum ani adresu, ani poświadczenia. → Kolejność z D6
  (kod przed tożsamościami), test odmowy dla **każdej** pary „tożsamość — powierzchnia, do
  której nie ma prawa", odmowa jako zachowanie domyślne dla trasy nieznanej zapisowi.
- **Zapis zapisu jest o jeden import od narzędzi.** Zakaz był dotąd spełniany konstrukcyjnie
  — narzędzia nie miały drogi do zapisu — a odtąd trzyma go test. → Test w
  `market-data-tools`; świadomie przyjęte i nazwane w delcie `market-mcp-upstream-access`
  jako zmiana ryzyka, a nie jako przeniesienie.
- **Pułapka `outputSchema`.** FastMCP serializuje `by_alias=True`; sam `serialization_alias`
  dał `'from_' is a required property` na czterech narzędziach — zielono w CI, zepsute na
  każdym realnym wywołaniu, bo `FastMCP.call_tool` (ścieżka testów) nie waliduje, a serwer
  lowlevel tak. → `conftest.py` dokładający walidację jedzie razem z narzędziami; bez niego
  ta klasa awarii wraca cicho.
- **Sufit powierzchni narzędzi może zniknąć w przeprowadzce.** → Test sufitu jest pozycją
  zadania, nie skutkiem ubocznym; wartość 19 700 znaków przenosi się bez zmiany.
- **Rozwiązanie zależności.** `mcp==1.27.0` przypięte dokładnie wchodzi do locka
  `market-data`, który ma własne ciężkie zależności. → Sprawdzane przy pierwszym zadaniu;
  konflikt jest tu wynikiem, który trzeba zobaczyć wcześnie, a nie na końcu.
- **Limiter obliczeń wskaźników.** Narzędzia obliczające wskaźniki muszą wziąć ten sam
  semafor, co router. → D1, osobna pozycja w zadaniach.
- **Klient MCP na pulpicie traci stdio.** → Świadomie, zapisane w `proposal.md` jako
  **BREAKING** i w delcie `market-mcp-transport` z uzasadnieniem. Droga po sieci zostaje.
