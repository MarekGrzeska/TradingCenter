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
