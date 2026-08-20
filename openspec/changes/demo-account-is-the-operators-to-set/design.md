## Context

Gateway wystawia dziś `GET /accounts` i `PUT /accounts/active`
(`capital_gateway/app.py`), oba oparte o `client.py`: `GET /api/v1/accounts` i
`PUT /api/v1/session {accountId}`. Korekty salda nie ma nigdzie — u dostawcy jest to
`POST /api/v1/accounts/topUp` z ciałem `{"amount": …}`, sprawdzone w dokumentacji
20 sierpnia 2026 wraz z granicami: kwota od −400 000 do 400 000, saldo demo nie przekracza
100 000, 10 żądań na sekundę i 100 na konto na dobę.

`trading-mcp` ma dziś siedem narzędzi w trzech plikach (`tools/account.py`,
`instruments.py`, `orders.py`), z których wszystkie dotyczące rachunku są odczytem, i
snapshot bajtowy dokumentu OpenAPI gatewaya, który CI porównuje przy każdej zmianie po
tamtej stronie.

Motywacja: proposal.md. Wymagania: `specs/capital-session` i `specs/trading-mcp-tools`
w tej zmianie.

## Goals / Non-Goals

**Goals:**

- Jedna trasa w gatewayu i trzy narzędzia w `trading-mcp`, bez nowego modułu i bez nowego
  wołającego.
- Skutek uboczny przełączenia konta — zerwany strumień — powiedziany tam, gdzie ktoś go
  przeczyta przed wywołaniem, a nie po.

**Non-Goals:**

- Zakładanie kont. API capital.com tego nie ma; nie da się tego obejść i nie próbujemy.
- Ekran w terminalu. Operator dosypuje przez rozmowę z agentem — tą samą drogą, którą
  składa zlecenia.
- Własna księga doładowań. `GET /history/transactions` u dostawcy już to trzyma, a druga
  kopia rozjeżdża się z pierwszą.
- Limity dobowe po naszej stronie. Patrz D3.

## Decisions

### D1. Trasa: `POST /accounts/top-up`, ciało `{ "amount": <liczba> }`

Bez identyfikatora konta w ciele. Dostawca koryguje konto aktywne sesji i tak, a przyjęcie
`account_id` obiecywałoby wybór, którego nie ma — wywołujący, który chce skorygować inne
konto, przełącza się na nie i to widzi w śladzie.

Odrzucone: `POST /accounts/{id}/top-up`. Ładniejsze, kłamliwe.

### D2. Kwota ujemna przechodzi

Zakres dostawcy jest symetryczny i zabranie środków jest równie potrzebne co dosypanie —
„co robi zespół, gdy zostaje mu tysiąc" jest warunkiem eksperymentu, nie awarią. Gateway
odmawia tylko kwoty zerowej, bo to jedyna, która nic nie znaczy.

### D3. Granice dostawcy nie są kopiowane

Sufit 100 000, zakres ±400 000 i limit stu żądań na dobę zostają tam, gdzie są sprawdzane —
u dostawcy. Kopia w `config.py` byłaby prawdą do pierwszej cichej zmiany po tamtej stronie,
a wtedy moduł zaczyna odmawiać rzeczy, które przechodzą, albo przepuszczać te, które nie.
Odmowa dostawcy jest tłumaczona na odmowę z powodem (`ToolRefusal` po stronie MCP,
4xx po stronie gatewaya), nie na awarię — to jest ta sama reguła, którą zestaw narzędzi już
stosuje do odmów rynku.

Jedyna liczba, którą trzymamy, to zero z D2, i nie jest granicą dostawcy.

### D4. Trzy narzędzia, dwa oznaczone jako zapisujące

`list_accounts` czyta. `switch_active_account` i `top_up_demo_account` zmieniają stan — i
to jest rozszerzenie znaczenia „zmienia stan" w tym module, dotąd obejmującego wyłącznie
ruch na rynku. Przełączenie zmienia to, czego dotyczy **każde następne** zlecenie, a
korekta salda zmienia, ile agent ma pieniędzy; oba są dokładnie tym, przed czym adnotacja
ma ostrzegać.

### D5. O zerwanym strumieniu mówi opis narzędzia, nie kod

Nie ma czego wyłączać ani z czym się synchronizować: strumień jest w gatewayu, jego
konsumentem jest market-data, a `Upstream` odtwarza połączenie sam, z narastającym
odstępem — zerwanie po przełączeniu konta jest dla niego takim samym zerwaniem jak każde
inne i tą samą drogą wraca. Czego brakuje, to żeby wołający **wiedział**, że je wywołał:
narzędzie odpowiada sukcesem, a skutek jest po drugiej stronie systemu.

Odrzucone: odmowa przełączenia, gdy strumień jest zestawiony. Zabiera możliwość, której
istnieniem jest cała ta zmiana, żeby uniknąć przerwy, którą moduł i tak umie przeżyć.

Odrzucone: powiadamianie market-daty przez gateway. Moduł nie woła modułu; a przerwa jest
i tak widoczna po jej własnej stronie, jako `reconnecting`.

### D6. Snapshot kontraktu i sufit powierzchni to część tej zmiany

Zmiana w gatewayu unieważnia bajtowy snapshot w `trading-mcp`; trzy narzędzia podnoszą
zserializowaną powierzchnię ponad zapisany sufit. Oba testy MUST się wywrócić, zanim
zostaną poprawione — to jest ich cała wartość — i oba są poprawiane w tej zmianie, każdy z
własnym powodem w commicie.

## Risks / Trade-offs

- **Model dosypuje sobie, kiedy zabraknie środków, i eksperyment przestaje mierzyć to, co
  miał** → tego nie da się zamknąć kodem: narzędzie zostało dane świadomie (odpowiedź
  operatora z 20 sierpnia). Broni się ślad: korekta idzie przez `tool_calls`, jak każde
  wywołanie, więc przebieg, w którym agent sam sobie dosypał, da się od takiego rozpoznać.
- **Limit stu żądań na dobę jest wspólny dla operatora i agenta** → wyczerpanie objawia
  się odmową z powodem, nie awarią (D3), więc operator dowie się, co je wyczerpało.
- **Przełączenie konta w środku zbierania świec** → przerwa rzędu sekund do minuty, z
  odtworzeniem po stronie market-daty i luką widoczną w pokryciu. Opis narzędzia to mówi
  (D5), a `candle-age-stale` jest alertem, który by to zauważył, gdyby przerwa się
  przeciągnęła.
- **`top_up` w środowisku innym niż demo** → niemożliwe z konstrukcji: moduł nie startuje
  z hostem innym niż demo (`capital-session`, "Wyłącznie środowisko demo"), a narzędzie
  woła gateway, nie dostawcę.

## Migration Plan

Brak migracji i brak stanu do przeniesienia. Kolejność wdrożenia bez znaczenia dla
poprawności: `trading-mcp` z narzędziem, którego gateway jeszcze nie ma, dostaje 404 i
zamienia je na odmowę nazywającą powód — czyli dokładnie to, co robi dziś z każdą trasą,
której nie ma.
