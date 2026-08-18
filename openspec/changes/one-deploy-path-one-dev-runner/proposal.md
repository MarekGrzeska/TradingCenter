## Why

Iteracja 2 planu refactoru (`docs/plan-refactoru.html`). Iteracja 1 zamknęła ręczne kopie
Pythona; ta zamyka kopie w warstwie, przez którą kod dojeżdża na produkcję i przez którą
wstaje lokalnie. Rachunek zmierzony 18 sierpnia 2026, nie oszacowany:

- **Siedem workflow wdrożeniowych App Service to 458 linii kodu** (bez komentarzy), a diff
  dowolnych dwóch z nich to ten sam zestaw podstawień. Zmiana bloku OIDC, wersji buildx czy
  kształtu sondy to siedem ręcznych edycji, których nic nie pilnuje — i dokładnie tak
  rozjechały się sondy: lekcja z 16 sierpnia (kontener wstaje, control plane mówi `Running`)
  weszła do dwóch workflow z siedmiu, a pozostałe pięć dostało ją ręcznie w iteracji 0.
- **`dev.sh` 496 + `dev.ps1` 647 = 1 143 linie jednej logiki napisanej dwa razy.** Iteracja 0
  naprawiła trzeci udokumentowany dryf tej pary (`dev.ps1` startował `teams-mcp` i gubił go
  z nadzoru) — reaktywnie, jak dwa poprzednie. 100% dotychczasowego dryfu siedzi w tabeli
  serwisów, nie w platformowej hydraulice procesów.
- **Push prosto na `main` z Terraformem nie przechodzi żadnej walidacji.** `terraform.yml`
  ma wyłącznie wyzwalacz `pull_request`, a `checks.yml` nie zna ścieżki `infra/**`.
- **~300 linii mechanicznego Terraforma**: tryplet rejestracji Easy Auth ×6 (rozrzucony
  między `app-service.tf` i `entra.tf`), polityki Key Vault ×7.
