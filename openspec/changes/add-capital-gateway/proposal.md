## Why

Dwa spike'y udowodniły po jednej połowie capital.com i żadnej z nich nie da się użyć z zewnątrz.
`TradingHub/modules/broker-gateway` (Python/FastAPI) handluje, ale deklaruje
`has_streaming: false` i pobiera najwyżej 1000 świec. `TwelveDataTest` (plugin dev-serwera Vite)
streamuje świece na żywo i schodzi 20 000 świec wstecz, ale jego wiedza siedzi w hooku Reacta
i w pluginie Vite — dostępna wyłącznie z karty przeglądarki i tylko dopóki działa dev-serwer.

TradingCenter jest następcą ekosystemu TradingHub. Jego pierwszy moduł składa oba spike'y w jedną
usługę, żeby handel, głęboka historia i strumień na żywo pochodziły z jednego kontraktu, który
zje agent, backtest i przyszły terminal w Reakcie.

## What Changes

- Nowy moduł `modules/capital-gateway` — usługa FastAPI, jedyne miejsce wiedzące o istnieniu
  capital.com.
- **Handel**, przeniesiony z `broker-gateway`: konta, przełączanie aktywnego konta, pozycje,
  zlecenia MARKET/LIMIT/STOP, dołączone SL/TP, zmiana pozycji, zlecenia oczekujące oraz
  asynchroniczne rozliczenie `dealReference → confirms`.
- **Głęboka historia**, przeniesiona ze spike'u `TwelveDataTest`: świece stronicowane wstecz poza
  limit 1000 wierszy, kotwiczone na najstarszej już pobranej świecy, a nie na zegarze.
- **Strumień na żywo**, nowy jako publikowany kontrakt: wychodzący WebSocket dla konsumentów
  niosący `candle` (w budowie i zamkniętą) oraz `quote`. Jedno połączenie z providerem na parę
  `(epic, resolution)` dzielone przez wszystkich subskrybentów.
- **Świeca w budowie składana po stronie serwera**, nie u konsumenta. Kubełkowanie kwotowań
  wychodzi z hooka Reacta, w którym siedzi dziś, więc każdy konsument widzi jedną definicję
  bieżącej świecy.
- **Wyłącznie demo.** Adres bazowy inny niż host demo jest odrzucany przy starcie. Ten moduł nie
  jest w stanie złożyć zlecenia za prawdziwe pieniądze.
- **`BrokerPort` znika, neutralne DTO zostają.** DTO są kontraktem HTTP. Protokół nie jest dziś
  w `broker-gateway` referencjonowany przez nic wykonywalnego — `app.py` typuje swoją zależność
  jako konkretny adapter — więc nie wymusza niczego, co pozornie wymusza.
- **Zero składowania.** Historia jest stronicowana od providera na żądanie; nic nie jest
  zapisywane.

## Capabilities

### New Capabilities
- `capital-session`: uwierzytelnienie w capital.com, czas życia i odnawianie sesji, bezpiecznik
  demo-only, konta i wybór aktywnego konta, publikowane możliwości modułu.
- `capital-market-data`: wyszukiwanie i wyliczanie instrumentów, odczyt świec oraz historia
  stronicowana głębiej niż jedno żądanie do providera.
- `capital-trading`: pozycje, składanie zleceń MARKET/LIMIT/STOP, dołączane i zmieniane stopy,
  zlecenia oczekujące oraz to, jak asynchroniczna transakcja staje się rozliczonym wynikiem.
- `capital-streaming`: kontrakt wychodzącego WebSocketa — rodzaje wiadomości, świeca w budowie,
  współdzielenie subskrypcji, utrzymanie połączenia i wznawianie po zerwaniu.

### Modified Capabilities

Brak — TradingCenter nie ma jeszcze żadnych specyfikacji.

## Impact

- **Nowe**: `modules/capital-gateway/` (Python 3.12, FastAPI, httpx, websockets, pydantic;
  `uv` + `ruff` + `pytest`). Ta zmiana ustanawia też układ repozytorium: `modules/`, `openspec/`,
  `docs/`.
- **Kontrakt**: HTTP opisane przez OpenAPI pod `/docs`, plus WebSocket `/ws/stream`, którego
  kształty wiadomości są publikowane jako JSON Schema — OpenAPI nie opisuje ładunków WebSocketa.
- **Poświadczenia**: `CAPITAL_API_KEY`, `CAPITAL_IDENTIFIER`, `CAPITAL_PASSWORD` w `.env`, nigdy
  nieopuszczające procesu.
- **Bez wpływu**: TradingHub działa nietknięty. Tamtejszy `broker-gateway` jest przez ten moduł
  zastąpiony, ale jego wygaszenie to osobna decyzja, poza tą zmianą.
- **Świadomie nieobecne**: brak bazy danych, brak schedulera, brak UI, brak dostępu do konta live,
  brak warstwy abstrakcji nad providerem.
