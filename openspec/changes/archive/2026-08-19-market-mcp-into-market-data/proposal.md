## Why

`market-mcp` jest procesem, którego jedyną treścią ponad narzędzia jest to, że stoi osobno:
klient HTTP do rodzica (142 linie), kopia jego schematu (2 921 linii JSON-a) i skrypt
pilnujący, żeby kopia nie zwietrzała (114 + 111 linii testu). Zmierzone na `main @ bfbf039`:
pakiet ma 2 078 linii, z czego **416 to rusztowanie granicy między procesami**, a ~1 650 to
wartość — redukcja świec, sufity odpowiedzi i zdania o niepewności. Za to rusztowanie płaci
się App Service'em, Dockerfile'em, lockiem, workflow deploy, tripletem Entra, jobem CI
i drugim hopem sieciowym na każde wywołanie narzędzia.

Wartość przeżywa w całości jako warstwa w aplikacji właściciela danych. Rusztowanie znika
nie dlatego, że jest źle napisane, tylko dlatego, że **schemat w tym samym procesie nie ma
jak być nieświeży**.

To pierwsza z dwóch połówek kierunku A (`docs/rachunek-po-refactorze.html`). `teams-mcp`
idzie osobną zmianą, po tej — market-mcp jest tańszym dowodem wzorca, bo ma jednego
konsumenta mniej i nie zmienia niczego w danych.

## What Changes

- Zestaw narzędzi MCP przenosi się do `market-data` i jest montowany jako trasa **`/mcp`**
  w jego aplikacji. Nazwy narzędzi, ich opisy, sufity i kształt odmowy — bez zmian.
- Klient HTTP do archiwum znika. Narzędzia sięgają po te same dane **wywołaniem funkcji**,
  przez tę samą warstwę, z której korzystają routery REST. Wywołanie narzędzia: 2 hopy → 1.
- Snapshot kontraktu, skrypt `contract.py` i `test_contract.py` znikają razem z powodem,
  dla którego istniały.
- **BREAKING — transport stdio znika.** Zostaje jedna droga do narzędzi. Klient MCP na
  pulpicie operatora traci drogę przez strumienie procesu; test parzystości transportów
  odchodzi razem z nią. Decyzja świadoma, podjęta przy tej propozycji: rachunek trzymał ją
  jako „zdecydowaną a niewykonaną", a wmontowanie w market-data nie pozwala jej dłużej
  odkładać.
- **NOWE — autoryzacja per wołający.** `market-data` zaczyna rozróżniać, kto sięga po co:
  `terminal` po REST, `agent` i `teams` **wyłącznie** po `/mcp`. Dziś takiego rozróżnienia
  nie ma w ogóle.
- **BREAKING — `MARKET_MCP_URL` i `MARKET_MCP_SCOPE`** u `agent` i `teams` wskazują odtąd
  na `market-data`. Reguła „oba albo żaden" zostaje; brak obu nadal znaczy moduł bez
  narzędzi, co jest konfiguracją wspieraną, nie awarią.
- Moduł `modules/market-mcp/` przestaje istnieć — wraz z App Service, workflow deploy,
  Dockerfile'em, lockiem, tripletem Entra i portem 8040 w runnerze dev.

**Korekta rachunku, którą trzeba zapisać.** Rachunek nazwał cenę A tak: *„Mechanizm już
istnieje: `RequireCallerIdentity` z tc-mcp-kit"*. Zmierzone: `RequireCallerIdentity`
sprawdza wyłącznie, **czy** tożsamość jest obecna, nigdy **czyja**
(`packages/tc-mcp-kit/tc_mcp_kit/network_identity.py`, 68 linii). Wpuszczenie `agent`
i `teams` do `allowed_applications` archiwum otwiera im całe REST — z `POST /pairs`
i `DELETE /pairs/{symbol}` włącznie — a ten mechanizm tego nie zamknie, bo oba moduły
tożsamość niosą i przejdą. **Autoryzacja per wołający jest nowym kodem, nie przeprowadzką.**
To piąta liczba tego planu, która nie przeżyła pomiaru.

