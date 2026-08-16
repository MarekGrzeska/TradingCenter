## Why

16 sierpnia 2026 produkcyjny `agent` stał ciemny: obraz z `0009_drawing_visibility` wobec
bazy na `0005`, `schema_version.py` odmawiał startu, kontener wychodził z kodem 3 w pętli.
Nic nie było zepsute — po prostu nikt nie uruchomił `alembic upgrade head`, bo nie robi tego
ani kontener, ani `deploy-agent.yml`, a smoke check tego wdrożenia czyta control plane Azure
i zaświecił się na zielono nad kontenerem, który się nie podnosił. Miesiąc wcześniej ta sama
dziura kosztowała `prompt_revisions` czytane jako `permission denied`.

Operator prosił o zautomatyzowanie tego wielokrotnie. Reguła jest już zapisana w `CLAUDE.md`
(„Migrations are never the operator's job"); ta zmiana ją spełnia.

## What Changes

- **Moduł migruje własną bazę przy starcie**, pod blokadą doradczą Postgresa
  (`pg_advisory_lock`): drugi proces czeka, zamiast ścigać się o ten sam `alembic_version`.
  To odwraca decyzję zapisaną w `Dockerfile` obu modułów — powodem odwrócenia jest blokada,
  której wtedy nie było, i cena, którą tamta decyzja okazała się mieć.
- **Migracja idzie tożsamością aplikacji**, nie administratora Entra. Tabela utworzona przez
  rolę aplikacji jest jej własnością, więc grant przestaje istnieć jako klasa problemu —
  `ALTER DEFAULT PRIVILEGES` przypięte do roli tworzącej obiekt przestaje być pułapką,
  bo tworzy zawsze ta sama rola.
- **BREAKING dla kolejności operacji:** istniejące tabele obu baz są własnością
  administratora, więc `ALTER TABLE` z roli aplikacji odmówiłby. Przed pierwszym wdrożeniem
  tej zmiany operator jednorazowo przenosi własność istniejących obiektów na rolę aplikacji
  i nadaje jej `CREATE` na schemacie. Wdrożenie kodu przed tym krokiem daje moduł, który
  nie wstaje — dokładnie ten objaw, który zmiana likwiduje, więc kolejność jest częścią
  zmiany, nie przypisem do niej.
- **`schema_version.py` zostaje** jako druga linia, nie jako jedyna. Po tej zmianie jego
  odmowa znaczy coś węższego niż dotąd: nie „nikt nie zmigrował", tylko „baza jest przed
  obrazem" — czyli wycofanie wdrożenia na starszy obraz.
- **Nieudana migracja nie wypuszcza wdrożenia**: kontener nie wstaje, probe App Service nie
  przechodzi, poprzedni kontener serwuje dalej, a workflow kończy się czerwono. Smoke check
  obu wdrożeń MUST przestać raportować zielono nad kontenerem, który się nie podniósł.
- **Oba moduły naraz** — `market-data` i `agent`. Mechanizm jest ten sam, oba mają bliźniacze
  `schema_version.py` i bliźniacze `migrations/env.py`; zrobienie jednego zostawia drugi jako
  minę o identycznym kształcie.

## Capabilities

### New Capabilities

Żadnych. Zmiana dokłada wymagania do dwóch istniejących zdolności — nie powstaje nic, czego
nie dałoby się powiedzieć o połączeniu modułu z jego bazą.

### Modified Capabilities

- `agent-database-connection`: moduł doprowadza własną bazę do rewizji, dla której został
  zbudowany, zanim zacznie odpowiadać; robi to pod blokadą wyłączną; robi to własną
  tożsamością, więc jest właścicielem tego, co tworzy; odmawia pracy, gdy nie zdołał.
- `market-data-database-connection`: to samo wymaganie, ten sam mechanizm, ta sama odmowa.

## Impact

- `modules/agent` i `modules/market-data`: `app.py` (lifespan), `db.py` (blokada doradcza),
  `migrations/env.py` (wywołanie w procesie, nie z CLI), `Dockerfile` (komentarz, który
  dziś mówi coś przeciwnego), `README.md` (sekcja o ręcznej migracji na produkcji).
- `.github/workflows/deploy-agent.yml`: smoke check, który dziś nie odróżnia żywego
  kontenera od martwego. `deploy-market-data.yml` bez zmian — ten już sięga do procesu.
- `infra/app-service.tf`: wyłączenie `/health` agenta spod Easy Auth, tym samym wzorem
  co `/ping` w `market-data` i `/health` w `market-mcp`. Bez ścieżki, która odpowiada
  przed Easy Auth, wdrożenie agenta nie ma jak zobaczyć własnego procesu.
- Produkcja, krokiem operatora wykonanym raz przed wdrożeniem: przeniesienie własności
  istniejących tabel obu baz oraz `alembic_version` na role `app-tradingcenter-agent`
  i `app-tradingcenter-market-data`, plus `GRANT CREATE ON SCHEMA public`.
- Własność i uprawnienia **wewnątrz** bazy zostają poza Terraformem, tak jak dotąd —
  nadaje je operator SQL-em, bo Terraform nie zarządza rolami w Postgresie.
- `CLAUDE.md`: sekcja „Migrations are never the operator's job" traci akapit o spłacanym
  długu, bo dług zostaje spłacony.
