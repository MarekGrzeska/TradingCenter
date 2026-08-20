## Why

Drzwi `capital-gateway` nie sprawdzają nikogo. Easy Auth stoi przed tą aplikacją z
`unauthenticated_action = "AllowAnonymous"` i `require_authentication = false` — bo
`market-data` i `trading-mcp` wołają ją kluczem współdzielonym i **bez tokenu** — a przy tym
ustawieniu moduł uwierzytelniający nie waliduje niczego i nie wstawia nagłówka
`x-ms-client-principal`. Zmierzone 20 sierpnia 2026: żądanie z `Authorization: Bearer notatoken`
dotarło do własnego middleware modułu i tam zostało odrzucone, podczas gdy to samo żądanie do
`market-data` odrzuciła platforma, nagłówkiem `WWW-Authenticate`, nie dopuszczając go do
aplikacji.

Skutkiem jest wymaganie, które nie ma jak być spełnione. `capital-access-control` mówi, że moduł
uznaje uwierzytelnionego wołającego rozpoznanego z oświadczeń tokenu — a oświadczenia przychodzą
w nagłówku, którego nikt nie wypełnia. Zakładka Konta w terminalu nie odczytała na produkcji
nigdy ani jednego konta: każde żądanie kończy się `401`, co terminal pokazuje jako wygaśniętą
sesję operatora.

Przy okazji zmierzono drugą rzecz, która zmienia ocenę ryzyka: **żadna aplikacja w tej grupie
zasobów nie ma ograniczenia adresowego**. Gateway odpowiada każdemu, kto zna nazwę hosta, a
klucz współdzielony jest całością jego obrony.

## What Changes

- `market-data` i `trading-mcp` przestają być rozpoznawane po kluczu współdzielonym i wołają
  gateway **tokenem własnej tożsamości zarządzanej**, o audiencji `api://tradingcenter-capital-gateway`.
- Easy Auth gatewaya przechodzi na `require_authentication = true` i `Return401`, z wyliczoną
  listą aplikacji: `market-data`, `trading-mcp`, terminal. Od tego momentu token jest
  walidowany przez platformę, zanim aplikacja go zobaczy.
- `caller_access.py` zostaje tym, czym jest — rejestrem, która trasa należy do którego
  wołającego. Przejście przez drzwi nadal MUST NOT oznaczać dostępu do wszystkiego.
- **BREAKING dla wdrożenia, nie dla kontraktu**: przestawienie platformy przed wypuszczeniem
  obu modułów z tokenami odcina je w chwili `apply`. Kolejność jest częścią zmiany, nie
  szczegółem wykonania.
- Klucz współdzielony zostaje jedyną postacią poświadczenia w pracy lokalnej, gdzie nie ma
  Entry, i przestaje cokolwiek otwierać na produkcji.
- `/ws/stream` i `/` pozostają wyłączone z Easy Auth — strumień ginie, gdy moduł
  uwierzytelniający przechwytuje upgrade, a sonda musi odpowiadać bez poświadczenia. Klucz
  sprawdzany wewnątrz uchwytu WebSocketa zostaje.

## Capabilities

### New Capabilities

Brak. Zmiana naprawia mechanizm, który wymagania już opisują.

### Modified Capabilities

- `capital-access-control`: token wołającego MUST być zwalidowany, zanim moduł uwierzytelni
  kogokolwiek jego oświadczeniami; nagłówek z oświadczeniami, którego nikt nie zweryfikował,
  MUST NOT być tożsamością. Wdrożenie MUST postawić przed modułem uwierzytelniającego, który
  odrzuca token nieważny, zamiast przepuszczać go dalej.
- `market-data-upstream-access`: poświadczeniem do gatewaya na produkcji jest token tożsamości
  modułu, nie klucz współdzielony.
- `trading-mcp-upstream-access`: to samo, wraz z odmową startu, gdy poświadczenia nie da się
  uzyskać.

## Impact

- `infra/app-service.tf` — `auth_settings_v2` gatewaya, lista `allowed_applications`, i
  przypisania ról aplikacji dla obu tożsamości zarządzanych. Zmiana dotyka `azuread_*`, więc
  `terraform-apply.yml` odmówi: `apply` jest lokalny, operatora.
- `modules/market-data` — warstwa wołająca gateway (`gateway.py`) zdobywa token i wysyła go
  obok klucza; `market-data-upstream-access` opisuje, co się dzieje, gdy tokenu nie da się
  uzyskać.
- `modules/trading-mcp` — to samo w jego kliencie gatewaya, wraz ze sprawdzeniem demo, które
  wykonuje przed otwarciem portu.
- `modules/capital-gateway` — `caller_access.py` i `RequireGatewayKey` zostają, ale przestają
  być jedyną warstwą; komentarze opisujące dzisiejszy stan wymagają korekty razem z kodem.
- `modules/terminal` — bez zmian w kodzie. Zakładka Konta zaczyna działać, bo zaczyna działać
  mechanizm, na którym ją oparto.
- `scripts/dev.py` — praca lokalna zostaje na kluczu; sprawdzenie zgodności obu `.env` nadal ma
  sens i nie znika.
