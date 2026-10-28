## Why

Teamy biegną równolegle, ale wszystkie handlują na jednym „aktywnym koncie”. To konto jest stanem jedynej sesji capital.com w `capital-gateway`, więc dwa teamy przełączające się na swoje konta przestawiają je sobie nawzajem w trakcie runu, a zlecenie jednego ląduje na koncie drugiego. Kilku strategii nie da się dziś testować obok siebie w izolacji. Pomiary z 28 października (`docs/demo-wiele-kont-rownolegle.html`, sekcja 08) pokazały, że przeszkodę można usunąć: każda sesja capital.com ma własne aktywne konto, zlecenie złożone w jednej nie jest widoczne w drugiej, a przełączenie konta w jednej sesji nie zrywa strumienia innej. Ten sam pomiar potwierdził błąd dzisiejszego kodu: po wygaśnięciu sesji świeży login wraca na konto preferowane, a bramka nie przywraca konta wybranego wcześniej.

## What Changes

- `capital-gateway` trzyma po jednej sesji capital.com na każde konto, którego ktoś użył. Wszystkie sesje dzielą jeden budżet zapytań. Strumień notowań dostaje własną sesję, która nigdy nie zmienia konta.
- Trasy konta i handlu (`/positions`, `/orders`, `/working-orders`, `/accounts/top-up`) przyjmują konto w nagłówku żądania. Bez nagłówka działają na koncie aktywnym, jak dziś. Nieznane konto jest odmową i nigdy nie przechodzi po cichu na konto aktywne.
- Sesja odnowiona po wygaśnięciu wraca na konto, na którym była. Dotyczy to także sesji domyślnej. To poprawka błędu z pomiaru 3 i może zostać wdrożona jako pierwsza.
- Przełączenie konta aktywnego przestaje zrywać strumień notowań, więc ostrzeżenie o zerwaniu znika z opisu trasy, z narzędzia `switch_active_account` i z ekranu kont w terminalu.
- `trading-mcp`: każde narzędzie konta i zleceń przyjmuje opcjonalne `account_id` i przekazuje je do bramki. Konto pojawia się w śladzie `trading_mcp.trace`.
- `teams`: rewizja może nieść konto (`trading.account_id`). Silnik dokleja je do każdego wywołania narzędzia `trading-mcp`, a model nie widzi tego parametru i nie może go nadpisać. Zespół z przypisanym kontem nie może dostać `switch_active_account` ani `top_up_demo_account`. Wiersz śladu zleceń zapisuje konto. Rewizja bez konta działa tak jak dziś.
- Terminal: wybór konta przy granicach handlowych w edytorze zespołu. Ekran kont pokazuje pozycje dowolnego konta bez przełączania konta aktywnego.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `capital-session`: konto wskazywane w żądaniu i sesja na konto, wspólny budżet zapytań, odnowiona sesja wraca na swoje konto, przełączenie konta nie dotyka strumienia, korekta salda wskazanego konta.
- `trading-mcp-tools`: `account_id` w narzędziach konta i zleceń, opis przełączenia bez ostrzeżenia o strumieniu.
- `teams-trading`: rewizja niesie konto, silnik je wstrzykuje, narzędzia wyboru konta są wyłączone dla zespołu z kontem, wiersz śladu niesie konto.
- `terminal-teams`: wybór konta przy granicach handlowych.
- `terminal-accounts`: pozycje dowolnego konta bez przełączania, przełączenie konta bez ostrzeżenia o strumieniu.

## Impact

- Kod: `capital_gateway/client.py` (konto sesji, przywracanie po ponownym logowaniu), nowa pula sesji z jednym `RateGate`, `app.py` (zależność czytająca nagłówek konta, sesja strumienia), `adapter.py`. `trading_mcp/tools/account.py`, `orders.py`, `client.py`. `teams/contract.py`, `runner/engine.py`, `tools/assignment.py`, `store/trades.py`, `validation.py`. Edytor zespołu i ekran kont w terminalu.
- Kontrakty: OpenAPI bramki (nagłówek na trasach konta), snapshot w `trading-mcp`, kontrakt teamów i wygenerowany kontrakt terminala. Po zmianie trzeba uruchomić skill `contract-sync`.
- Baza danych: migracja `teams`, nowa kolumna `account_id` (nullable) w tabeli zleceń, stosowana w `lifespan`.
- Narzędzia MCP: nowy parametr w ośmiu narzędziach zwiększa sumę opisów, więc sufit powierzchni narzędzi `trading-mcp` może wymagać korekty.
- Zgodność: wołający bez nagłówka i rewizje bez konta zachowują się tak jak dziś. Nic nie przestaje działać.
- `review.md` zostanie napisany po wykonaniu zadań, jeśli zmiana na niego zasłuży. Nie jest potrzebny przed implementacją.
