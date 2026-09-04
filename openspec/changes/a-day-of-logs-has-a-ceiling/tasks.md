## 1. Terraform

- [ ] 1.1 `infra/monitoring.tf`: `daily_quota_gb = 1` na `azurerm_log_analytics_workspace.main`, z liczbą i powodem z design.md w dwóch liniach; komentarz o „niedosięganiu 5 GB" znika
- [ ] 1.2 `azurerm_monitor_scheduled_query_rules_alert_v2` `alert-log-ingestion-capped`: zapytanie do `_LogOperation` (kategoria `Ingestion`, zatrzymanie zbierania), co 15 minut nad oknem godziny, severity 2, akcja do `ag-tradingcenter-operator`
- [ ] 1.3 `data "azurerm_subscription" "current"` i `azurerm_consumption_budget_subscription` `budget-tradingcenter`: 75 EUR miesięcznie, prognoza > 80% i rzeczywisty > 100% na `var.operator_email`, `start_date` 2026-09-01
- [ ] 1.4 `terraform fmt -check` i `terraform validate`; `terraform plan` lokalnie, żeby zobaczyć trzy dodania i jedną zmianę w miejscu, i nic więcej

## 2. Runbook

- [ ] 2.1 `docs/kiedy-produkcja-milczy.html`: nowy alert — co znaczy, że zbieranie stoi, gdzie odczytać godzinę resetu, kiedy podnieść sufit na resztę dnia ręcznie i że pozostałe alerty do resetu nic nie mówią
- [ ] 2.2 Jedno zdanie w `CLAUDE.md` przy „Things that will bite you" **tylko** jeśli sufit okaże się pułapką w praktyce; domyślnie nic, bo plik ma sufit z testem

## 3. Kolejność wdrożenia — warunek, nie notatka

- [ ] 3.1 PR #242 zmerge'owany i wdrożony (`deploy-gateway`, `deploy-market-data` zielone)
- [ ] 3.2 Następnego dnia zapytanie do `Usage` pokazuje dobowy ingest poniżej 100 MB; jeśli nie, ta zmiana czeka, a #242 wymaga poprawki
- [ ] 3.3 `terraform apply` operatora; potwierdzenie: `az monitor log-analytics workspace show` pokazuje `dailyQuotaGb: 1`, `az consumption budget list` pokazuje budżet, reguła alertu jest w grupie zasobów

## 4. Zamknięcie

- [ ] 4.1 `review.md` według szablonu, po `apply`: co zmierzono po wdrożeniu (dobowy ingest, godzina resetu), co odbiega od proposal.md
