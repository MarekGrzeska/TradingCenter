## Context

Plan wysokiego poziomu i jego uzasadnienie: `docs/migracja-azure-vps-plan.html`. Ten dokument rozstrzyga, jak.
Dziś (13 października 2026): trzy App Service na planie B2, PostgreSQL Flexible B1ms z ośmioma bazami i logowaniem
tokenem Entra, Key Vault, dwie Static Web Apps, App Insights z testami dostępności i alertami, Easy Auth przed każdą
aplikacją, wdrożenia GitHub Actions przez OIDC do Azure, stan Terraform na koncie Azure Storage (`infra/bootstrap/`).

## Goals / Non-Goals

**Goals:** cały system na jednym VPS-ie dowolnego dostawcy; ta sama granica bezpieczeństwa co dziś (proces na
regułę zapisu, rejestry wołających bez zmian); wdrożenie bez ręcznej pracy, z automatycznym powrotem; kopie bazy,
które ktoś odtworzył; Azure wyłączony dopiero po testach.

**Non-Goals:** wysoka dostępność (jeden serwer, odtwarzalny z kodu i kopii, to świadomy kompromis); Kubernetes;
zmiana dostawcy logowania (Entra zostaje — D1 = B); zmiany funkcjonalne modułów.

## Decisions

**1. Weryfikacja tokenu w `tc-runtime`, przed rejestrem tras.** Easy Auth robił dwie rzeczy: odrzucał nieważny
token i podawał aplikacji oświadczenia (`X-MS-CLIENT-PRINCIPAL`). Middleware w `tc-runtime` robi obie: sprawdza
podpis kluczem z JWKS tenanta (pamięć podręczna, odświeżenie przy nieznanym `kid`), wystawcę (`iss` tenanta),
audiencję (identyfikator API aplikacji) i ważność, a z ważnego tokenu wyciąga `azp`/`appid` — tę samą wartość, którą
dziś czyta `calling_application`. Rejestry (`caller_access.py`, `root_access.py`) i ich testy zostają bez zmian.
Token nieważny → 401 przed rejestrem (wymaganie „odmowa pochodzi od warstwy uwierzytelniającej”). Alternatywa —
weryfikacja w Caddy (np. wtyczka JWT albo oauth2-proxy) — odrzucona: przenosi regułę bezpieczeństwa poza kod i
testy repozytorium, a dodatkowa usługa to dodatkowy element do wdrażania.

**2. Droga żądania rozstrzyga wymagany dowód.** Tylko Caddy publikuje porty (80/443); aplikacje i baza nie mają
portów na hoście. Caddy dopisuje każdemu żądaniu z zewnątrz nagłówek krawędzi (nadpisując, co przyszło) i usuwa
`X-MS-CLIENT-PRINCIPAL*`. Żądanie **z** nagłówkiem krawędzi MUST mieć ważny token Entra. Żądanie **bez** niego
przyszło siecią wewnętrzną Dockera, czyli od innej usługi systemu — MUST nieść klucz współdzielony, a tożsamość
wołającego bierze się z tego, który klucz przyszedł (jak dziś lokalnie). To zastępuje tokeny tożsamości zarządzanej
(`GATEWAY_SCOPE`, `CAPITAL_GATEWAY_SCOPE`), których na VPS nie ma. Alternatywa — rejestracje aplikacji z sekretem
dla każdej usługi (client credentials) — odrzucona: trzy nowe sekrety do rotacji w zamian za to, co sieć wewnętrzna
daje za darmo, i dalsza zależność usług od Entra.

**3. Trzeci tryb połączenia z bazą: „serwer”.** Dziś: lokalny (pętla zwrotna, hasło w adresie) albo tożsamość
(token Entra, TLS). Na VPS: hasło roli w adresie, host z listy `DATABASE_PRIVATE_HOSTS` (domyślnie `postgres`),
bez TLS — ruch nie opuszcza hosta, a sieć Compose jest oznaczona jako `internal`. Host spoza listy i spoza pętli
zwrotnej bez tożsamości: dalej odmowa startu. Każdy pakiet dostaje własną rolę i hasło (rola jest właścicielem
swojej bazy od początku — koniec z `grant-schema-ownership.sql`). Tryb tożsamości zostaje w kodzie do fazy 8, żeby
gałąź mogła być wdrażana na Azure i na VPS jednocześnie, i znika razem z Azure.

**4. Pula połączeń przestaje być wąskim gardłem.** Postgres na VPS ustawiamy z `max_connections` 100; budżet w
`scripts/tests/test_pool_budget.py` rośnie z 30 do 60 w tej samej zmianie (zapis: serwer jest nasz, wartość
mierzona w fazie 6). Pula Telegrama wraca do 4.

**5. Sekrety: GitHub Secrets → `.env` na serwerze.** Workflow składa `.env` z sekretów środowiska `production`
GitHub, przesyła go przez SSH (stdin, nie argument), zapisuje jako `/opt/tradingcenter/.env` z prawami 600 i
właścicielem użytkownika aplikacji. W repozytorium nie ma żadnej wartości. Lista wymaganych nazw jest w
`deploy/env.required`; workflow odmawia wdrożenia, gdy którejś brakuje — zamiast referencji Key Vault, która
zostawała dosłownym tekstem.

