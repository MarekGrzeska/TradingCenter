## 0. Przed zmianą kodu

- [x] 0.1 Rozstrzygnięte 15 sierpnia przez Cost Management (`az rest` na
      `Microsoft.CostManagement/query`; `az consumption usage list` oddaje tu same
      `null`, `az costmanagement` nie jest zainstalowane). Koszt faktyczny 1–15 sierpnia:
      **App Service 0,0105 €**, PostgreSQL 0,00 €, Key Vault 0,0014 €, Azure Monitor
      0,27 € — czyli największą pozycją rachunku jest monitoring, a plan B1 jest
      praktycznie darmowy. Komentarz w `app-service.tf` mówił prawdę. Decyzja nie brzmi
      więc „płacić dwa razy tyle", tylko „zacząć płacić ~24 €/mies." — przedstawiona
      operatorowi z tą liczbą i podjęta świadomie.

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

- [x] 2.1 `terraform apply -target=azurerm_service_plan.main` — 15 sierpnia 2026, ~16:30
      UTC. **Aplikacje się nie zrestartowały**, wbrew temu, co zapowiadał `design.md`;
      dowód niżej, w 3.4.
- [x] 2.2 `terraform apply` bez `-target`. Po nim `terraform plan -detailed-exitcode`
      oddaje `0` — „No changes. Your infrastructure matches the configuration".
- [x] 2.3 SKU potwierdzone: `sku B2`, `tier Basic`, `capacity 1`. Opis alertu na Azure
      zmieniony, próg dalej 92.

## 3. Sprawdzenie po wdrożeniu

- [x] 3.1 `market-data` widzi bazę: sonda `GET /ws/candles` oddaje `404 {"detail":"Not
      Found"}` z kontenera za pierwszym razem. Mocniejszy dowód niż sonda: rola
      `app-tradingcenter-market-data` ma 18 żywych połączeń w `pg_stat_activity`.
- [x] 3.2 `agent` widzi bazę: rola `app-tradingcenter-agent` ma połączenie otwarte
      16:36:10 UTC, czyli po skalowaniu. Rozmowa przez terminal zostaje do przejścia
      przez operatora — przeglądarki nie da się sprawdzić stąd.
- [ ] 3.3 `capital-gateway` ma sesję: terminal pokazuje żywe notowania. Do przejścia
      przez operatora.
- [x] 3.4 Przerwy nie było, więc nie ma dziury do sprawdzenia — i to jest samo w sobie
      wynik. `pg_stat_activity` pokazuje połączenie `market-data` otwarte 15:55:51 UTC,
      **przed** skalowaniem i wciąż żywe po nim: proces nie został zrestartowany, bo
      restart zerwałby tę sesję. Zbieranie też się nie zatrzymało — `BTCUSD MINUTE_5`
      ma 17 z 18 możliwych świec w oknie 90 minut obejmującym oba `apply`, najnowsza
      16:35. Adresy wyjściowe się nie przestawiły: 32 adresy, 32 reguły
      `AllowMarketDataOutbound`, 32 `AllowAgentOutbound`, plan czysty.

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
