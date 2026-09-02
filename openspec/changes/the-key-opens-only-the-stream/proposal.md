## Why

Od `the-gateway-door-authenticates` przed bramką stoi uwierzytelniający platformy z listą trzech
aplikacji, a mimo to o tym, **jak daleko** wołający sięga, rozstrzyga nadal klucz współdzielony:
`RequireGatewayKey` sprawdza go jako pierwszy i klucz otwiera wszystko, łącznie ze składaniem
zleceń. Tożsamość aplikacji czyta się dopiero wtedy, gdy klucza nie ma — i tylko po to, żeby
przeglądarkę wpuścić na rachunek. Klucz, który wyciekł z dowolnego `.env`, razem z tokenem
którejkolwiek z trzech aplikacji otwiera dziś trasę `/orders`.

Zmierzone 1 września 2026 w przeglądzie: jeden klucz statyczny dla trzech wołających, i
mechanizm, który `architecture.md` nazwał lepszym — lista aplikacji, jak w każdym innym module —
odłożony „na własną propozycję". To jest ta propozycja.

Zmiana OpenSpec z dwóch powodów mechanicznych: zmienia wymaganie w `capital-access-control`
i dotyka `infra/app-service.tf`.

## What Changes

- **Na produkcji o dostępie do tras HTTP rozstrzyga aplikacja z oświadczeń zwalidowanego tokenu,
  a klucz nie otwiera żadnej.** Moduł wołający z listy `MODULE_CALLER_APPLICATION_IDS`
  (`market-data`, `trading-mcp`) sięga wszystkiego; wołający z listy przeglądarek — rachunku,
  jak dotąd; żądanie bez nazwanej aplikacji jest odmową, choćby niosło właściwy klucz.
- **Klucz zostaje poświadczeniem dokładnie dwóch miejsc**: `/ws/stream`, którego
  uwierzytelniający platformy nie umie przepuścić (20 sierpnia 2026), i pracy lokalnej, gdzie
  nie ma platformy, która nazwałaby kogokolwiek. Nic w tych dwóch miejscach się nie zmienia.
- **Wołający nie zmieniają się wcale.** `market-data` i `trading-mcp` wysyłają dziś token obok
  klucza; od tej zmiany na produkcji liczy się token, lokalnie klucz. Żadna linia po ich stronie.
- **Infrastruktura**: jedno ustawienie w bloku bramki z dwoma id, które jej `allowed_applications`
  już nazywa.
- **Bramka nie bierze pakietu.** Przegląd zapisał „z P2 to jest import, nie nowy plik" i mylił
  się: `tc-runtime` niesie asyncpg, alembic, SQLAlchemy i azure-identity, a bramka potrzebuje
  trzydziestu linii czytających jedno oświadczenie. Powód w `design.md`.

## Capabilities

### Modified Capabilities

- `capital-access-control`: „Każde wywołanie niesie poświadczenie" mówi, która postać
  poświadczenia otwiera które miejsce — aplikacja na trasach HTTP produkcji, klucz na
  strumieniu i lokalnie — i że na produkcji klucz sam nie otwiera żadnej trasy HTTP.

## Impact

- **Kod**: `capital_gateway/config.py` (druga lista aplikacji), `capital_gateway/app.py`
  (drzwi: `RequireGatewayKey` staje się `GatewayDoor`, bo klucz przestał być tym, czego wymaga),
  `caller_access.py` (docstring), `tests/test_access_control.py`.
- **Infrastruktura**: `infra/app-service.tf`, blok `capital_gateway` —
  `MODULE_CALLER_APPLICATION_IDS`. Operator: `apply`. Kolejność jest tu bezpieczna w obie strony:
  obraz przed `apply` odmawia modułom na produkcji (lista pusta = nikt), więc **`apply` MUST
  wyprzedzić deploy** — a od P5 deploy czeka na `checks`, więc jest na to kilka minut; bezpieczniej
  zrobić `apply` przed merge, bo ustawienie bez obrazu, który je czyta, nic nie zmienia.
- **Pozostałe moduły**: bez zmian. `trading-mcp` ma snapshot OpenAPI bramki, a middleware nie
  jest w schemacie; CI i tak uruchomi jego job.
- **Dokumenty**: README bramki, `.env.example`, akapit o drzwiach w `CLAUDE.md`.

`design.md` powstaje dla dwóch decyzji z realną alternatywą: pakiet czy własna kopia, i skąd
moduł wie, że stoi za platformą. `tasks.md` powstaje.
