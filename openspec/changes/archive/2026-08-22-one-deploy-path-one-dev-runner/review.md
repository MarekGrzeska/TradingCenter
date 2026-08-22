## Verdict

Weszło wszystko z ośmiu grup zadań poza uruchomieniem stacka i obejrzeniem wdrożeń przez
Actions — te dwie rzeczy są świadomie odroczone do testów po całości i tak są odhaczone,
nie jako zrobione. Terraform jest zaaplikowany, `plan` mówi `No changes`, siedem aplikacji
odpowiada. Trzy znaleziska z przeglądu diffa były realne, dwa z nich **zepsułyby produkcję
przy pierwszym merge'u** — są naprawione w `d29637f`, każde z testem, który czerwienieje po
odwróceniu poprawki.

Czego następny czytelnik nie powinien wziąć za przeoczenie: `moved.tf` jest jednorazową
instrukcją i schodzi przy archiwizacji tej zmiany; cel „~175 linii workflow" nie jest
osiągnięty i nie będzie (256, uzasadnienie niżej); a `infra/` urosło o 139 linii, co przy
tym celu wygląda na porażkę i nią nie jest.

## Verified

Uruchomione, nie zadeklarowane:

```
scripts/    uv run pytest -q      155 passed
            uv run ruff check .   All checks passed
            uv run pyright        0 errors, 0 warnings
infra/      terraform fmt -check -recursive .        (czysto, oba rooty)
            terraform init -backend=false + validate  Success (infra i infra/bootstrap)
            terraform plan                            0 to add, 8 to change, 0 to destroy
            terraform apply <zapisany plan>           Apply complete
            terraform plan (po apply)                 No changes
```

Po `apply`, przeciw produkcji:

```
market-mcp   /health   200      teams        /health   200
trading-mcp  /health   200      agent        /health   200
teams-mcp    /health   200      market-data  /ping     200
```

`trading-mcp` odpowiadające 200 jest tu najmocniejszym pojedynczym sygnałem: ten moduł nie
otwiera portu, dopóki brama nie potwierdzi konta demo, więc 200 znaczy, że doszedł do bramy
przez jej firewall ze wspólnym kluczem.

Bramka przeniesienia stanu sprawdzona przez **uruchomienie planu na `main` w osobnym
worktree** i porównanie treści, nie przez przeczytanie liczby na końcu — patrz `design.md`,
D4, gdzie bramka jest z tego powodu przeformułowana.

Stack lokalny **nie był uruchamiany** (odroczone). Sprawdzone zamiast tego bez startowania
czegokolwiek: `preflight` na realnym repo daje 0 problemów, oba wrappery dochodzą do
`dev.py` z kodem 0, `--explain` wypisuje kolejność.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| krytyczne | `.github/workflows/deploy-*.yml` (7×) | Wywołujący stracili blok `permissions:` przy zamianie na callery. Reusable workflow może tylko **zawęzić** token wywołującego, nigdy poszerzyć; domyślne uprawnienie tego repo to `read` (sprawdzone przez API), a `id-token` nie jest nadawane domyślnie **nigdy**. Każde wdrożenie padłoby na `azure/login` z `Unable to get ACTIONS_ID_TOKEN_REQUEST_URL`, a push do GHCR na braku `packages: write`. | FIXED `d29637f` |
| krytyczne | `scripts/dev.py` (`Stack.start`) | `pnpm` i `npx` to shimy `.CMD` na Windows, a CreateProcess dokleja tylko `.exe`. `dev.ps1` podniósłby siedem back endów i wywalił się na ostatnim kroku niezłapanym `FileNotFoundError`, kładąc resztę. `preflight` tego nie łapie, bo `shutil.which` **znajduje** `pnpm.CMD` — sprawdzone empirycznie na tej maszynie. | FIXED `d29637f` |
| średnie | `scripts/dev.py` (`real_environment`) | `port_owner` nie był podawany, więc odmowa „port 8010 is already in use" straciła człon „by uvicorn (pid 4312)", który drukowały oba skrypty shellowe — czyli tę połowę komunikatu, która mówi, że to własna pozostałość po poprzednim uruchomieniu. Test asertujący `"by uvicorn"` przechodził wyłącznie na wstrzykniętej atrapie. | FIXED `d29637f` |

