# Tasks

## 1. Moduł

- [ ] 1.1 `config.py`: `DATABASE_USER` opcjonalny; walidatory warunkowe — tryb tożsamości
      wymaga TLS i zakazuje poświadczenia w URL, tryb bez tożsamości wymaga pętli zwrotnej
- [ ] 1.2 `migrations/env.py`: bez `DATABASE_USER` migracje jadą na URL dosłownie, bez
      tożsamości
- [ ] 1.3 Testy `config.py` dla obu trybów i odmowy hosta zdalnego bez tożsamości

## 2. Środowisko lokalne

- [ ] 2.1 `compose.yaml` przywrócony z historii, nagłówek zaktualizowany
- [ ] 2.2 `.env.example`: lokalny `DATABASE_URL` z hasłem, sekcja tożsamości opisana jako
      produkcyjna
- [ ] 2.3 `scripts/dev.sh`: Docker w preflight, `docker compose up -d --wait db` przed
      migracjami, strażnik hosta zamiast nazwy bazy
- [ ] 2.4 `scripts/dev.ps1`: to samo co 2.3

## 3. Infrastruktura

- [ ] 3.1 `infra/entra.tf`: usunięty dev-SP z sekretem i outputami
- [ ] 3.2 `infra/database.tf`: usunięta baza `market_data_dev`; `infra/variables.tf` —
      komentarz o IP bez odwołania do pracy lokalnej
- [ ] 3.3 Operator: `terraform apply` (destroy SP + bazy dev) — poza tym PR, świadomie

## 4. Dokumentacja

- [ ] 4.1 `README.md` (root): sekcja o bazie lokalnej i wymaganiu Dockera
- [ ] 4.2 `modules/market-data/README.md`: sekcja Run i tabela zmiennych
- [ ] 4.3 `CLAUDE.md`: pułapka „no local database" odwrócona

## 5. Weryfikacja

- [ ] 5.1 `openspec validate local-dev-database-in-docker --strict`
- [ ] 5.2 `ruff check` + `pytest` (z testami `db`) w `modules/market-data`
- [ ] 5.3 Start stacku na kontenerze: migracje przechodzą, moduł odpowiada
