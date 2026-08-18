## Context

Stan i pomiary — `proposal.md`, „Why". Cztery ograniczenia kształtują wszystko poniżej.

**CI nie aplikuje Terraforma i nie będzie.** `terraform-apply.yml` odrzuca każdy plan
ruszający `azuread_*`, bo principal CI ma `Application.Read.All`, nie write. Moduł
`easy-auth-app` składa się wyłącznie z zasobów `azuread_*`, więc jego jedyna droga na
produkcję prowadzi przez lokalny `apply` operatora. Projekt nie ma też branch protection
(prywatne repo na darmowym planie), więc pominięty job nie blokuje niczego — bramka musi być
w treści zadania, nie w wymaganym checku.

**Sonda wdrożenia jest mechanizmem obronnym, który już raz cicho padł.** 16 sierpnia 2026
`deploy-agent.yml` raportował zielono nad kontenerem wychodzącym z kodem 3, bo pytał control
plane o stan *witryny*. Iteracja 0 dołożyła asercję tagu obrazu do wszystkich siedmiu sond —
i **nie dołożyła jej testu**, bo sonda żyje wewnątrz YAML-a, gdzie nie ma jak jej wywołać.
Zasada nr 5 planu („każdy mechanizm obronny ma test swojego trybu awarii") jest więc dla tej
konkretnej obrony niespełniona, a ta zmiana i tak przepisuje wszystkie siedem.

**`scripts/` nie ma dziś żadnego domu testowego.** 1 143 linie shella nie mają testów, bo
shell w tym repo nigdy ich nie miał. Przepisanie ich na ~400 linii Pythona bez testów byłoby
przeniesieniem tego samego braku do języka, w którym brak przestaje być usprawiedliwiony.

**Kolejność startu stacka to wiedza z awarii, nie preferencja.** `trading-mcp` pyta bramę o
`GET /capabilities` i **wychodzi**, gdy odpowiedź nie mówi `demo` — brama, która jeszcze nie
odpowiada, daje „A service exited" i to jest prawda. Ta wiedza żyje dziś w prozie komentarzy
obok bloków startowych i musi przeżyć port.

## Goals / Non-Goals

**Goals:**

- Jedna edycja zmienia kształt wdrożenia dla wszystkich siedmiu aplikacji App Service.
- Jedna edycja zmienia kolejność, port albo komendę startu stacka na obu platformach.
- Sonda wdrożenia ma test swojego trybu awarii — tego z 16 sierpnia, dosłownie.
- Terraform z `infra/**` nie dojeżdża na `main` bez `fmt` i `validate`.
- Nowy moduł App Service to wpis w tabeli dev + ~15 linii wywołującego + tryplet z modułu.
- Stan Terraforma po `apply`: identyczny. Zero `add`, zero `change`, zero `destroy`.

**Non-Goals:**

- Aplikowanie Terraforma przez CI. Nie zmienia się ani o milimetr.
- `for_each` po siedmiu `azurerm_linux_web_app`. Te bloki różnią się naprawdę.
- `deploy-terminal.yml`. Static Web App, inny mechanizm, nie jest wywołującym.
- Wieloetapowe budżety retry w sondzie — kalibracja planu wprost je odrzuca.
- Zmiana czegokolwiek, co moduł robi, publikuje albo czego odmawia.

## Decisions

### D1. Sonda wychodzi z YAML-a do `scripts/deploy_probe.py`, z testem trybu awarii

Reusable workflow woła skrypt; skrypt zawiera pętlę, asercje i komunikat błędu.

Rozważone i odrzucone: **sonda inline w reusable workflow.** Tańsza o jeden plik i o jeden
job CI, i tak wygląda dziś. Odrzucona z jednego powodu: obrona, której trybu awarii nie da
się wywołać, jest dokładnie tym, co repo przestało przyjmować po pierwszej iteracji audytu —
a tu tryb awarii jest znany z dnia i godziny. Test, o który chodzi, jest krótki: control
plane zwraca stary SHA, `/health` zwraca 200, sonda MUSI nie przejść. Drugi: 200 z ciałem,
które nie jest ciałem aplikacji (strona Easy Auth), MUSI nie przejść.

Rozważone i odrzucone: **`scripts/deploy-probe.sh`.** Bash byłby bliżej dzisiejszego kodu,
ale test wymagałby stubowania `az` i `curl` przez PATH, czyli własnego harnessu; a `dev.py`
i tak przynosi Pythona do `scripts/`. Jeden język w tym katalogu, nie dwa.

Szew jest funkcyjny, nie procesowy: pętla przyjmuje `current_image()` i `probe()` jako
argumenty, a `main()` podstawia pod nie `az` i `httpx`. Test woła funkcję, nie proces —
nie ma czego stubować w PATH i nie ma wyścigu o port.

### D2. `scripts/` dostaje własny projekt uv i własny job w `checks.yml`

`scripts/pyproject.toml` (nazwa `tc-scripts`, nie publikowany, bez zależności runtime poza
stdlib i `httpx`), `scripts/tests/`, job `scripts` w `checks.yml` na ścieżce `scripts/**`
uruchamiający `uv run pytest`, `uv run ruff check .`, `uv run pyright` — te same trzy
komendy, co każdy moduł.

Rozważone i odrzucone: **wsadzić testy skryptów do istniejącego modułu.** Każdy kandydat
byłby modułem testującym narzędzie, które nim nie jest; `market-data` testujące runner dev
to gorsza granica niż nowy pyproject.

Rozważone i odrzucone: **bez testów, jak dziś.** To jest stan, który ta zmiana ma zamknąć,
a nie przenieść. Odchylenie od planu iteracji 2 nazwane jawnie: plan mówił „`scripts/dev.py`
zastępuje `dev.sh` + `dev.ps1`" i nie mówił nic o domu testowym. Dom kosztuje jeden
`pyproject.toml` i jeden job, a bez niego zasada nr 5 nie ma gdzie stanąć — ani dla sondy,
ani dla odmów, które runner dev wypowiada przed startem (niezgodny klucz bramy, `DATABASE_URL`
spoza loopbacku). Te odmowy są obronami i mają dokładnie ten kształt, którego zasada nr 5
wymaga: wywołać scenariusz, sprawdzić, że runner odmawia.

### D3. Sonda to jedna pętla z czterema parametrami, nie enum wariantów

Wejścia: `probe_path` (puste = tylko control plane), `expected_status`, `body_contains`
(puste = bez sprawdzenia ciała), `attempts`. Zmierzony rozkład:

| moduł | `probe_path` | status | `body_contains` | próby |
|---|---|---|---|---|
| capital-gateway | *(puste)* | — | — | 10 |
| agent | `/health` | 200 | `"status"` † | 20 |
| teams | `/health` | 200 | `"status"` † | 20 |
| market-data | `/ws/candles` | 404 | `"detail"` | 12 |
| market-mcp | `/health` | 200 | `"status"` | 12 |
| trading-mcp | `/health` | 200 | `"status"` | 12 |
| teams-mcp | `/health` | 200 | `"status"` | 12 |

† Zaostrzenie, nie przeniesienie: dziś `agent` i `teams` przyjmują samo 200, choć oba
zwracają `{"status": "ok"}` (`agent/app.py:111`, `teams/app.py:176`) — dokładnie to, czego
trzy moduły MCP już wymagają. Wartość jest więc odczytana ze źródła, nie zgadnięta, i
zaostrzenie nie kosztuje nic poza jedną linią wejścia.

Rozważone i odrzucone: **`probe_variant: control-plane | health | ws-404`** — kształt, który
proponował plan. Pomiar go podważa: warianty różnią się czterema skalarami, a enum ukrywa je
za nazwą. Pierwszy moduł, który chce `/health` z innym kluczem w ciele, wymusza czwarty
wariant i wtedy nazwa przestaje mówić, co się różni.

Różnica 20 vs 12 prób zostaje parametrem, a nie zostaje uśredniona: `agent` i `teams`
blokują `lifespan` na migracji, więc ich okno musi być dłuższe, i to jest ta sama liczba,
która w `db.py` odróżnia `migration_lock_wait_seconds` agenta od market-daty.

### D4. Bloki `moved` w HCL, nie `terraform state mv`

Rozważone i odrzucone: **osiemnaście `terraform state mv` z ręki.** Osiemnaście wywołań
przeciw współdzielonemu stanowi, bez artefaktu w diffie i bez planu, który ktokolwiek
przeczyta przed apply. `moved` jest deklaratywne, idempotentne i widoczne w PR — a plan CI
na tym PR pokazuje wynik przed tym, jak operator cokolwiek zaaplikuje.

Bramka: zadanie nie jest zrobione, dopóki lokalny `terraform plan` nie powie
`0 to add, 0 to change, 0 to destroy`. Nie „prawie zero" — zero.

### D5. `terraform validate` w `checks.yml` przez `init -backend=false`

`fmt -check` + `init -backend=false` + `validate`. Bez backendu: bez poświadczeń Azure, bez
blokady stanu, bez OIDC — więc job biegnie także na PR z forka i nie ściga się z lokalnym
`apply` operatora.

Rozważone i odrzucone: **dodać `push: main` do `terraform.yml`.** Dałoby pełny `plan` po
merge'u, ale każdy merge brałby wtedy blokadę stanu i wymagałby OIDC, a `plan` na `main` po
fakcie odpowiada na pytanie, na które chcieliśmy odpowiedzieć przed.

### D6. Tabela serwisów to dane w Pythonie, nie `services.json`

Lista zamrożonych dataclass w `dev.py`: `name`, `directory`, `port`, `command`,
`health_path`, `log_prefix`, `color`, `why` — gdzie `why` jest tą prozą, która dziś siedzi w
komentarzu obok bloku startowego.

Rozważone i odrzucone: **`scripts/services.json`** — propozycja audytu. Była słuszna, gdy
czytały ją dwa skrypty w dwóch językach. Przy jednej implementacji JSON dokłada parser i
walidację, a odbiera to, co `pyright` daje za darmo.

### D7. Wrappery zostają

`dev.sh` i `dev.ps1` kurczą się do przekazania argumentów. `./scripts/dev.sh`,
`./scripts/dev.ps1 -NoTerminal` i wszystko, co o nich mówią `CLAUDE.md` i `README.md`, dalej
działa. Dryf ginie konstrukcyjnie, bo w wrapperze nie ma czego rozjechać: ~5 linii bez ani
jednej decyzji. Alternatywa (skasować oba) jest czystsza o dwa pliki i droższa o wszystkie
nawyki i dwa dokumenty — wybór operatora, zapisany tu, żeby następny czytelnik nie „poprawił"
wrapperów przez usunięcie.

## Risks / Trade-offs

**Plan Terraforma pokazuje `destroy` + `create` zamiast `moved` na `azuread_application_password`**
→ sześć rotacji sekretu Easy Auth, czyli sześć aplikacji odrzucających każdy token
operatora, do ręcznej naprawy. Największe ryzyko iteracji. Mitygacja trójstopniowa:
`moved` zamiast `state mv` (D4); plan czytany na PR przez CI **przed** jakimkolwiek apply;
bramka `0/0/0` jako warunek ukończenia zadania. Rollback: `git revert` bloków `moved` i
modułu przywraca stan opisany tak, jak jest w state — dopóki nikt nie zaaplikował.

**Reusable workflow nie widzi zmiennych zakresowanych do środowiska `production`**
→ `azure/login` dostaje pusty `client-id` i wszystkie siedem wdrożeń pada naraz. To trap
`workflow_call`: sekrety nie dziedziczą się automatycznie, a zmienne środowiskowe wymagają,
by *wołany* job deklarował `environment: production`. Mitygacja: wołany job deklaruje je
sam, a pierwsze wdrożenie idzie na jednym module (`market-mcp` — najmniejszy blast radius:
bez bazy, bez klucza OpenAI, jedyny konsument to agent i teams przez sieć), nie na siedmiu.

**Sonda z zaostrzoną asercją ciała odrzuca poprawne wdrożenie `agent`/`teams`**
→ zielony deploy staje się czerwony bez powodu. Ryzyko jest małe, bo klucz `status` jest
odczytany z ich własnych handlerów, a nie z pamięci (D3) — ale jest niezerowe, gdyby przed
kontenerem stanęło coś, co zwraca 200 z innym ciałem. Mitygacja: pierwsze wdrożenie po
zamianie idzie na `market-mcp`, którego asercja się nie zmienia, więc czerwień na `agent`
byłaby wtedy sygnałem o `agent`, nie o wspólnym workflow.

**`dev.py` gubi którąś z odmów, którą shell wypowiadał** → wraca awaria, przed którą ta
odmowa broniła: stack idzie w dół z „A service exited", albo dev pisze do zdalnej bazy.
Mitygacja: każda odmowa dostaje test w `scripts/tests/` (D2), a nie jest przenoszona na
oko. Odmowy do pokrycia: niezgodność `CAPITAL_GATEWAY_API_KEY` z `GATEWAY_API_KEY`,
`DATABASE_URL` poza loopbackiem, brak Dockera, zajęty port, brak `OPENAI_API_KEY`.

**Wrapper w PowerShellu i wrapper w bashu przekazują flagi inaczej** → jedyny dryf, jaki
zostaje po D7. Mitygacja: `dev.py` przyjmuje oba pisownie (`--no-terminal` i `-NoTerminal`)
i test sprawdza, że dają ten sam wynik parsowania. Trzy linie testu za zamknięcie ostatniej
szczeliny tej pary.

**Iteracja 2 jest równoległa do iteracji 3 i 4** (`.github/`, `scripts/`, `infra/`
przeciw `modules/terminal` i kodowi modułów) → konflikt tylko w `checks.yml`, gdy tamte
dołożą filtr. Mitygacja: ta zmiana idzie na `main` pierwsza, bo przepisuje `checks.yml` i
siedem `deploy-*.yml`; rebase po niej jest trywialny, przed nią nie.

## Open Questions

Brak otwartych. Jedyne pytanie tego designu — zakres zmiennych `AZURE_*` — zostało
odczytane z ustawień repozytorium przy zadaniu 3.1: to **zmienne repozytorium**, a
środowisko `production` nie ma własnych. Odpowiedź nie zniosła jednak deklaracji
`environment: production` w wołanym jobie, i to z ostrzejszego powodu, niż zakładało
pytanie: federated credential w `github-oidc.tf` ma w subject `:environment:production`,
więc job bez tej deklaracji nie uwierzytelni się do Azure wcale — niezależnie od tego,
skąd czyta zmienne.
