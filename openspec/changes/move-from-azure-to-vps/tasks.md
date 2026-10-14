Wszystko na gałęzi `infra/vps`, przebudowywanej na `main` co kilka dni. Azure działa bez zmian do grupy 9.
Kroki oznaczone **(operator)** wymagają konta, decyzji albo zgody operatora.

## 0. Decyzje i test YouTube

- [x] 0.1 **(operator)** Dostawca VPS, rozmiar (min. 4 vCPU / 8 GB / 80 GB SSD, UE), domena i układ adresów (cztery poddomeny — decyzja 17). Magazynu S3 nie ma: stan Terraform zostaje w Azure Storage, kopie ściąga komputer operatora (decyzje 9 i 18) — **14 października 2026:** OVHcloud VPS (6 vCPU, 11 GB, 96 GB, adres 57.129.181.251, AS16276), bez własnej domeny: nazwy `*.57-129-181-251.sslip.io`
- [x] 0.2 Próbny VPS: `youtube-transcript-api` na 10 filmach z obserwowanych kanałów, powtórzone po dobie; wynik zapisany tutaj (przechodzi / częściowo / blokowany) — **blokowany:** z adresu OVH 9 z 10 filmów `RequestBlocked` (`scripts/yt_ip_test.py`), z adresu domowego 9 z 10 `ok`; zostaje Gemini
- [x] 0.3 SSH dla wdrożeń: zakresy adresów GitHub Actions czy Tailscale — decyzja zapisana w `design.md` — na razie port 22 z każdego adresu, tylko klucze (`ssh_allowed_cidrs` w Ansible do zawężenia)

## 1. Uwierzytelnianie w procesie

- [x] 1.1 nowy pakiet `packages/tc-entra-auth` (decyzje 13–15): weryfikacja JWT Entra (JWKS tenanta z pamięcią i odświeżeniem przy nieznanym `kid`; `iss`, `aud`, `exp`, `nbf`); z ważnego tokenu `azp`/`appid` jako aplikacja wołająca — wejście do istniejących rejestrów (`calling_application`)
- [x] 1.2 Rozpoznanie drogi: nagłówek krawędzi → wymagany token; brak nagłówka → wymagany klucz usługi, tożsamość z klucza; `X-MS-CLIENT-PRINCIPAL*` ignorowane w trybie serwera
- [x] 1.3 `tc-mcp-kit` i klienci (`agent/tools/client.py`, `market_data/gateway/_http.py`, `trading_mcp/client.py`): bez tokenów tożsamości zarządzanej w trybie serwera, sam klucz po sieci wewnętrznej
- [ ] 1.4 Testy: nagrane prawdziwe tokeny Entra; podrobiony podpis, zły `iss`, zła audiencja, wygasły, nieznany `kid`; klucz z krawędzi odrzucony; rejestry tras bez zmian (istniejące testy zielone). **Otwarte:** nagrane prawdziwe tokeny z tenanta — testy podpisują wygenerowanym kluczem RS256; operator dostarcza parę nagranych tokenów (v1 i v2), reszta jest zrobiona

## 2. Baza w trybie serwera

- [x] 2.1 `tc-runtime` i ustawienia każdego modułu: tryb serwera (hasło roli, host z `PRIVATE_HOSTS`), odmowa dla innych hostów bez tożsamości; `scripts/dev.py` bez zmian zachowania lokalnego
- [x] 2.2 Skrypt inicjujący Postgres: osiem baz, osiem ról, każda właścicielem swojej bazy, `pg_stat_statements`
- [x] 2.3 `max_connections` 100; budżet w `test_pool_budget.py` 60; pula Telegrama 4
- [x] 2.4 Testy trybu serwera (start, odmowa hosta spoza listy, hasło poza logami)

## 3. Compose i krawędź

