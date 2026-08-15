## 0. Przed zmianą kodu

- [ ] 0.1 Operator sprawdza w Cost Analysis, czy plan B1 jest dziś rozliczany, czy mieści
      się w darmowym rocznym limicie — `az consumption usage list` oddaje na tej
      subskrypcji `pretaxCost` jako `null`, więc z wiersza poleceń tego nie widać.
      To jedyna niezmierzona rzecz w tej zmianie i jedyna, która może ją odwołać
      (`design.md`, Risks).

## 1. Terraform

- [x] 1.1 `infra/app-service.tf`, `azurerm_service_plan.main`: `sku_name` z `B1` na `B2`.
- [x] 1.2 Komentarz nad zasobem planu przestaje mówić „a shared B1 plan" i „B1 fits the
      free-tier grant"; zamiast tego niesie pomiar z 15 sierpnia (dołek 83%, suma szczytów
      882 MB z 1792 MB, narzut platformy rosnący z liczbą aplikacji) i to, że
      `worker_count` zostaje 1 niezależnie od SKU.
- [x] 1.3 `infra/monitoring.tf`, `alert-plan-memory-high`: opis mówi dziś „The B1 plan
      both apps share is over 92% memory" — cztery aplikacje i nie B1. Próg 92 zostaje
      bez zmian (`design.md`, „Próg alertu zostaje na 92”).
- [x] 1.4 `terraform fmt` i `terraform validate` w `infra/`.
- [x] 1.5 Otworzyć PR — `terraform plan` w CI (`terraform.yml`). **Wynik: PR #94,
      `Plan: 0 to add, 12 to change, 0 to destroy`, bez błędu.** Widoczne dokładnie dwie
      zamierzone zmiany (`sku_name B1 -> B2`, opis alertu). Reguł `market_data_outbound`
      i `agent_outbound` w diffie **nie ma** — Terraform czyta adresy wyjściowe ze stanu
      jako wartość znaną i nie wie, że Azure je przestawi. `design.md` poprawione: to
      czyni zadanie 2.2 ważniejszym, nie mniej ważnym. Pozostałe dziesięć pozycji
      w planie to szum providera bez widocznej różnicy, obecny przed tą zmianą.

## 2. Wdrożenie (operator, nie CI)

- [ ] 2.1 Po scaleniu: `terraform apply -target=azurerm_service_plan.main`. Cztery
      aplikacje restartują się w trakcie.
- [ ] 2.2 `terraform apply` bez `-target` — reguły firewalla bazy i `ip_restriction`
      gatewaya zbiegają się do nowych adresów wyjściowych planu.
- [ ] 2.3 Potwierdzić SKU: `az appservice plan show --name asp-tradingcenter
      --resource-group rg-tradingcenter --query "sku"` pokazuje `B2`.

## 3. Sprawdzenie po wdrożeniu

- [ ] 3.1 `market-data` widzi bazę: `GET /ws/candles` na wdrożonej aplikacji oddaje 404
      z ciałem JSON modułu (ta sama sonda, której używa `deploy-market-data.yml`), a
      `Data History` w terminalu pokazuje, że zbieranie ruszyło dalej.
- [ ] 3.2 `agent` widzi bazę: rozmowa w terminalu odpowiada, a `Agents cost` pokazuje
      wiersz zużycia z tej tury.
- [ ] 3.3 `capital-gateway` ma sesję: terminal pokazuje żywe notowania, a nie ostatnią
      świecę sprzed restartu.
- [ ] 3.4 Sprawdzić, że w oknie między 2.1 a 2.2 przerwa w zbieraniu zapisała się jako
      dziura w `coverage_ranges`, a nie jako cisza rynku — to jest test tego, że moduł nie
      skłamał o tym, czego nie zebrał.

## 4. Obserwacja

- [ ] 4.1 Po tygodniu odczytać dołek nocny `MemoryPercentage` planu (01:00–06:00 UTC) i
      porównać z przewidywanymi ~40%. Rozjazd w górę oznacza, że narzut platformy nie
      skaluje się tak, jak założono w `proposal.md`.
- [ ] 4.2 Odczytać `MemoryWorkingSet` czterech aplikacji z tego samego tygodnia. Jeśli
      któraś rośnie mimo restartu z 2.1, to dopiero wtedy jest to wyciek — i wtedy jest
      to osobna zmiana, z zapasem 2 GB na jej zdiagnozowanie.
- [ ] 4.3 Dopiero mając 4.1, zdecydować o progu alertu. Osobna zmiana, z pomiarem.

## 5. Domknięcie

- [ ] 5.1 `openspec validate scale-app-service-plan-to-b2 --strict` — **oczekiwany błąd**
      „Change must have at least one delta". CLI 1.6.0 nie honoruje `skip_specs: true` przy
      `--strict`, co dotyczy każdej zmiany bez delt w tym repozytorium
      (`archive/2026-08-09-slim-market-data-app`, `.../checks-run-before-a-merge`,
      `.../generate-terminal-contract-from-openapi`, `.../raise-memory-alert-threshold`).
      Nie zaspokajać tego wymyślonym wymaganiem — spec opisuje zachowanie, a zachowanie
      się nie zmienia.
- [ ] 5.2 `review.md` przed archiwizacją
