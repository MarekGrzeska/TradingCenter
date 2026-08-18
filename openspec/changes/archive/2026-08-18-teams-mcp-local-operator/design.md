## Context

Motywacja jest w `proposal.md` — „Why". Tu tylko to, co ogranicza rozwiązanie.

Dzisiejszy łańcuch: terminal → `agent` (`Authorization` operatora, zdjęty z obsługiwanego
żądania) → `teams-mcp` (`x-operator-authorization`) → `teams` (`Authorization`, walidowany
przez Easy Auth, principal kładziony na żądanie). `teams-mcp` nie wysyła w tym łańcuchu
własnej tożsamości zarządzanej — ta odpowiada na inne pytanie, o jeden hop wcześniej
(`client.py`, docstring).

Trzy fakty w kodzie kształtują rozwiązanie:

- `operator.py::operator_token` jest jednym miejscem, przez które ta decyzja przechodzi, i
  jest wołane z `tools/_shared.py::_call` **przed** czymkolwiek sieciowym. Nie ma dostępu do
  `Settings` — dostaje wyłącznie `Context` MCP.
- `tools.register(mcp, teams)` przekazuje warstwie narzędzi **tylko klienta**. `Settings`
  kończy się na `build_server`/`build_http_app`.
- `Settings._upstream_mode_is_coherent` już wie, czy `teams_url` jest w pętli zwrotnej, i już
  wymusza równoważność: pętla zwrotna ⟺ `TEAMS_SCOPE` nieustawione. Logika jest wpisana w
  środek walidatora i nie jest z niego wyprowadzona.
- `teams/auth.py` przypisuje `UNAUTHENTICATED = "anonymous"` każdemu żądaniu bez nagłówków
  principala, dopóki jego własne `require_authenticated_principal` jest wyłączone. Lokalny
  terminal dostaje dokładnie to samo, więc lokalnie nie ma dwóch właścicieli do pogodzenia.

Produkcja jest po drugiej stronie obu warunków naraz, sprawdzone w `infra/app-service.tf`:
`app-tradingcenter-teams-mcp` ma `REQUIRE_AUTHENTICATED_PRINCIPAL = "true"` i
`TEAMS_URL = https://app-tradingcenter-teams.azurewebsites.net`.

## Goals / Non-Goals

**Goals.** Jedno miejsce decyzji, ta sama funkcja co dziś. Tryb lokalny nieosiągalny z
produkcyjnej konfiguracji przez **dwa** niezależne warunki, nie jeden. Stan widoczny przy
starcie, a nie wywnioskowany z braku odmowy.

**Non-Goals na poziomie projektu** (poza tym, co wyłącza `proposal.md`): nie wprowadzamy
lokalnego uwierzytelniania ani udawanego tokena; nie ruszamy `teams`, `agent` ani terminala;
nie zmieniamy niczego w `infra/**`; nie rozszerzamy zakresu nasłuchu — `TEAMS_MCP_HOST`
zostaje w pętli zwrotnej.

## Decisions

### Dwa warunki, nie jeden

Tryb lokalny wymaga **obu**: `require_authenticated_principal == False` **i** `teams_url` w
pętli zwrotnej.

Rozważone: **tylko `require_authenticated_principal == False`** — odrzucone, bo ta flaga mówi
o hopie *przed* tym modułem, a token, którego brakuje, waliduje `teams`, czyli hop *za* nim.
Instancja z wyłączoną flagą, ale wskazująca zdalne `teams` — na przykład wystawiona przez
tunel przy diagnozie — pisałaby wtedy do prawdziwego katalogu jako `anonymous`, cicho.
Rozważone: **tylko pętla zwrotna w `teams_url`** — odrzucone, bo za uwierzytelniaczem brak
tokena jest usterką łańcucha i ma się nią pozostać; kształt „Easy Auth przed modułem, `teams`
lokalnie" nie występuje, ale jeśli wystąpi, to jako pomyłka, a nie jako maszyna deweloperska.
Rozważone: **osobne ustawienie** (`ALLOW_UNAUTHENTICATED_OPERATOR`) — odrzucone: trzecie
ustawienie, którego jedyna poprawna wartość wynika z dwóch już istniejących, i dokładnie ten
rodzaj ustawienia, który ktoś kiedyś przestawi w Azure „na chwilę".

Warunek liczony **raz**, jako własność `Settings` wyprowadzona z tego, co walidator już
sprawdza. Rozpoznawanie pętli zwrotnej wychodzi z ciała `_upstream_mode_is_coherent` do
własnej funkcji i jest wołane z obu miejsc — dziś ta wiedza jest w jednym wyrażeniu wewnątrz
walidatora i drugi czytelnik nie ma jak jej użyć.

### Brak nagłówka, nie udawany token

W trybie lokalnym `client.py` **nie wysyła `Authorization`**. Nie wysyła też `Bearer ""`.

