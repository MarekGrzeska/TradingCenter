## Why

Rano 9 sierpnia praca lokalna przeszła na bazę `market_data_dev` na serwerze Azure — dla
wierności produkcji. Wieczorem tego samego dnia audyt tempa pracy
(`docs/dlaczego-robi-sie-wolniej.html`) nazwał tę decyzję największym stałym podatkiem
infrastrukturalnym projektu: latencja każdej lokalnej operacji, allowlist IP do poprawienia po
każdej zmianie sieci, sekret dev-owego service principala z roczną rotacją. Operator z tej
wierności rezygnuje: tempo pracy lokalnej jest ważniejsze, a schemat i tak weryfikują testy
`db` na prawdziwym Postgresie w kontenerze.

## What Changes

**Praca lokalna wraca do bazy w kontenerze Dockera.** Produkcja zostaje dokładnie tam, gdzie
jest — App Service, tożsamość zarządzana, `market_data` na serwerze Azure — zmienia się
wyłącznie maszyna deweloperska.

- `market-data` MUST umieć połączyć się z bazą lokalną hasłem z `DATABASE_URL`, bez tożsamości
  Entra i bez TLS — ale wyłącznie z bazą lokalną: bez skonfigurowanej tożsamości moduł
  MUST NOT połączyć się z hostem innym niż pętla zwrotna. Tryb wybiera `DATABASE_USER`:
  ustawiony — tożsamość jak dotąd; pusty — hasło i tylko loopback.
- `compose.yaml` wraca (przywrócony z historii, commit sprzed `531bd04`): PostgreSQL 17 na
  porcie 55432 pętli zwrotnej, z wolumenem i healthcheckiem.
- `scripts/dev.sh` i `scripts/dev.ps1` MUST startować kontener bazy przed migracjami i MUST
  odmówić startu, gdy `DATABASE_URL` wskazuje hosta innego niż pętla zwrotna — strażnik
  przestaje pilnować nazwy bazy, zaczyna pilnować hosta.
- Z Terraforma znikają: dev-owy service principal (`sp-tradingcenter-market-data-dev` z
  sekretem i trzema outputami) i baza `market_data_dev` — oba istniały tylko dla pracy
  lokalnej. `terraform apply` wykonuje operator; skasowanie bazy jest destrukcyjne i jest
  jego świadomą decyzją przy apply.
- `.env.example`, README-y i CLAUDE.md idą za tym wszystkim.

## Capabilities

### Modified Capabilities

- `market-data-database-connection`: wymagania TLS i tożsamości zostają zawężone do bazy
  zdalnej — tam obowiązują bez zmian; dochodzi wymaganie, że praca bez tożsamości jest
  dopuszczalna wyłącznie wobec bazy na pętli zwrotnej.

## Impact

- `modules/market-data`: `config.py` (tryby połączenia), `migrations/env.py`, `.env.example`,
  `README.md`. `db.py` bez zmian — tryb bez tożsamości już istnieje, korzystają z niego testy.
- `compose.yaml` (przywrócony), `scripts/dev.sh`, `scripts/dev.ps1`.
- `infra/entra.tf`, `infra/database.tf`, `infra/variables.tf` (komentarz) — apply u operatora.
- `README.md`, `CLAUDE.md`.
- Bez zmian: capital-gateway, terminal, workflowy deploy, produkcyjna ścieżka połączenia.
