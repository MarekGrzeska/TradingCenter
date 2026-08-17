## Why

Operator rozmawia z agentem o rynku i nie może przez tę rozmowę zobaczyć własnych pozycji,
salda ani otwartych zleceń — `trading-mcp` ma jednego wołającego i jest nim `teams`. Żeby
ruszyć rachunek, operator musi złożyć zespół, zapisać rewizję i uruchomić przebieg; żeby
tylko *sprawdzić* pozycję, musi wyjść z czatu do terminala. To jest droga wokół czegoś, co
istnieje: dziewięć narzędzi stoi gotowych za portem, do którego agent nie ma wpisu.

Zmiana daje modułowi `agent` ten sam zestaw, jaki ma `teams` — czytający i zapisujący,
bez potwierdzenia i bez granic po stronie tego modułu. Jest to świadoma decyzja operatora,
dokładnie w tej formie, jakiej wymaga `trading-mcp-transport`: „dopisanie kolejnego ma być
decyzją, nie skutkiem ubocznym". Zasięg ogranicza `trading-mcp`, który nie otwiera portu,
dopóki gateway nie potwierdzi rachunku demonstracyjnego, a nie liczba wpisana w ten moduł.

## What Changes

- **BREAKING (na poziomie wymagania, nie wire'u):** agent przestaje być modułem, który
  zapisuje wyłącznie w widoku terminala. Wymaganie `agent-tools` „Agent zapisuje wyłącznie
  w widoku terminala" mówi dziś wprost „nie składa zlecenia" i „serwer narzędzi MUST
  pozostać czytający", ze scenariuszem, w którym agent proszony o złożenie zlecenia
  odpowiada, że to poza jego zakresem. Zostaje przemianowane i przepisane.
- Agent dostaje trzeci serwer narzędzi: `trading-mcp`, konfigurowany i psujący się
  niezależnie od `market-mcp` i `teams-mcp`. Brak adresu to obsługiwany stan — agent bez
  narzędzi handlowych, tak jak dziś bez tamtych dwóch.
- Wywołania zmieniające stan rachunku dostają ślad o innym kształcie niż pozostałe:
  wiersz przed wysłaniem, uzupełniony skutkiem, gdy ten wróci, oraz skutek **nieznany**
  jako wartość, a nie jako brak wiersza. Dziś cały ślad tury zapisuje się po jej końcu, w
  jednej paczce z odpowiedzią (`turn.py`) — tura przerwana po złożeniu zlecenia nie
  zostawia po nim nic.
- Agent MUST NOT twierdzić, że zlecenie zostało złożone, gdy skutku nie zna.
- Ten moduł MUST NOT nieść własnej granicy wielkości ani liczby zleceń — tak samo jak
  `teams` nie trzyma ich w konfiguracji, i z tego samego powodu.
- `trading-mcp` dostaje drugiego wołającego wymienionego imiennie. Sama reguła transportu
  („lista wyliczona, nigdy «każdy uwierzytelniony w katalogu»") zostaje bez zmian — już
  dopuszcza tylu wołających, ilu wymieniono, więc jej wymaganie nie jest tu zmieniane.

## Capabilities

### New Capabilities
- `agent-trading`: na jakich warunkach rozmowa rusza rachunek — czego moduł nie
  narzuca, co zostaje w śladzie po każdym wywołaniu zapisującym i czego agent nie ma prawa
  operatorowi powiedzieć o zleceniu, którego skutku nie zna.

### Modified Capabilities
- `agent-tools`: wymaganie „Agent zapisuje wyłącznie w widoku terminala" — przemianowane i
  przepisane na wskazany zakres zapisu, w którym rachunek demonstracyjny stoi obok widoku
  terminala; wypada z niego zdanie o serwerze narzędzi, który MUST pozostać czytający, oraz
  scenariusz odmowy złożenia zlecenia. Warunek odwracalności ręką operatora przestaje
  obowiązywać dla rachunku — zlecenia wykonanego operator nie cofa wybierakiem — i to
  wymaga powiedzenia, co stoi na jego miejscu.
- `terminal-chart`: wymaganie „Operator zarządza naniesionymi obiektami z listy" cytuje
  przemianowane wymaganie z nazwy; cytat idzie za nazwą.

## Impact

**`modules/agent`** — `config.py` (trzeci triplet ustawień, sprawdzany osobno),
`tools/registry.py` (trzeci `ToolServer`, bez tokenu operatora: `trading-mcp` działa na
tożsamości modułu, nie w imieniu osoby), `prompt.py` (co model wie o narzędziach ruszających
rachunek), `store.py` + migracja Alembica (ślad przed wysłaniem: `tool_calls.message_id`
jest dziś `NOT NULL`, a w chwili wywołania odpowiedzi jeszcze nie ma — kształt do
rozstrzygnięcia w `design.md`), `turn.py` (dwufazowy zapis dla wywołań zapisujących),
`.env.example`, `README.md`.

**`infra/app-service.tf`** — tożsamość zarządzana `agent` w `allowed_applications`
`trading-mcp` (dziś lista jednoelementowa) oraz `TRADING_MCP_URL` i `TRADING_MCP_SCOPE` w
`app_settings` agenta. Wymaga `terraform apply` ręką operatora, bo CI nie aplikuje;
narzędzia pojawiają się po tym `apply` i po restarcie agenta, nie po deployu obrazu.

**`modules/terminal`** oraz `agent/contract.py` — transkrypt niesie już wywołania narzędzi
wraz ze skutkiem, więc dochodzi nowa wartość skutku („nieznany") i osobna lista wywołań,
które przetrwały turę bez wypowiedzi agenta (`design.md`, D1). Kontrakt agenta nie jest
generowany, więc jedyną kontrolą tego pairingu są ręcznie pisane DTO terminala i jego testy.

**`scripts/dev.sh`, `scripts/dev.ps1`** — podpowiedź o brakującym `TRADING_MCP_URL` w
`.env` agenta, tak jak dziś o `MARKET_MCP_URL`; kolejność startu jest już dobra
(`trading-mcp` wstaje przed agentem).

**`CLAUDE.md`, `docs/`** — `trading-mcp` jest tam opisany jako moduł z jednym nazwanym
wołającym, w trzech miejscach.
