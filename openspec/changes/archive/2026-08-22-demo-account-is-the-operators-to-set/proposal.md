## Why

Konto demo jest warunkiem każdego eksperymentu, który ten system prowadzi, i jedyną rzeczą
w nim, której nie da się ustawić z terminala ani z rozmowy. Saldo skończone po serii
stratnych przebiegów zespołu zatrzymuje pracę do czasu, aż ktoś otworzy stronę
capital.com; drugie konto demo, założone po to, żeby dwa eksperymenty nie mieszały sobie
wyników, jest widoczne w API i nieprzełączalne inaczej niż ręcznie.

capital.com potrafi trzy z czterech rzeczy, o które tu chodzi (sprawdzone w dokumentacji
20 sierpnia 2026): wylistować konta, przełączyć aktywne (`PUT /session`) i **skorygować
saldo konta demo** (`POST /accounts/topUp`). Czwartej — założenia nowego konta — API nie ma
wcale i ta zmiana jej nie wymyśla. Dwie pierwsze gateway już wystawia i nikt ich nie woła
poza terminalem; trzeciej nie ma nigdzie.

## What Changes

- `capital-gateway` dostaje trasę korygującą saldo konta demo. Kwota ujemna jest
  przyjmowana tak samo jak dodatnia: ustawienie chudego rachunku jest częścią ustawiania
  warunku eksperymentu, nie pomyłką.
- Odmowa dostawcy — sufit salda, zakres kwoty, limit dobowy — MUST docierać jako odmowa
  nazywająca powód, nie jako awaria dostępu. Moduł MUST NOT powtarzać tych limitów we
  własnym kodzie: dostawca je zna i zmienia bez pytania nas.
- `trading-mcp` dostaje trzy narzędzia: wylistowanie kont, przełączenie aktywnego i
  korektę salda konta demo. Dwa ostatnie zmieniają stan i MUST być tak oznaczone —
  dotychczas wszystkie narzędzia rachunku w tym module były odczytem.
- **Przełączenie konta zrywa strumień notowań** (dokumentacja capital.com: „WebSocket
  streaming falls off when the financial account is changed"). Opis narzędzia MUST to
  mówić, a nie zostawiać modelowi do odkrycia — konsekwencją jest przerwa w zbieraniu
  świec, której nie widać z poziomu rozmowy.
- Sufit powierzchni narzędzi `trading-mcp` MUST zostać zmierzony ponownie i podniesiony
  świadomie albo zestaw MUST zostać ścieśniony. Trzy narzędzia to koszt płacony w każdej
  turze rozmowy.

## Capabilities

### New Capabilities

Brak — trzy istniejące zbiory wymagań mówią już o koncie, o handlu i o zestawie narzędzi.

### Modified Capabilities

- `capital-session`: korekta salda konta demo jako możliwość modułu, obok wyliczania kont i
  przełączania aktywnego; przełączenie mówi, że zrywa strumień.
- `trading-mcp-tools`: trzy narzędzia konta w zestawie, w tym dwa zmieniające stan; sufit
  powierzchni przeliczony.

## Impact

- `modules/capital-gateway`: `client.py` (wywołanie `POST /api/v1/accounts/topUp`),
  `adapter.py`, `dtos.py` i `app.py` (trasa i jej model) — **kontrakt między modułami**,
  więc `trading-mcp` odświeża swój bajtowy snapshot dokumentu OpenAPI, a CI uruchamia jego
  job przy każdej zmianie w gatewayu.
- `modules/trading-mcp`: `tools/account.py` (trzy narzędzia), `client.py` jeśli brakuje
  metody piszącej, `tests/test_tool_surface.py` (nowy sufit).
- `modules/terminal`: bez zmian. Operator dosypuje przez rozmowę z agentem — ta sama droga,
  którą składa zlecenia — a nie przez osobny ekran, którego nikt nie prosił.
- Bez migracji, bez zmian w infrastrukturze. `trading-mcp` nie zyskuje nowego wołającego:
  workbench już jest jedynym.
- `review.md` po wykonaniu.
