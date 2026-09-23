## Why

**Grupy obserwacji dało się tylko dokładać.** Kontrakt REST pozwalał grupę utworzyć, przypisać do
niej wydarzenie i ją skasować, ale nie przemianować; pocket nie umiał z grupami nic poza filtrem;
a model — jedyny, który grupy tworzy hurtowo — miał jedno narzędzie, `create_group`, i żadnego,
żeby zobaczyć, jakie grupy już są. Skutek jest na produkcji: modele potworzyły duplikaty tej samej
kategorii w różnej pisowni, a jedyny, kto mógł je posprzątać, to operator w terminalu, klikając
wydarzenie po wydarzeniu. Unikalność nazwy trzymała się dokładnego ciągu znaków, więc „Crypto" i
„crypto " były dla bazy dwiema grupami.

**Katalog modeli przestał odpowiadać temu, co OpenAI sprzedaje.** 4 września 2026 wyszedł GPT-6
Astra, 22 września GPT-6 Sol i GPT-6 Luna. Operator chce w wybieraku wyłącznie tych trzech, z Luną
jako domyślną do większości pracy.

To jest zmiana OpenSpec z dwóch powodów niezależnie: zmienia wymaganie `polymarket-data-tools`
(„jedyne narzędzia zmieniające stan dopisują") i dotyka `infra/**` (katalog modeli jest w
Terraformie).

## What Changes

- **Grupa ma jedną nazwę, niezależnie od pisowni.** Indeks unikalny na nazwie po `lower` i
  zwinięciu białych znaków (migracja polymarket `0005`). Duplikaty już istniejące migracja scala
  do najstarszej grupy danej pisowni — wydarzenia przechodzą, nic innego się nie rusza.
  Utworzenie grupy nazwą istniejącej w innej pisowni zwraca tę istniejącą.
- **Kontrakt REST dostaje przemianowanie i scalanie.** `PATCH /groups/{id}` (409, gdy nazwę nosi
  już inna grupa) oraz `DELETE /groups/{id}?move_events_to={id}` — skasowanie grupy z
  przeniesieniem jej wydarzeń do innej, czyli scalenie duplikatu jednym aktem.
- **Pięć narzędzi grup zamiast jednego.** `list_groups` (czyta), `create_group`, `rename_group`,
  `move_event_to_group`, `delete_group` (z `move_events_to`). `delete_group` jest jedynym
  narzędziem oznaczonym jako destrukcyjne — ginie grupa, nie żadna obserwacja ani próbka.
- **Narzędzie pyta, zanim stworzy podobną grupę.** Nazwa, która tylko *przypomina* istniejącą
  (podzbiór słów, wspólny początek, kilka liter różnicy — `group_names.similar`), jest odmową z
  listą podobnych, dopóki model nie potwierdzi `confirm_new`. `track_event` z nową grupą zadaje to
  samo pytanie. REST tego nie robi: operator wpisuje nazwę świadomie.
- **Oba ekrany dostają porządkowanie grup.** Terminal: przemianowanie wybranej grupy i wybór grupy
  docelowej przy kasowaniu. Pocket: arkusz „Groups" (przemianowanie, kasowanie ze scaleniem) i
  „Move to group" na karcie wydarzenia.
- **Katalog modeli: `gpt-6-luna`, `gpt-6-sol`, `gpt-6-astra`**, stawki standardowe z cennika
  OpenAI z 23 września 2026 (za 1M tokenów: Luna 0,10/0,50 USD, Sol 2/10, Astra 10/50), Luna
  domyślna. Stawki powyżej 272K tokenów wejścia i ceny cache nie są modelowane — katalog nie ma
  na nie pola, a rozmowy tej długości tu nie występują.
- **Sesje i rewizje na starych modelach przechodzą na następców — przy starcie, nie migracją.**
  Mapa sukcesji leży w asemblacji (`workbench/model_successors.py`): Luna→Luna i Sol→Sol to
  sukcesja OpenAI, Terra nie ma następcy i idzie na Sol, wpis w jej cenie. Przy każdym starcie
  procesu sesja albo agent rewizji, który wskazuje model **nieobecny** w skonfigurowanym katalogu,
  przechodzi na następcę — ale tylko wtedy, gdy następca **jest** w katalogu. Migracja nie
  wiedziałaby, co skonfigurowano: przepisałaby dane przed `apply` operatora i do tego czasu
  zostawiła produkcję z sesjami na modelach, których katalog nie zna. Tak kolejność wdrożenia i
  `apply` jest obojętna, a katalog bez następcy zostawia odmowę nazywającą stary model.
  Wiadomości i `usage` zachowują model, którym naprawdę powstały. **Rewizja zespołu jest tu
  przepisywana w miejscu** — wbrew temu, że jest niezmiennym blobem — bo nowa rewizja zostawiłaby
  w tyle harmonogramy przypięte do starej, a te odmawiałyby startu.
- **`social_data`**: tłumaczenie na Lunie, analiza na Solu (wcześniej Terra, średnia półka).

## Capabilities

### Modified Capabilities

- `polymarket-data-tools`: zestaw zmienia listę obserwacji **i jej grupy**; nowe wymaganie, że
  narzędzie pyta przed utworzeniem grupy podobnej do istniejącej.
- `polymarket-data-api`: grupy da się przemianować i scalić; nazwa grupy jest jedna niezależnie
  od pisowni.
- `terminal-polymarket`: operator przemianowuje, przenosi i scala grupy.

`agent-models` i `teams-models` się nie zmieniają: katalog jest konfiguracją, a wymagania mówią o
tym, jak moduł traktuje model wycofany — nie o tym, jakie modele są w katalogu. Przejście na
następców dzieje się w asemblacji, raz dla każdego wiersza, i nie podmienia modelu w chwili
wywołania.

Pocket nie ma własnej specyfikacji i ta zmiana jej nie zakłada.

## Impact

- **Kod**: `polymarket_data/{store,group_names,routers/groups,routers/observations,mcp_app}.py`,
  `polymarket_data/tools/{groups,observations,archive,_shared,__init__}.py`, `social_data/config.py`;
  migracja polymarket `0005`; `workbench/{model_successors,app}.py`,
  `agent/store/sessions.py`, `teams/store/catalogue.py`. Terminal: `GroupBar.tsx`,
  `polymarketApi.ts`. Pocket: `api.ts`, `useArchive.ts`, `PolymarketScreen.tsx`, `EventCard.tsx`,
  nowe `GroupsSheet.tsx`, `MoveEventSheet.tsx`. Kontrakt polymarket wygenerowany na nowo w obu.
- **Powierzchnia narzędzi polymarket**: 16 266 znaków przy dwunastu narzędziach; sufit podniesiony
  świadomie z 15 500 do 18 250, ten sam zapas 12%.
- **Infrastruktura**: `infra/variables.tf` (`agent_models`, `teams_models`), `infra/app-service.tf`
  (`AGENT_DEFAULT_MODEL_ID`). **Operator: `apply`**, w dowolnej chwili względem wdrożenia. Do
  tego czasu produkcja ma stary katalog i działa na nim jak dotąd; restart po `apply` przenosi
  sesje i rewizje na GPT-6.
- **Bez `design.md`** — decyzje są cztery i każda ma akapit powyżej. **Bez `tasks.md`** — zmiana
  powstała i została wdrożona w jednym PR, lista zadań nie miałaby czego pilnować.
