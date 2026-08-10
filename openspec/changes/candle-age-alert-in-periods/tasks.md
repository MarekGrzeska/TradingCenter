## 1. Metryka w okresach

- [ ] 1.1 Wystawić `DELIVERY_GRACE` i `STALE_AFTER_PERIODS` z `tracking.py` do odczytu przez telemetrię, bez kopiowania wartości
- [ ] 1.2 Policzyć w `telemetry.py` spóźnienie w okresach: `(wiek − DELIVERY_GRACE) / period_length(resolution)`, podłogowane do zera
- [ ] 1.3 Zarejestrować `market_data.candle_age_periods` jako drugi obserwowalny gauge, z tymi samymi wymiarami `symbol` i `resolution`
- [ ] 1.4 Zostawić `market_data.candle_age_seconds` bez zmian

## 2. Testy modułu

- [ ] 2.1 Zdrowa para `MINUTE` i zdrowa para `WEEK` raportują spóźnienie poniżej jednego okresu
- [ ] 2.2 Para pominięta o tę samą liczbę okresów raportuje tę samą wartość niezależnie od rozdzielczości
- [ ] 2.3 Świeca zamknięta przed chwilą, jeszcze nieodebrana, daje zero, nie wartość ujemną
- [ ] 2.4 Para o zamkniętym rynku nie pojawia się w żadnej z dwóch metryk
- [ ] 2.5 `uv run pytest`, `uv run ruff check .`, `uv run pyright` przechodzą

## 3. Alarm

- [ ] 3.1 Przestawić `azurerm_monitor_metric_alert.candle_age` na `market_data.candle_age_periods` z progiem `3`
- [ ] 3.2 Usunąć `skip_metric_validation = true` wraz z nieaktualnym komentarzem
- [ ] 3.3 Poprawić `description` reguły — mówi dziś o dziesięciu minutach
- [ ] 3.4 Przepisać komentarz nad regułą: co znaczy jeden próg dla wszystkich rozdzielczości i skąd bierze się trzy

## 4. Wdrożenie, w tej kolejności

- [ ] 4.1 Wdrożyć `market-data`
- [ ] 4.2 Potwierdzić w Application Insights, że `market_data.candle_age_periods` ma punkty
- [ ] 4.3 `terraform apply` (operator, nie CI)
- [ ] 4.4 Sprawdzić, że `alert-candle-age-stale` zszedł ze stanu `Fired`

## 5. Dokumentacja

- [ ] 5.1 Dopisać obie metryki i ich role do README `market-data`
- [ ] 5.2 Odnotować w `docs/kiedy-produkcja-milczy.html`, że pozycja 01 jest zamknięta