**6. Wdrożenie: SSH, Compose, sonda, powrót.** `deploy-vps.yml` startuje po zielonym `checks` (jak dziś,
`workflow_run`), bramka `deploy_gate.py` bez zmian. Kroki: zapamiętaj aktualne tagi obrazów → `docker compose pull`
dla obrazów z tego commita → `up -d` → sonda (`deploy_probe.py`: tag obrazu kontenera = commit **i** trasa zdrowia
200, przez SSH i z zewnątrz) → przy porażce przywróć zapamiętane tagi i `up -d`, a workflow kończy się błędem.
Migracje dalej robi każdy moduł w swoim `lifespan` pod blokadą doradczą — kolejność „ustawienia przed obrazem”
znika, bo `.env` i obraz zmieniają się w jednym kroku. SSH: klucz wdrożeniowy z ograniczeniem do jednego polecenia
(`command=` w `authorized_keys`) uruchamiającego skrypt wdrożenia; port 22 tylko z zakresów GitHub Actions i adresu
operatora, albo przez Tailscale — decyzja w fazie 2 po wyborze dostawcy.

**7. Serwer jako kod bez Terraforma dostawcy.** Dostawca nieznany (D2), więc: `deploy/cloud-init.yaml` (użytkownik,
klucze, wyłączone logowanie hasłem i roota, Docker, Python do Ansible) + `deploy/ansible/` (firewall, automatyczne
aktualizacje bezpieczeństwa, katalogi, Compose, Caddy, rotacja logów, cron kopii). Odtworzenie serwera = nowa maszyna
+ cloud-init + jedno uruchomienie Ansible + odtworzenie kopii.

**8. Terminal i pocket z tego samego Caddy.** Workflow buduje oba (`VITE_*` wskazują nowe adresy) i kopiuje `dist/`
na serwer. Jedna domena, ścieżki albo poddomeny (np. `terminal.`, `pocket.`, `api.`) — decyzja w fazie 0 razem z
domeną. Rejestracje Entra dostają nowe adresy przekierowań (Terraform `azuread_*`, `apply` operatora).

**9. Stan Terraform po Azure.** Konto Azure Storage z `infra/bootstrap/` znika z resztą. Korzeń `infra/`
ogranicza się do `azuread_*` i przenosi stan do backendu niezależnego od Azure (S3-kompatybilny magazyn, ten sam co
kopie zapasowe), z migracją `terraform init -migrate-state` **przed** `destroy`.

**10. Obserwacja.** Zewnętrzny monitor dostępności (usługa hostowana poza serwerem, darmowy plan) odpytuje trasy
zdrowia trzech aplikacji co minutę i powiadamia operatora. Na serwerze: rotacja logów Dockera, alert przy braku
nocnej kopii i przy zapełnieniu dysku (> 80%) — przez `/telegram` workbencha, który już ma adresata. App Insights i
`deploy-watch`/`prod-health` przepisane na `docker logs` i `docker stats` przez SSH.

**11. Równoległa praca dwóch stosów jest zakazana dla pętli.** Na VPS w fazach 5–6 pętle (`*_INGEST_ENABLED`,
harmonogram zespołów, strumień rynkowy, odbiór Telegrama) startują wyłączone albo na osobnym koncie demo i testowym
bocie — konto capital.com ma jeden budżet zapytań, bot jeden odbiór, a pętle płacą dostawcom i wysyłają alerty.
Przełączenie (faza 7) = zatrzymanie pętli w Azure, końcowy zrzut, odtworzenie, włączenie pętli na VPS.

**12. YouTube.** Faza 0: z próbnego VPS u wybranego dostawcy pobranie napisów 10 filmów (`youtube-transcript-api`),
powtórzone po dobie. Wynik zapisany w `tasks.md`. Przywrócenie dostawcy napisów to **osobna zmiana** po
przełączeniu (cofnięcie #286 bez zmian w bazie), bo zależy od wyniku testu, a ta zmiana nie powinna czekać.

## Risks / Trade-offs

- [Błąd w weryfikacji tokenu otwiera system] → testy na prawdziwych tokenach Entra (nagranych) i na tokenach
  podrobionych, złym `iss`, złej audiencji, wygasłych i z nieznanym `kid`; sprawdzenie z zewnątrz w fazie 6, że
  nieważny token dostaje 401, zanim cokolwiek się wykona; `review.md` obowiązkowy.
- [Ktoś wystawi port aplikacji na hoście i ominie krawędź] → test w repozytorium, który czyta `docker-compose.yml`
  i odmawia `ports:` poza Caddy; Ansible weryfikuje firewall.
- [Jeden serwer] → odtworzenie z kodu i kopii przećwiczone w fazie 4; czas odtworzenia zapisany.
- [Kopie, które nie działają] → próba odtworzenia przed przełączeniem i co miesiąc (zadanie w cronie z alertem).
- [Gałąź odjeżdża od `main`] → przebudowa co kilka dni; zamrożenie zmian w `infra/` Azure na czas migracji.
- [IP VPS też zablokowany przez YouTube] → zostaje Gemini; decyzja nie blokuje migracji.

## Migration Plan

Fazy 0–8 z `docs/migracja-azure-vps-plan.html`; zadania w `tasks.md`. Powrót do fazy 7 włącznie: start Azure
(App Service i pętle), bo Azure zostaje nieusunięty do fazy 8. Po fazie 8 powrót = odtworzenie VPS z kopii.

## Open Questions

- Dostawca VPS i rozmiar (operator; min. 4 vCPU / 8 GB / 80 GB SSD, region UE).
- Domena i układ adresów (poddomeny czy ścieżki).
- SSH dla wdrożeń: zakresy GitHub Actions czy Tailscale.
- Magazyn na kopie i stan Terraform (S3-kompatybilny, poza dostawcą VPS).
