## Why

Przegląd z 23 września 2026 (`docs/przeglad-2026-09-23.html`, P9) policzył, co produkcja mówi o sobie
na zewnątrz. Jeden web test — `/market/ping` workbencha — i ani jednego `health_check_path`. Śmierć
`capital-gateway` wychodzi tylko pośrednio, przez alert wieku świec, a śmierć `trading-mcp` nie wychodzi
wcale, dopóki operator nie zapyta agenta o pozycje. Po etapie 4 `one-process-per-security-boundary`
aplikacje są trzy, więc brakuje dwóch testów, nie trzech.

Druga rzecz to drzwi bazy. Stała reguła `AllowDeveloper` wpuszcza adres, który operator miał kiedyś:
przegląd zastał w niej nieaktualne IP, czyli regułę, która nic nie daje, a zostaje otwarta dla kogoś,
kto ten adres dostanie po nim. Pomiar T4 w tym samym przeglądzie pokazał drogę, która wystarcza: reguła
tymczasowa na bieżący adres, usuwana na końcu sesji (`.claude/skills/system-review/scripts/t4.sh`).

Trzecia to przypisanie obciążenia bazy. Żeby ustalić, że 97% transakcji pochodzi z jednej linii, trzeba
było dwóch odczytów `pg_stat_*` przez tymczasową regułę firewalla, a i tak tylko do poziomu tabel.
`pg_stat_statements` jest ładowane przez serwer, ale nie dozwolone (`azure.extensions` jest puste), więc
następny przegląd nie widzi zapytań.

To zmiana OpenSpec, bo dotyka `infra/**`.

## What Changes

- **Dwa web testy dostępności** z alertem, wzorem `market_data_ping`: `capital-gateway` na `/`
  i `trading-mcp` na `/health` — obie ścieżki już są wyłączone z Easy Auth i niczego nie czytają.
  Jeden zasób z `for_each`, nie dwie kopie; istniejący test `/market/ping` zostaje pod swoją nazwą, bo
  zmiana nazwy odtworzyłaby test i alert.
- **Bez stałej reguły `AllowDeveloper`** i bez zmiennej `developer_ip_address`. Dostęp operatora do bazy to
  reguła tymczasowa, zakładana i usuwana w tej samej sesji; `scripts/grant-schema-ownership.sql` mówi jak.
- **`azure.extensions = PG_STAT_STATEMENTS`** na serwerze. `CREATE EXTENSION` w bazie `postgres` jest
  jednorazowym krokiem operatora (rola aplikacji nie może tworzyć rozszerzeń); od tej chwili przegląd czyta
  zapytania zamiast tabel.
- **Nowa zdolność `production-liveness`**: każda aplikacja App Service jest sprawdzana z zewnątrz, a baza
  nie ma stałej reguły dla adresu człowieka.

## Capabilities

### New Capabilities
- `production-liveness`: co z zewnątrz mówi, że aplikacja żyje, i czyje adresy baza wpuszcza na stałe.

## Impact

- `infra/monitoring.tf`, `infra/database.tf`, `infra/variables.tf`, `infra/terraform.tfvars.example`,
  `scripts/grant-schema-ownership.sql`.
- Apply operatora. Po nim jednorazowo: `CREATE EXTENSION pg_stat_statements;` w bazie `postgres`,
  jako administrator Entra, przez regułę tymczasową.
- `design.md` pominięty: każda decyzja ma tu jedno zdanie powodu i nie ma alternatywy wartej opisania.