- **Liczebniki wpisane ręcznie w 11 miejscach** `infra/*.tf`. Audyt udowodnił nieprawdziwość
  m.in. treści e-maila alertu pamięci („The plan all four apps share…" przy siedmiu), na
  której stoi udokumentowana procedura decyzji o SKU.

Ta iteracja jest też wejściem iteracji 6: szablon nowego modułu nie ma czego generować,
dopóki wdrożenie modułu to 65 linii własnego workflow i dwa bloki w dwóch skryptach dev.

## What Changes

**Jedna droga wdrożenia**

- Nowy `.github/workflows/_deploy-app-service.yml` (`workflow_call`) z wejściami:
  `module`, `image_name`, `app_name`, `build_context`, `dockerfile`, `probe_path`,
  `expected_status`, `body_contains`, `attempts`.
- Siedem `deploy-*.yml` staje się wywołującymi po ~15 linii: wyzwalacz, filtr ścieżki,
  `concurrency`, `with:`. Komentarze-incydenty (16 sierpnia w `deploy-agent.yml`, powód
  demo-checku w `deploy-trading-mcp.yml`) zostają **u wywołujących** — to najcenniejsza
  treść tych plików i nie ma jej gdzie zmieścić we wspólnym.
- **Sonda to jedna pętla, nie trzy kształty.** Pomiar poprawia tu plan i audyt: siedem sond
  różni się czterema parametrami, nie trzema wariantami. `capital-gateway` to `probe_path`
  puste (tylko control plane, bo brama nie wpuszcza runnera), `agent`/`teams` to `/health`
  200 z 20 próbami (ich `lifespan` czeka na migrację), trzy moduły MCP to `/health` 200 z
  ciałem zawierającym `"status"`, `market-data` to `/ws/candles` 404 z ciałem zawierającym
  `"detail"`.
- **Asercja ciała odpowiedzi obejmuje wszystkie siedem.** Znalezisko nieopisane w audycie:
  `agent` i `teams` przyjmują dziś samo 200, gdy trzy moduły MCP sprawdzają 200 **i** ciało.
  Po parametryzacji sprawdzenie ciała jest darmowe, więc odpowiedź nie z kontenera przestaje
  móc przejść w dwóch workflow, w których dziś może.

**Jeden runner dev**

- Nowy `scripts/dev.py` — jedna implementacja. Tabela serwisów (nazwa, katalog, port,
  komenda, ścieżka health, kolejność, powód kolejności) jako **dane w jednym miejscu**.
- `dev.sh` i `dev.ps1` kurczą się do cienkich wrapperów przekazujących flagi
  (`--no-terminal` / `-NoTerminal`), więc nawyki, `README.md` i `CLAUDE.md` dalej działają.
- Przenoszone bez zmiany zachowania, bo każde z nich powstało z awarii: porównanie
  `CAPITAL_GATEWAY_API_KEY` z `GATEWAY_API_KEY` przed startem czegokolwiek, odmowa dla
  `DATABASE_URL` spoza loopbacku, tworzenie brakujących roli i baz `agent`/`teams`,
  ostrzeżenie o braku `MARKET_MCP_URL` / `TRADING_MCP_URL` / `TEAMS_MCP_URL`, nadzór nad
  wszystkimi ośmioma procesami, sprzątanie po sobie.
- Proza opisująca kolejność startu (`trading-mcp` wychodzi, gdy brama nie odpowiada;
  `teams` przed `teams-mcp`) jedzie razem z wierszami tabeli, w polu, nie w komentarzu obok.

**CI**

- `checks.yml`: job `infra` dla ścieżki `infra/**` — `terraform fmt -check` i
  `terraform validate` (bez `init` z backendem, więc bez poświadczeń i bez blokady stanu).
- `checks.yml`: blok translacji nazw (12 linii `case`, istniejący tylko dlatego, że nazwa
  zmiennej w bashu nie zniesie łącznika) zastąpiony tablicą asocjacyjną — wzorce w jednym
  miejscu, bez drugiego wykazu nazw obok pierwszego.

**Terraform, chirurgicznie**

- Moduł lokalny `infra/modules/easy-auth-app/` — tryplet `azuread_application` +
  `azuread_service_principal` + `azuread_application_password` ×6, z blokami `moved`.
- `for_each` dla siedmiu `azurerm_key_vault_access_policy`.
- Bloki siedmiu `azurerm_linux_web_app` **zostają jawne** — różnią się naprawdę, a połowa
  `app-service.tf` to datowane komentarze incydentów, których `for_each` nie udźwignie.
- Liczebniki wyliczane z `local` (`length(local.web_app_names)`), nie wpisywane — w treści
  alertu i w komentarzach.

## Capabilities

### New Capabilities

Brak. Ta zmiana nie dodaje żadnemu modułowi zachowania.

### Modified Capabilities

Brak. Żadne wymaganie w `openspec/specs/` nie zmienia się: specyfikacje w tym repo opisują,
co moduł robi, publikuje i czego odmawia, a nie jak jego obraz dojeżdża na produkcję ani jak
stack wstaje lokalnie. Kryterium akceptacji jest tożsamość zachowania: obraz zbudowany z tych
samych plików, sonda pytająca o to samo lub więcej, stack startujący w tej samej kolejności,
plan Terraforma bez ani jednego `add`, `destroy` i `change`.

Zmiana ma więc `skip_specs: true` w `.openspec.yaml` i kwalifikuje się do OpenSpeca przez
**kategorię 3** wyzwalacza — infrastruktura (`infra/**`).

`review.md` powstanie po wdrożeniu, nie teraz: to jest zmiana z ryzykiem stanu Terraforma i
z siedmioma sondami do sprawdzenia, więc jest o czym pisać, ale dopiero po pomiarze.

## Impact

**Pliki**

- `.github/workflows/_deploy-app-service.yml` (nowy), `deploy-{agent,gateway,market-data,market-mcp,teams,teams-mcp,trading-mcp}.yml` (7 przepisanych; `deploy-terminal.yml` nietknięty — Static Web App, nie App Service, i nie jest wywołującym).
- `scripts/dev.py` (nowy), `scripts/dev.sh`, `scripts/dev.ps1` (wrappery).
- `.github/workflows/checks.yml`.
- `infra/modules/easy-auth-app/` (nowy), `infra/app-service.tf`, `infra/entra.tf`,
  `infra/monitoring.tf`, `infra/github-oidc.tf`, `infra/key-vault.tf`.
- `CLAUDE.md`, `README.md` — tam, gdzie opisują skrypty dev i kształt wdrożenia.

**Krok operatora, jeden i nieusuwalny.** `terraform-apply.yml` odmawia planu ruszającego
`azuread_*`, bo CI ma `Application.Read.All`, nie write. Moduł `easy-auth-app` przenosi w
stanie sześć `azuread_application_password`, więc **plan aplikuje operator lokalnie**, a
zadanie nie jest zrobione, dopóki ten plan nie powie `0 to add, 0 to change, 0 to destroy`.
Plan pokazujący `destroy` + `create` zamiast `moved` znaczy sześć rotacji sekretu Easy Auth,
czyli sześć aplikacji odrzucających każdy token do ręcznej naprawy — to jest największe
ryzyko tej iteracji i `design.md` opisuje, jak jest bramkowane.

**Bez zmian**: granice runtime między modułami, kontrakty, tożsamości, osobne bazy, siedem
osobnych lockfile'ów, `.dockerignore` i kontekst builda z iteracji 1, demo-check
`trading-mcp`, migracje w `lifespan` pod advisory lockiem.
