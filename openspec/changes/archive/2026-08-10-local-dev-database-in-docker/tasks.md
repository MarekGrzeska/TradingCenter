# Tasks

## 1. Moduł

- [x] 1.1 `config.py`: `DATABASE_USER` opcjonalny; walidatory warunkowe — tryb tożsamości
      wymaga TLS i zakazuje poświadczenia w URL, tryb bez tożsamości wymaga pętli zwrotnej
- [x] 1.2 `migrations/env.py`: bez `DATABASE_USER` migracje jadą na URL dosłownie, bez
      tożsamości
- [x] 1.3 Testy `config.py` dla obu trybów i odmowy hosta zdalnego bez tożsamości

## 2. Środowisko lokalne

- [x] 2.1 `compose.yaml` przywrócony z historii, nagłówek zaktualizowany
- [x] 2.2 `.env.example`: lokalny `DATABASE_URL` z hasłem, sekcja tożsamości opisana jako
      produkcyjna
- [x] 2.3 `scripts/dev.sh`: Docker w preflight, `docker compose up -d --wait db` przed
      migracjami, strażnik hosta zamiast nazwy bazy
- [x] 2.4 `scripts/dev.ps1`: to samo co 2.3

## 3. Infrastruktura

- [x] 3.1 `infra/entra.tf`: usunięty dev-SP z sekretem i outputami
- [x] 3.2 `infra/database.tf`: usunięta baza `market_data_dev`; `infra/variables.tf` —
      komentarz o IP bez odwołania do pracy lokalnej
- [x] 3.3 Operator: `terraform apply` (destroy SP + bazy dev) — poza tym PR, świadomie

## 4. Dokumentacja

- [x] 4.1 `README.md` (root): sekcja o bazie lokalnej i wymaganiu Dockera
- [x] 4.2 `modules/market-data/README.md`: sekcja Run i tabela zmiennych
- [x] 4.3 `CLAUDE.md`: pułapka „no local database" odwrócona

## 5. Weryfikacja

- [x] 5.1 `openspec validate local-dev-database-in-docker --strict`
- [x] 5.2 `ruff check` + `pytest` (z testami `db`) w `modules/market-data`
- [x] 5.3 Start stacku na kontenerze: migracje przechodzą, moduł odpowiada
