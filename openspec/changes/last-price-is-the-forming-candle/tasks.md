## 1. market-data — odczyt świecy w toku

- [x] 1.1 `Hub` oddaje świecę w toku dla pary bez tworzenia pokoju przy odczycie i bez brania jego zamka
- [x] 1.2 `Hub` oddaje śledzone rozdzielczości, które świecę w toku mają, od najdrobniejszej
- [x] 1.3 Zależność routera czytająca hub z `Request` — `deps.hub` bierze `WebSocket` i nie da się jej użyć na trasie HTTP
- [x] 1.4 Kształt odpowiedzi w `contract.py`: świeca, znacznik okresu w toku, rozdzielczość, z której pochodzi, oraz stan rynku
- [x] 1.5 Trasa w `routers/candles.py`; bez `resolution` wybiera archiwum, z `resolution` honoruje
- [x] 1.6 Powód braku świecy: para nieśledzona, rynek zamknięty, rynek otwarty i cisza — trzy różne odpowiedzi
- [x] 1.7 Testy: odczyt w trakcie sesji, wybór rozdzielczości bez wskazania, rozdzielczość wskazana, rynek zamknięty, feed stoi, para nieśledzona
- [x] 1.8 Test: odczyt niczego nie utrwala — po nim archiwum świec zamkniętych jest niezmienione

## 2. Kontrakty po stronie konsumentów

- [x] 2.1 `pnpm contract:generate` w terminalu; `src/data/contract.generated.ts` nie jest edytowany ręcznie
- [x] 2.2 `pnpm contract:check` i `pnpm typecheck` w terminalu — nic w `archive.ts` ani `types.ts` się nie zmienia
- [x] 2.3 Snapshot schematu w market-mcp odświeżony; `uv run python scripts/contract.py check` przechodzi

## 3. market-mcp — cena bieżąca

- [x] 3.1 Kształt wejściowy w `upstream.py` dla nowej trasy archiwum
- [x] 3.2 `get_last_price` pyta o świecę w toku, a o ostatnią zamkniętą dopiero gdy jej nie ma
- [x] 3.3 `resolution` opcjonalne: pominięte oznacza wybór archiwum, wskazane jest honorowane
- [x] 3.4 Odpowiedź niesie znacznik okresu w toku, rozdzielczość, z której pochodzi, i wiek
- [x] 3.5 Notatki rozróżniają rynek zamknięty od zbierania, które stoi; żadne z nich nie jest ciszą rynku
- [x] 3.6 Opis narzędzia mówi, że zakres okresu w toku jeszcze się poszerzy
- [x] 3.7 Testy: cena w trakcie sesji, po zamknięciu rynku, przy stojącym feedzie, para nieśledzona, rozdzielczość wskazana przez model

## 4. Domknięcie

- [x] 4.1 `uv run pytest`, `ruff check .`, `pyright` w `modules/market-data` — z `-m db`
- [x] 4.2 `uv run pytest`, `ruff check .`, `pyright`, `scripts/contract.py check` w `modules/market-mcp`
- [x] 4.3 `pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm contract:check` w `modules/terminal`
- [ ] 4.4 Przejście ręczne na żywym stosie: pytanie o cenę przy otwartym rynku i przy zamkniętym
- [x] 4.5 `openspec validate last-price-is-the-forming-candle --strict`
- [x] 4.6 `review.md`
- [ ] 4.7 Pull request
