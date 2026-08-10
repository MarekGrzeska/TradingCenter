## 1. Terraform

- [x] 1.1 W `infra/monitoring.tf`, `azurerm_monitor_metric_alert.plan_memory`: zmienić
      `threshold` z 85 na 92, zaktualizować opis alertu (`description`) o nowy próg.
- [x] 1.2 `terraform fmt` i `terraform validate` w `infra/`.
- [x] 1.3 Otworzyć PR — `terraform plan` w CI (`terraform.yml`) pokaże diff jednej wartości.

## 2. Wdrożenie

- [ ] 2.1 Po scaleniu: `terraform apply` lokalnie (operator, nie CI).
- [ ] 2.2 Potwierdzić w Azure Portal / `az monitor metric-alert show`, że
      `alert-plan-memory-high` ma `threshold = 92`.

## 3. Obserwacja

- [ ] 3.1 Porównać dołek `MemoryPercentage` z nocy 08-11 (~01:00-06:00 UTC) z dołkiem 08-10 —
      jeśli wyżej, wrócić do tematu skalowania zamiast progu (zob. `design.md`).
