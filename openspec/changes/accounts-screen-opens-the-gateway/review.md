# Review — accounts-screen-opens-the-gateway

## Cena, którą ta zmiana płaci, i to, co zostało z obrony

Warto ją powtórzyć poza `design.md`, bo jest to jedyna zmiana w tym repozytorium, która
**odejmuje** warstwę obrony. Gateway miał dwie: sprawdzenie klucza w kodzie i listę dwóch
adresów w konfiguracji platformy. Zostaje pierwsza. Klucz, który wycieknie, był dotąd
bezużyteczny spoza planu; teraz wystarcza sam.

Co ogranicza szkodę i dlatego to przeszło: moduł odmawia startu z hostem innym niż demo
capital.com i nie da się tego przestawić ustawieniem (`capital-session`, „Wyłącznie
środowisko demo"). Za tymi drzwiami nie ma prawdziwych pieniędzy — jest konto testowe,
które ta sama zmiana pozwala doładować z ekranu.

Co z tego wynika operacyjnie: rotacja `GATEWAY_API_KEY` przestaje być formalnością.
`docs/rotacja-poswiadczen.html` opisuje jak.

## Dwa poświadczenia, jedno miejsce sprawdzania

Podejrzenie, które warto zapisać: łatwo tu było zrobić wyjątek dla trasy zamiast dla
wołającego („`/accounts` bez klucza"). Byłoby krócej i byłoby dziurą — każdy z internetu
czytałby wtedy stan rachunku. To, co stoi, sprawdza **kto**, a dopiero potem **dokąd**, i
oba sprawdzenia są w module, nie w konfiguracji platformy.

Rejestr tras jest listą dozwolonych, nie zakazanych. Test `test_a_path_outside_the_record_
is_refused_by_default` jest tam po to, żeby trasa dopisana za miesiąc była domyślnie poza
zasięgiem przeglądarki — i to jest w tej warstwie wart więcej niż którykolwiek pojedynczy
wpis.

## Co apply pokazał: dwie rzeczy, obie moje

**Easy Auth zabija upgrade WebSocketa, a `AllowAnonymous` tego nie zmienia.** Zmierzone
20 sierpnia, kilka minut po pierwszym apply: strumienie market-daty padły z „timed out
during opening handshake" i **nie wróciły** — ostatnie połączenie `/ws/stream` skończyło
się o 13:43, dokładnie przy restarcie, i przez godzinę nie było ani jednego nowego. Gateway
przez cały ten czas odpowiadał na HTTP, więc z zewnątrz nic nie wyglądało na zepsute, a
archiwum przestało dostawać świece i poszło nadrabiać REST-em, aż capital.com zaczął
odpowiadać `error.too-many.requests`.

`AllowAnonymous` rozstrzyga, czy żądanie **zostanie odrzucone**, a nie czy upgrade
przeżyje przechwycenie. Naprawa to `excluded_paths = ["/ws/stream", "/"]` — dokładnie ten
sam wyjątek, który market-data ma u siebie dla `/ws/candles`, i którego nie przepisałem
razem z resztą wzorca. Nic nie tracimy: klucz jest sprawdzany w samym handlerze
WebSocketa, i zawsze tam był. Potwierdzone po naprawie ręcznym połączeniem z produkcyjnym
gatewayem: handshake OK, `status: connected`, świeca US100 MINUTE_5 w drugiej ramce.

**Terminal wdrożony bez adresu gatewaya.** `deploy-terminal.yml` ma ten sam wpis dla
archiwum i dla workbencha, a dla gatewaya go nie dostał — więc przeglądarka pytała Static
Web App o `/gateway-api/accounts`, dostawała stronę aplikacji i ekran mówił
`Unexpected token '<'`. Pułapka jest w tym pliku opisana dwa razy, dla agenta i dla teams;
wszedłem w nią trzeci raz. Dopisana z komentarzem, żeby czwartego nie było.

Co z tego wynika ogólniej: obie pomyłki są tego samego rodzaju — **wzorzec przepisany bez
jednej linii**. Za pierwszym razem brakowało wyjątku dla strumienia, za drugim wpisu w
buildzie. Kopiowanie kształtu z market-daty było dobrym pomysłem; kopiowanie go z pamięci
zamiast obok otwartego pliku nie.

## Czego nie dało się sprawdzić bez apply

Wszystkiego, co dzieje się **przed** aplikacją: czy Easy Auth z `AllowAnonymous` naprawdę
przepuszcza żądanie bez tokenu (tak mówi dokumentacja i tak zachowuje się market-data w
odwrotnej konfiguracji), i czy nagłówek `X-MS-CLIENT-PRINCIPAL` przychodzi w kształcie,
który `calling_application` czyta. Kształt jest przepisany z market-daty, gdzie został
zmierzony na produkcji 19 sierpnia — ale tam czyta go inny moduł zza innej rejestracji.

Pierwszy apply to rozstrzygnie i jest jedyną drogą. Jeżeli okaże się, że kształt jest inny,
objaw będzie jednoznaczny: ekran Accounts dostanie `401` i powie to wprost, a market-data i
trading-mcp nie zauważą niczego, bo idą kluczem.

## Terminal: token, którego jeszcze nie prosi po imieniu

Ekran wysyła token, który terminal ma dziś — wystawiony dla market-daty. Gateway przyjmuje
go jako trzecią dozwoloną audiencję, tym samym ruchem, którym robi to workbench od czasu,
gdy powstał. Zakres własny gatewaya jest zarejestrowany i pre-autoryzowany, więc zmiana
terminala na proszenie o token po imieniu jest zmianą jednego pliku i nie wywoła drugiego
pytania o zgodę.

## Drobiazg, który zauważy pierwszy uruchamiający lokalnie

`GATEWAY_PROXY_KEY` w `.env` terminala musi być tą samą wartością co `GATEWAY_API_KEY` w
`.env` gatewaya. Niedopasowanie objawia się jako „the accounts could not be read — missing
or invalid caller key" — czytelnie, ale dopiero po wejściu na zakładkę. `dev.py` porównuje
już taką parę dla trading-mcp i mógłby porównywać i tę; nie dopisałem tego, bo to osobny
moduł i osobne testy, a nie część tej zmiany.

## Weryfikacja

- `capital-gateway`: `uv run pytest` — 222 passed, 11 skipped; ruff i pyright czysto
- `terminal`: `pnpm test` — 666 passed; lint, typecheck i `contract:check` czysto
- `trading-mcp`: `scripts/contract.py check` — snapshot gatewaya zgodny
- `terraform fmt -check -recursive` i `terraform validate` — czysto
- `openspec validate accounts-screen-opens-the-gateway --strict` — valid

## Trzecia połowa tego samego wzorca (20 sierpnia, po wdrożeniu)

Ekran kont na produkcji odpowiedział „the accounts could not be read — capital-gateway is
not reachable", a log gatewaya milczał. To nie był ten sam błąd co poprzednio: paczka
terminala zbudowana z `fdd5591` ma już adres gatewaya wkompilowany (sprawdzone w
`assets/index-*.js` serwowanym z produkcji — są tam wszystkie trzy hosty). Pytanie szło pod
właściwy adres i nie doszło.

Zabrakło CORS-u na App Service gatewaya. `GET /accounts` z tokenem jest zapytaniem
międzydomenowym z nagłówkiem `Authorization`, więc przeglądarka wysyła najpierw `OPTIONS` —
a `OPTIONS` nie niesie żadnego tokenu. Easy Auth odpowiedziało `401`, przeglądarka nie
wysłała właściwego zapytania, a odmowa na poziomie sieci dociera do `fetch` jako wyjątek,
nie jako status. Stąd komunikat o module nieosiągalnym zamiast o odrzuconym.

Zmierzone z zewnątrz, tym samym `Origin` co terminal:

| Aplikacja | Odpowiedź na preflight |
|---|---|
| `app-tradingcenter-market-data` | `200`, z `Access-Control-Allow-Origin` |
| `app-tradingcenter-gateway` | `401`, bez żadnego nagłówka CORS |

Poprawka to ten sam blok `cors`, który market-data i workbench noszą od początku —
`allowed_origins = [local.terminal_origin]`, `support_credentials = false`. Żadna trasa się
przez to nie otwiera: co przeglądarka może osiągnąć za drzwiami, mówi lista w
`caller_access.py`, i ta się nie zmienia.

Wzorzec do zapamiętania, bo to jego trzecie wystąpienie w dwa dni: **wystawienie modułu
przeglądarce to trzy rzeczy, nie jedna** — audiencja i aplikacja w Easy Auth, adres
wkompilowany w paczkę terminala, oraz CORS. Za każdym razem skopiowano dwie z trzech, za
każdym razem objaw wyglądał na awarię czegoś innego.

Zmiana jest w `infra/`, więc `terraform apply` należy do operatora. Do sprawdzenia po
zastosowaniu: preflight na `/accounts` z origin terminala ma odpowiedzieć `200` z
`Access-Control-Allow-Origin`, a zakładka Konta pokazać saldo zamiast ostatniej odpowiedzi.
