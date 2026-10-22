## 1. Przygotowanie (w repozytorium)

- [x] 1.1 `infra`: baza `youtube`, sekrety `youtube-data-api-key` i `gemini-api-key`, zmienna `youtube_enabled`, ustawienia za nią, pula Telegrama 3
- [x] 1.2 `scripts/enable_youtube_prod.py` z testami (na sucho, odmowy, zapora zamykana po błędzie, wartość poza argumentem i ekranem)
- [x] 1.3 `test_pool_budget.py` liczy pakiet YouTube; domyślna pula Telegrama zgodna z Terraform
- [ ] 1.4 `terraform plan` z `youtube_enabled=false` pokazuje tylko nową bazę i brak zmian ustawień workbencha poza pulą Telegrama

## 2. Włączenie (operator, w tej kolejności)

- [ ] 2.1 Po scaleniu `add-youtube-archive` i `youtube-transcripts-through-gemini` i zielonym wdrożeniu workbencha (`deploy-watch`)
- [ ] 2.2 `terraform apply` z `youtube_enabled=false`
- [ ] 2.3 Płatny klucz Gemini w lokalnym `.env`; `uv run python scripts/enable_youtube_prod.py` (próba), potem `--apply --gemini-key-is-paid`
- [ ] 2.4 `youtube_enabled=true` w `terraform.tfvars`, `terraform apply`
- [ ] 2.5 `deploy-watch`, potem `prod-health`: `/youtube/state` — dostawcy, sufity, wiek pętli; zmiana puli Telegrama widoczna w jego metrykach
- [ ] 2.6 Jeden kanał na liście obserwacji, jeden film przez `direct` → `gemini`; `provider_state` pokazuje blokadę `direct` z Azure