- [x] 3.1 `deploy/docker-compose.yml`: Caddy (jedyne `ports:`), gateway, workbench, trading-mcp, postgres; sieć `internal`; limity pamięci; `restart: unless-stopped`
- [x] 3.2 `deploy/Caddyfile`: TLS dla domeny, przekierowanie HTTP→HTTPS, nagłówek krawędzi nadpisywany, usuwanie `X-MS-CLIENT-PRINCIPAL*`, trasy do usług, pliki terminala i pocketa, `/ws/stream` z przepuszczeniem WebSocket (zamiast tego krawędź zwraca 404 — decyzja 17)
- [x] 3.3 Test w repozytorium: żadna usługa poza Caddy nie ma `ports:`; nagłówki usuwane
- [x] 3.4 Cały stos z jednego `docker compose up` na czystej maszynie (lokalnie albo na próbnym VPS)

## 4. Serwer jako kod

- [x] 4.1 `deploy/cloud-init.yaml`: użytkownik `deploy`, klucze, bez hasła i roota, Docker, Python
- [x] 4.2 `deploy/ansible/`: zapora (80/443, 22 z ograniczonych adresów), automatyczne aktualizacje bezpieczeństwa, rotacja logów Dockera, katalog `/opt/tradingcenter`, użytkownik aplikacji, cron kopii i alertów dysku
- [x] 4.3 **(operator)** Postawienie produkcyjnego VPS i zastosowanie 4.1–4.2; sprawdzenie skanem portów z zewnątrz

## 5. Wdrożenie z sondą i powrotem

- [x] 5.1 `deploy/env.required` (nazwy) i składanie `.env` z GitHub Secrets środowiska `vps`, przesyłane przez stdin, prawa 600; odmowa przy brakującej nazwie
- [x] 5.2 `.github/workflows/deploy-vps.yml` (`workflow_run` po `checks`, gałąź `infra/vps`): `deploy_gate.py` → zapamiętanie tagów → `pull` → `up -d` → `deploy_probe.py` (tag obrazu + zdrowie, przez SSH i z zewnątrz) → przywrócenie tagów i błąd przy porażce
- [x] 5.3 Klucz wdrożeniowy z `command=` w `authorized_keys` (jedno polecenie: skrypt wdrożenia)
- [x] 5.4 Terminal i pocket: build z adresami VPS, kopia `dist/` na serwer w tym samym przebiegu
- [x] 5.5 Próba: celowo zepsuty obraz zostaje sam cofnięty

## 6. Kopie zapasowe

- [x] 6.1 Nocny `pg_dump` każdej bazy do `/opt/tradingcenter/backups`, retencja 14 dni, alert przy braku zrzutu z doby (`alert.sh`); użytkownik `backup` z kluczem tylko do odczytu (`backup-serve`: `list`/`get`/`ack`); `scripts/pull-backups.ps1` dla komputera operatora; alert, gdy `ack` nie przyszedł od 3 dni
- [ ] 6.2 Próba odtworzenia z kopii z komputera operatora na świeżej maszynie; czas odtworzenia zapisany w `design.md`
- [ ] 6.3 Miesięczna próba odtworzenia w cronie, z alertem przy porażce

## 7. Dane i testy na VPS

- [x] 7.1 **(operator)** Rejestracje Entra: nowe adresy przekierowań terminala i pocketa (`azuread_*`, `terraform apply`)
- [x] 7.2 Zrzut ośmiu baz z Azure (tunel przez tymczasową regułę zapory), odtworzenie na VPS, `alembic upgrade head`, porównanie liczby wierszy — **14 października 2026:** zrzut z VPS-a (tymczasowa reguła zapory, token Entra operatora w pliku 600, usunięte po), odtworzenie bez błędów, liczby wierszy w każdej z 8 baz tabela po tabeli zgodne ze źródłem (polymarket 36,5 mln, market_data 1,18 mln), migracje bez zmian
- [x] 7.3 Start na VPS z wyłączonymi pętlami i strumieniem rynkowym (albo osobne konto demo i testowy bot) — zastąpione przez pełne okno na życzenie operatora: Azure zatrzymany przed zrzutem, więc pętle nie pracowały równolegle ani przez chwilę
- [x] 7.4 Lista dymna: zdrowie trzech aplikacji; logowanie terminala i pocketa; nieważny token → 401 z zewnątrz; wykres i strumień świec; zlecenie demo; rozmowa z agentem z narzędziami rachunku; przebieg zespołu; alert Telegram; film YouTube od dodania do oceny — operator, 14 października 2026: logowanie, wykres, zlecenie demo, agent, zespół, Telegram, YouTube działają
- [ ] 7.5 Zewnętrzny monitor dostępności trzech tras zdrowia z alertem
- [ ] 7.6 Kilka dni pracy w tle bez niespodzianek w logach; `review.md`

