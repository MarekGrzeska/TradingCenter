## Context

Bramka jest jedynym modułem bez bazy i bez pakietu: jej obraz buduje się z własnego katalogu, a
`deploy-gateway.yml` ma najkrótszą listę ścieżek. Ma też jedyną trasę w systemie bronioną samym
kluczem — `/ws/stream` — i to zostaje.

## Decisions

### Własna kopia `calling_application`, nie import z pakietu

Przegląd z 1 września zapisał, że po P2 „to jest import, nie nowy plik". Alternatywa była
rozważona i odrzucona liczbą: `tc-runtime` zależy od asyncpg, alembic, SQLAlchemy i
azure-identity — cztery biblioteki dla modułu, który nie ma bazy ani tożsamości do
przedstawienia — a `tc-mcp-kit` od `mcp`. Bramka potrzebuje trzydziestu linii, które czytają
jedno oświadczenie z jednego nagłówka; `measure-duplication.py --threshold 70` nie wskazuje
tej pary, bo plik bramki to 60 linii, a pakietowy 200. Trzeci warunek współdzielenia z
`architecture.md` — pakiet nie może kosztować konsumenta więcej niż kopia — tu przegrywa
wprost. Kopia zostaje, z tym akapitem jako powodem.

### Produkcja to `GATEWAY_ENV=production`, nie nowa flaga

Pozostałe moduły mają `REQUIRE_AUTHENTICATED_PRINCIPAL`. Bramka ma już jeden znacznik
„jestem wdrożona" — `is_production()` — od którego zależy, czy publikuje `/docs`. Druga flaga
mówiąca to samo innymi słowami byłaby drugim miejscem, w którym można je ustawić różnie.
Kierunek błędu jest właściwy: gdyby uwierzytelniający platformy został wyłączony, produkcja
bez nazwanej aplikacji odmawia każdemu, także modułom — awaria, nie otwarte drzwi.

## Risks / Trade-offs

- Obraz z tą zmianą przed `apply` odmawia `market-data` i `trading-mcp` na produkcji: lista
  modułów jest pusta, a klucz nic nie otwiera. Kolejność: `apply` przed merge.
- Lokalnie nic się nie zmienia, więc lokalny test niczego tu nie dowodzi; dowodem jest test z
  `GATEWAY_ENV=production` i pomiar po `apply` (tasks 4.x).
