## 1. Kod

- [x] 1.1 Krok dostaje wyniki poprzedników (`run_recipe(step, ctx, given)`)
- [x] 1.2 `strategy_execute`: cena wykonania przy wejściu, cena otwarcia/zamknięcia i wynik z różnicy salda przy wyjściu
- [x] 1.3 Przepis `telegram_report` w katalogu i w `runtime.py`
- [x] 1.4 Testy: tabela formatowania i milczenia, wynik wyjścia z saldem i bez zmiany salda
- [x] 1.5 README workbencha

## 2. Wdrożenie

- [ ] 2.1 Strategia 68 rewizja 2 z `keu` domyślnie 0,5 (parametry backtestu #171)
- [ ] 2.2 Zespół demo: krok `strategy_execute` → krok `telegram_report`, harmonogramy w strefie America/New_York i Europe/London
