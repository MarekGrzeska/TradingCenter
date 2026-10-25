## 1. Brama i archiwum

- [x] 1.1 `InstrumentTerms` w `capital_gateway/dtos.py` i `mapping.py`: `overnight_long_rate`, `overnight_short_rate`, `overnight_rate_unit`, `overnight_charge_at`, `overnight_charge_interval_minutes` z `instrument.overnightFee`; test na `market_gold.json` i `market_sparse.json` (brak pola = null)
- [x] 1.2 Na demo (`-m live --run-live`): warunki US100, EURUSD, GOLD i BTCUSD — czy pole jest, i znak/jednostka stawek wobec opłaty w historii transakcji konta; wynik w design.md D3
- [x] 1.3 Skill `contract-sync`: snapshot OpenAPI bramy w `trading-mcp`
- [x] 1.4 `market_data`: `GET /instruments/{symbol}/terms` jako proxy (`gateway/instruments.py`, `routers/instruments.py`, rekord wołających); test, że kształt przechodzi bez zmian i że odmowa bramy nie jest pustym wynikiem

## 2. Pakiet strategii

- [x] 2.1 Migracja `0003`: `cost_profiles.source`, `fetched_at`, `broker`; `strategies.conversation_id`
- [x] 2.2 `broker_costs.py`: spread z `search` (dokładny symbol), finansowanie i godzina z `terms` (D3), odmowa z nazwą brakującej wartości; testy jednostkowe przeliczenia na nagraniu
- [x] 2.3 `archive.py`: odczyt `search` i `terms` przez `/market`; `POST /costs/{symbol}/from-broker`; źródło, chwila i surowe wartości w `CostProfileOut`
- [x] 2.4 `RunIn.costs` opcjonalne i `without_costs`; rozstrzygnięcie źródła przy kolejkowaniu (żądanie → profil → pobranie od brokera), `costs_source` w `request`, odmowa „koszty i bez kosztów naraz”
- [x] 2.5 `ReportOut.costs_source` i `without_costs` (z `request`), `headline` z oznaczeniem bez kosztów
- [x] 2.6 `run_backtest`: bez odmowy z braku profilu, `without_costs`, koszty i ich źródło w odpowiedzi; opis narzędzia; sufit powierzchni
- [x] 2.7 Testy: pierwsze uruchomienie pobiera profil (`-m db`, sztuczne archiwum), brak finansowania = odmowa bez profilu, broker nie odpowiada = profil bez zmian
- [x] 2.8 `PUT /strategies/{id}/conversation` i `conversation_id` w `StrategyOut`; test, że przypisanie nie tworzy rewizji

## 3. Terminal

- [x] 3.1 Skill `contract-sync`: kontrakty strategii i archiwum
- [x] 3.2 Formularz: koszty od brokera bez wpisywania (pobranie przy braku profilu), źródło i chwila, „Odśwież z capital.com”, przełącznik „bez kosztów” z ostrzeżeniem
- [x] 3.3 Raport i lista uruchomień: oznaczenie „bez kosztów” i źródło kosztów
- [x] 3.4 `Transcript` i `Composer` z `AgentChat.tsx` jako wspólne komponenty; `StrategyChat` w oknie tworzenia na własnej instancji `createAgentChatStore(null, …)` z kontekstem strategii
- [x] 3.5 Rozmowa strategii: otwarcie wczytuje `conversation_id`, nowa strategia zaczyna pustą, po zapisie przez agenta przypisanie (`PUT …/conversation`), tytuł rozmowy = nazwa strategii
- [x] 3.6 Testy: formularz bez profilu pokazuje koszty od brokera; czat strategii wysyła z kontekstem i nie zmienia rozmowy panelu; nowa strategia z czatu dostaje przypisaną rozmowę; raport bez kosztów oznaczony

## 4. Dokumentacja i wdrożenie

- [x] 4.1 `strategies/README.md` (koszty od brokera, „bez kosztów”, ścieżka zarchiwizowanego etapu 2), README bramy i archiwum
- [ ] 4.2 Po merge skill `deploy-watch`; pierwszy backtest z kosztami od brokera na produkcji
- [ ] 4.3 `review.md`
