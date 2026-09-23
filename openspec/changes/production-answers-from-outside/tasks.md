## 1. Infrastruktura

- [x] 1.1 `infra/monitoring.tf`: web test z alertem dla `capital-gateway` (`/`) i `trading-mcp` (`/health`), jeden zasób `for_each`
- [x] 1.2 `infra/database.tf`: bez reguły `AllowDeveloper`; `variables.tf` i `terraform.tfvars.example` bez `developer_ip_address`
- [x] 1.3 `infra/database.tf`: `azure.extensions = PG_STAT_STATEMENTS`
- [x] 1.4 `scripts/grant-schema-ownership.sql`: reguła tymczasowa zamiast stałej, z usunięciem

## 2. Operator

- [ ] 2.1 `terraform apply` (plan: dwa web testy, dwa alerty, jedna konfiguracja serwera, jedna reguła mniej)
- [ ] 2.2 Jednorazowo, jako administrator Entra przez regułę tymczasową: `CREATE EXTENSION pg_stat_statements;` w bazie `postgres`
- [ ] 2.3 Sprawdzenie: oba web testy zielone w Application Insights, `SELECT count(*) FROM pg_stat_statements` odpowiada
