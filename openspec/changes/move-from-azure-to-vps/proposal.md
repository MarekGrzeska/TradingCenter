## Why

Azure kosztuje nas więcej pracy, niż oszczędza. W samym październiku 2026: Easy Auth, który autoryzuje aplikację,
a nie trasę, więc każdy pakiet trzyma własny rejestr wołających; logowanie do bazy tokenem Entra i jednorazowe
nadawanie własności każdej nowej bazy; referencje Key Vault, które przy pustym sekrecie zostają dosłownym tekstem
i kładą cały proces; kolejność „ustawienia przed obrazem”, o którą potyka się każde wdrożenie; pula 30 połączeń
na bazie B1ms; i adres, któremu YouTube odmawia napisów w całości. Jeden operator, jeden system — wystarczy mu
jeden serwer, który rozumie.

Decyzje operatora (13 października 2026, `docs/migracja-azure-vps-plan.html`):
- **D1 = B**: aplikacje zostają publiczne, z logowaniem **Entra ID** (konto, które już jest; darmowe).
- **D2**: dostawcę VPS operator wybierze sam — plan i kod MUST być od dostawcy niezależne.
- **D3**: z Microsoftu zostaje tylko Entra ID (rejestracje aplikacji do logowania).

## What Changes

- **Docelowy hosting**: jeden VPS z Dockerem. Trzy procesy (`capital-gateway`, `workbench`, `trading-mcp`),
  PostgreSQL 17 z ośmioma bazami i reverse proxy z TLS (Caddy) — w Docker Compose. Terminal i pocket serwowane
  jako pliki statyczne przez to samo proxy. Obrazy dalej z GHCR.
- **Uwierzytelnianie bez Easy Auth**: weryfikację tokenu Entra (podpis z JWKS, wystawca, audiencja, ważność)
  przejmuje `tc-runtime`, w procesie, **przed** rejestrem tras — z tego samego tokenu powstaje ta sama tożsamość
  aplikacji (`azp`/`appid`), więc rejestry wołających zostają bez zmian. Nagłówki `X-MS-CLIENT-PRINCIPAL*` z
  zewnątrz są odrzucane na krawędzi.
- **Wywołania między usługami** idą siecią wewnętrzną Dockera, nie przez proxy, uwierzytelnione istniejącym
  kluczem współdzielonym; zastępują tokeny tożsamości zarządzanej. Proxy oznacza każde żądanie z zewnątrz, więc
  aplikacja wie, którą drogą przyszło.
- **Baza**: trzeci tryb połączenia — hasło własnej roli, host z jawnej listy prywatnych hostów sieci kontenerów;
  baza bez portu na zewnątrz. Tryb tożsamości Entra znika po wyłączeniu Azure.
- **Sekrety**: GitHub Secrets → plik `.env` na serwerze (właściciel aplikacja, prawa 600) przy każdym wdrożeniu;
  nic w repozytorium. Key Vault znika.
- **Wdrożenia**: GitHub Actions jak dziś (`checks` → bramka `deploy_gate.py`), potem SSH → `docker compose pull`
  i `up -d` → sonda `deploy_probe.py` (obraz z tego commita i zdrowy proces) → **automatyczny powrót do
  poprzedniego tagu**, gdy sonda nie przejdzie.
- **Serwer jako kod**: cloud-init + Ansible (bez Terraforma dostawcy — D2): użytkownik bez hasła, tylko klucze
  SSH, firewall (22 ograniczony, 80/443), automatyczne aktualizacje bezpieczeństwa, Docker.
- **Kopie zapasowe**: nocny `pg_dump` każdej bazy poza serwer, retencja, alert przy braku kopii, odtworzenie
  przećwiczone.
- **Obserwacja**: zewnętrzny test dostępności tras zdrowia i alert do operatora (Telegram/e-mail) zamiast App
  Insights; logi Dockera z rotacją.
- **Przebieg**: wszystko na gałęzi `infra/vps`; VPS wdrażany **obok** działającego Azure; testy; przełączenie;
  dopiero potem `terraform destroy` zasobów Azure (bez Entra) i merge do `main`.
- **YouTube**: test pobierania napisów z adresu VPS na starcie (faza 0). Jeśli przechodzą — osobna zmiana
  przywraca dostawcę napisów przed Gemini (kod jest w historii, #286). Jeśli nie — zostaje sam Gemini.

## Capabilities

### New Capabilities

- `vps-edge`: co stoi na krawędzi — TLS, które trasy są publiczne, oznaczanie żądań z zewnątrz, usuwanie
  nagłówków tożsamości, sieć wewnętrzna dla usług i bazy.
- `vps-deployment`: serwer jako kod, wdrożenie z sondą i powrotem, sekrety, kopie zapasowe z próbą odtworzenia.

### Modified Capabilities

- `capital-access-control`: tożsamość z tokenu weryfikowanego w procesie, nie przez platformę; wywołanie z sieci
  wewnętrznej uwierzytelnia klucz.
- `agent-database-connection`, `market-data-database-connection`: hasło własnej roli w prywatnej sieci
  kontenerów zamiast tokenu tożsamości; lista prywatnych hostów zamiast samej pętli zwrotnej.
- `production-liveness`: test dostępności spoza serwera, bez App Service; baza bez portu na zewnątrz, operator
  przez tunel SSH.

## Impact

- `packages/tc-runtime`: weryfikacja JWT Entra (JWKS z pamięcią podręczną), tryb połączenia „serwer”, rozpoznanie
  drogi żądania; `tc-mcp-kit`: tożsamość wołającego w obie strony bez tożsamości zarządzanej.
- Każdy moduł: ustawienia trybu serwera; `capital-gateway` i `trading-mcp` bez tokenów tożsamości zarządzanej.
- Nowe: `deploy/` (Compose, Caddyfile, cloud-init, Ansible, skrypty kopii), workflow `deploy-vps.yml`.
- `scripts/deploy_probe.py`: sonda także przez SSH/HTTP zamiast `az`.
- `infra/`: na koniec zostaje wyłącznie Entra (`azuread_*`), z nowym miejscem stanu Terraform — dziś stan leży
  na koncie Azure Storage, które znika.
- Terminal i pocket: nowe adresy API i przekierowania logowania (rejestracje Entra).
- Operator: domena (TLS i przekierowania Entra wymagają HTTPS na nazwie), konto VPS, magazyn na kopie, okno
  przełączenia, zgoda na `terraform destroy`.
- `CLAUDE.md`, `docs/architecture.md`, skille `deploy-watch` i `prod-health` — przepisane po przełączeniu.
- `review.md`: tak — zmiana warstwy uwierzytelniania i hostingu to najwięcej ryzyka w historii repozytorium.