## Capabilities

### New Capabilities

- `market-data-tools`: zestaw narzędzi, który archiwum publikuje dla modelu — wyłącznie
  czytający, z zapisanym sufitem powierzchni i opisem jako częścią kontraktu.
- `market-data-answers`: kształt odpowiedzi dla modelu — sufity treści, niepewność jadąca
  w odpowiedzi, trzy rodzaje „nie wiem", jeden kształt odmowy.
- `market-data-caller-access`: kto sięga po którą powierzchnię modułu. Trasa narzędziowa
  wobec REST, wymóg tożsamości wołającego, sonda zdrowia poza wymogiem.

### Modified Capabilities

- `market-mcp-tools`: usunięte w całości — wymagania przenoszą się do `market-data-tools`
  bez zmiany treści.
- `market-mcp-answers`: usunięte w całości — wymagania przenoszą się do
  `market-data-answers` bez zmiany treści.
- `market-mcp-transport`: usunięte w całości. Wymaganie „Dwa transporty, jeden zestaw
  narzędzi" znika wraz z transportem stdio; pozostałe dwa przenoszą się do
  `market-data-caller-access`.
- `market-mcp-upstream-access`: usunięte w całości. Trzy z czterech wymagań tracą przedmiot,
  gdy nie ma połączenia do opisania; czwarte — „Moduł MUST NOT importować kodu archiwum" —
  ta zmiana **odwraca wprost**, i to jest jej sedno, nie skutek uboczny.

## Impact

**Kod.** `modules/market-mcp/` znika; ~1 650 linii wartości i ich testy lądują
w `modules/market-data/`. `market_data/app.py` dostaje montaż `/mcp` — z pułapką kolejności
importów: `telemetry.configure()` stoi w linii 36 **przed** `from fastapi import FastAPI`,
bo autoinstrumentacja OTel łata atrybut klasy, więc nic importującego FastAPI ani Starlette
nie może wejść wyżej. `market-data` bierze `tc-mcp-kit` i `mcp==1.27.0` (przypięte dokładnie
— 2.0.0 przeniosło `FastMCP`).

**Konsumenci.** `agent` i `teams` — dwa ustawienia i nic więcej; `MCP_PATH = "/mcp"` mają
zaszyte i pasuje bez zmian. `terminal` nie zmienia się wcale.

**Infrastruktura.** Ubywa: `azurerm_linux_web_app.market_mcp`, `module.market_mcp_easy_auth`,
`data.azuread_service_principal.market_mcp_managed_identity`, `output market_mcp_hostname`.
Przybywa: `agent` i `teams` w `allowed_applications` archiwum. `terraform apply` jest
operatora, nie CI — a ta zmiana rusza `azuread_*`, więc jest jego z konstrukcji.

**CI i narzędzia.** `deploy-market-mcp.yml` znika; joby w `checks.yml` 13 → 12, wraz
z filtrem, który odpalał market-mcp na zmianę w `market_data/contract.py` — bo nie ma już
drugiej kopii do rozjechania. `scripts/dev.py` traci wpis i port 8040.

**Dokumentacja.** `CLAUDE.md` (mapa modułów, tabela komend, porty, uzasadnienie istnienia
`tc-mcp-kit` — dziś opiera się na tym, że biorą go wyłącznie moduły **bez** bazy danych,
a `market-data` bazę ma), `docs/architecture.md`, `README.md`.

**Czego ta zmiana nie rusza.** Kontraktu REST archiwum, terminala, granicy do capital.com,
`trading-mcp` ani `teams-mcp`. Reguła „no module imports another module" zostaje nietknięta
w literze: nie powstaje żaden nowy import między modułami — jeden moduł przestaje istnieć.