## 8. Przełączenie

- [x] 8.1 **(operator)** Zgoda na okno — operator, 14 października 2026
- [x] 8.2 Zatrzymanie pętli w Azure; końcowy zrzut i odtworzenie; włączenie pętli na VPS; terminal i pocket pod nowymi adresami — Azure (workbench, gateway, trading-mcp) zatrzymany 14:19 UTC, VPS pracuje od 14:26 UTC; terminal i pocket pod `*.57-129-181-251.sslip.io`
- [x] 8.3 Kilka dni obserwacji; Azure zatrzymany, nieusunięty (powrót = start Azure) — **pominięte z decyzji operatora** (14 października 2026): Azure usunięty tego samego dnia, powrót = odtworzenie z kopii, nie start Azure

## 9. Sprzątanie i merge

- [x] 9.1 Końcowy zrzut z Azure do archiwum na komputerze operatora (poza `backups/` serwera, żeby retencja go nie zjadła) — zrzuty z 14:19 UTC (Azure zatrzymany) w `Documents	radingcenter-backupszure-final-2026-10-14` na komputerze operatora, sumy SHA-256 zgodne z serwerem
- [x] 9.2 Stan Terraform zostaje w Azure Storage (`infra/bootstrap/`): korzeń `infra/` tylko z `azuread_*`, ten sam backend; sprawdzić, że `terraform.yml` dalej czyta stan (rola na koncie, OIDC) po wyłączeniu reszty — stan zostaje w Azure Storage (decyzja 9); korzeń `infra/` ograniczony do Entra
- [x] 9.3 **(operator)** `terraform destroy` zasobów Azure poza Entra i poza kontem ze stanem (`infra/bootstrap/` zostaje) — `terraform apply` planu: 77 do usunięcia, 4 zmiany, 0 nowych; rejestracje terminala, pocketa, API workbencha i gatewaya, tożsamość CI i jej dostęp do stanu zostały
- [ ] 9.4 Usunięcie trybu tożsamości bazy, Easy Auth i ścieżek `az` z kodu, workflowów i skryptów; `deploy-*.yml` Azure usunięte, `deploy-vps.yml` na `main` — **zrobione:** workflowy Azure (`deploy-*.yml`, `_deploy-app-service.yml`, `terraform-apply.yml`), `deploy_probe.py`, `enable_youtube_prod.py`, `grant-schema-ownership.sql`, skrypty skilli. **Zostaje osobną zmianą:** tryb tożsamości bazy (`DATABASE_USER`), `*_SCOPE`/`ManagedIdentityAuth`, `azure-identity`/`azure-monitor-opentelemetry` w modułach — kod martwy na serwerze, ale jego usunięcie dotyka ośmiu konfiguracji i ich testów
- [x] 9.5 `CLAUDE.md`, `docs/architecture.md`, skille `deploy-watch` i `prod-health` przepisane na VPS
- [ ] 9.6 Merge `infra/vps` do `main`; archiwum zmiany
- [x] 9.7 Jeśli 0.2 = przechodzi: osobna zmiana przywracająca dostawcę napisów YouTube przed Gemini (cofnięcie #286) — nie dotyczy: 0.2 = blokowany