Dwa z tych trzech mają wspólny kształt i to jest jedyna rzecz warta wyniesienia z tego
przeglądu: **jednostka poprawna, okablowanie zepsute.** Blok `permissions` istniał i był
asertowany — w pliku, w którym nie ma efektu. `resolve_command` po poprawce był poprawny i
przetestowany — a `Stack.start` mógł go w ogóle nie wołać. Odwrócenie poprawki nr 2 przeszło
przez testy za pierwszym razem i dopiero dopisany test okablowania (Popen dostaje
rozwiązaną ścieżkę) je zaczerwienił.

Sprawdzone i czyste przy okazji, żeby nie zostało to do sprawdzenia komuś innemu:
`moved.tf` pokrywa dokładnie te 21 adresów Entra i 7 Key Vault, które się przeniosły;
strażnik `azuread_*` w `terraform-apply.yml` dalej działa na zasobach zagnieżdżonych w
module, bo dopasowuje `.type`, nie `.address`; `/health` agenta i teams naprawdę zwraca
`{"status":"ok"}`, więc dołożona asercja ciała się trzyma.

## Spec coverage

Zmiana ma `skip_specs: true` — nie zmienia żadnego wymagania w `openspec/specs/`, więc nie
ma delty do przejścia. Kryterium przyjęte zamiast pokrycia specyfikacji było w
`proposal.md` sformułowane jako tożsamość zachowania, i tak zostało sprawdzone:

| Twierdzenie z propozycji | Czym udowodnione |
|---|---|
| Obraz budowany z tych samych plików | `scripts/tests/test_deploy_workflows.py::TestSharedWorkflow::test_tags_the_image_with_the_commit_and_never_latest`; kontekst i Dockerfile per wywołujący w `TestEveryCaller::test_names_its_module_and_its_app` |
| Sonda pyta o to samo lub więcej | `test_deploy_probe.py::test_a_healthy_answer_from_the_previous_container_does_not_pass`, `::test_a_200_whose_body_is_not_the_app_does_not_pass`, `::test_market_datas_404_with_a_detail_body_passes`, `TestControlPlaneOnly` (3 przypadki) |
| Wdrożenie nadal ma czym się uwierzytelnić | `test_deploy_workflows.py::TestEveryCaller::test_declares_the_permissions_itself` (dopisany po znalezisku), `TestSharedWorkflow::test_declares_the_production_environment` |
| Stack startuje w tej samej kolejności | `test_dev.py::TestStartOrder::test_the_order_is_the_one_both_scripts_claimed_to_have`, `::test_ports_are_the_fixed_ones`, `::test_every_back_end_is_waited_for` |
| Runner odmawia dokładnie tego, czego odmawiał | `test_dev.py::TestRefusals` — 5 scenariuszy odmowy plus 5 parametryzowanych po `REQUIRED_ENV` |
| Ostrzeżenia dalej są ostrzeżeniami, nie odmowami | `test_dev.py::TestAdvisoriesAreNotRefusals` (5 parametryzowanych + niezależność trzech URL-i) |
| Filtr CI decyduje tak samo | `test_checks_filter.py` — 16 przypadków, w tym oba kierunki spójności job↔wzorzec |
| Stan Terraforma identyczny | plan `main` vs plan gałęzi, porównane treścią (sekcja **Verified**) |

## Gaps

- **Uruchomienie stacka i obejrzenie siedmiu wdrożeń w Actions** — odroczone świadomie do
  testów po całości (zadania 3.5, 4.6, 5.11). Pierwsze wdrożenie przez wspólny workflow
  powinno pójść na `market-mcp`: bez bazy i bez klucza OpenAI, najmniejszy blast radius.
- **Żaden `deploy-*.yml` nie obserwuje `packages/`** — poprawka w `tc-runtime` albo
  `tc-mcp-kit` nie wywoła wdrożenia żadnego modułu, mimo że pakiet jest zapiekany w obraz.
  To luka z iteracji 1, nie z tej zmiany, i celowo tu nie ruszona: dodanie tego zamieniłoby
  jeden commit w pakiecie w sześć równoległych wdrożeń, co jest osobną decyzją.
- **Cztery dryfy na `main`** (`WEBSITES_ENABLE_APP_SERVICE_STORAGE` na teams i trzy listy
  `allowed_applications` czytane na nowo) zeszły przy `apply` tej zmiany. Nie były jej
  częścią; gdyby ktoś czytał ten `apply` później, to jest wyjaśnienie, skąd te cztery
  aplikacje w wyniku.
- **`modules/agent/.env` nie ma `TRADING_MCP_URL`** — wyszło z `preflight` przy weryfikacji.
  To stan lokalnej maszyny, nie repozytorium: lokalny agent nie widzi pozycji i nie wyśle
  zlecenia, dopóki linia nie zostanie dopisana.