Rozważone: **podstawiony token** (`Bearer local-operator`) — odrzucone z dwóch powodów naraz.
Pierwszy: `teams` lokalnie nie czyta `Authorization` w ogóle — principal bierze z nagłówków
`X-MS-CLIENT-PRINCIPAL-*` — więc podstawiony token nie robiłby nic poza wyglądaniem na
poświadczenie. Drugi: sfabrykowane poświadczenie na drucie jest tym, przed czym stoi całe
`teams-mcp-authorship`, a w dniu, w którym `teams` zacząłby walidować `Bearer` samodzielnie,
zaczęłoby się zachowywać inaczej — i to bez żadnej zmiany tutaj.

Typ `token: str` w `TeamsClient` i w `operator.py` staje się `str | None`. `None` znaczy
„świadomie żadnej tożsamości", a nie „zapomniano" — czego pilnuje warunek wyżej, jedyne
miejsce, które umie zwrócić `None`.

### Decyzja zostaje w `operator.py`, a warunek dojeżdża klientem

`operator_token` dostaje argument mówiący, czy brak tożsamości jest dopuszczalny, i pozostaje
jedynym miejscem, które o tym rozstrzyga — razem ze swoim komunikatem odmowy i ze swoim
docstringiem, gdzie czytelnik tej zasady szuka.

Warunek dociera do `_call` przez `TeamsClient`, który `Settings` już trzyma (czyta z nich
`teams_url` i limit czasu). Rozważone: **przekazać `Settings` przez `tools.register` do
`_call`** — odrzucone, bo to zmiana sygnatur w każdym module narzędzi po to, żeby dowieźć
jeden bool tam, gdzie już stoi obiekt zbudowany z tych samych ustawień. Rozważone:
**rozstrzygać w `_shared.py`** — odrzucone: dwie funkcje znałyby wtedy tę samą zasadę, a
odmowa jest w `operator.py` i tam ma zostać.

### Jedna linia przy starcie, nie dopisek do każdej odpowiedzi

Stan „narzędzia działają bez tożsamości" jest ogłaszany raz, logiem przy starcie, nazywającym
oba warunki.

Rozważone: **zdanie dopisywane do odpowiedzi każdego narzędzia** — odrzucone, bo płaci się za
nie tokenami modelu w każdym wywołaniu i różnicuje treść odpowiedzi lokalnych i
produkcyjnych, czyli psuje jedyną rzecz, którą lokalny przebieg ma dowodzić. Precedens za
logiem jest w repozytorium: `teams` mówi w ten sposób o wyłączonym zegarze
(`scheduler/clock.py`, `Clock.start`).

## Risks / Trade-offs

- **Instancja wdrożona wchodzi w tryb lokalny** → wymagane oba warunki, a produkcyjne
  ustawienia są po przeciwnej stronie obu (sprawdzone w `infra/app-service.tf`). Do tego
  `Settings` już odmawia startu przy niespójnej parze `TEAMS_URL`/`TEAMS_SCOPE`, więc
  „zdalny `teams` bez tożsamości" nie jest konfiguracją, którą da się zapisać po cichu.
  Testy: odmowa przy każdej z dwóch połówek osobno.
- **Tryb lokalny zasłania prawdziwą usterkę** — łańcuch, w którym token *powinien* dojść, a
  nie dochodzi → dopuszczalne tylko tam, gdzie nikt nie mógł go wystawić; wszędzie indziej
  komunikat odmowy zostaje słowo w słowo. Linia przy starcie mówi, w którym stanie moduł
  wstał.
- **Lokalnie wszystko należy do jednego właściciela** (`anonymous`), więc dwóch operatorów na
  jednej maszynie nie da się rozróżnić → przyjęte: tak jest lokalnie już dziś dla terminala,
  a to jest maszyna deweloperska, nie instalacja wieloosobowa.
- **Lokalny przebieg zaczyna kosztować** — narzędzia, które dotąd odmawiały, teraz uruchamiają
  zespoły i płacą za tokeny → to jest cel zmiany, a granice zostają te, które `teams` już ma:
  dobowa granica kosztu zespołu i granice handlowe obowiązują tak samo, gdy prosi model
  (`teams-mcp-authorship`, „Moduł nie rozszerza uprawnień, które operator już ma").

## Migration Plan

Bez migracji danych, bez zmiany kontraktu, bez `terraform apply`. Kolejność wdrożenia lokalnie
to restart stosu — `teams-mcp` czyta `Settings` przy starcie.

**Kolejność archiwizacji jest wiążąca:** zdolność `teams-mcp-authorship` jest dziś w
niezarchiwizowanej zmianie `add-teams-mcp`, a nie w `openspec/specs/`. `openspec validate
--strict` tego nie łapie — przeszło z tą deltą przy nieistniejącej zdolności — więc pilnuje
tego ten akapit i zadanie w `tasks.md`: najpierw archiwum `add-teams-mcp`, potem tej zmiany.
Odwrotna kolejność daje `MODIFIED` bez celu i cicho gubi treść wymagania.

**Rollback.** `REQUIRE_AUTHENTICATED_PRINCIPAL=true` w `modules/teams-mcp/.env` przywraca
dzisiejsze zachowanie bez wycofywania kodu — moduł wraca do odmawiania, a lokalny czat wraca
do stanu „narzędzia Teams odmawiają i mówią dlaczego".
