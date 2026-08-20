## 1. Infrastruktura, która nic jeszcze nie wymaga

- [x] 1.1 Dodać `market-data` i `trading-mcp` do `allowed_applications` gatewaya w `infra/app-service.tf` (tożsamości zarządzane obu aplikacji, obok terminala)
- [x] 1.2 Sprawdzić `terraform plan` i potwierdzić, że plan nie rusza `excluded_paths` ani `unauthenticated_action`
- [ ] 1.3 `apply` lokalny operatora; potwierdzić, że oba moduły i strumień pracują dalej bez zmian

## 2. market-data przedstawia token

- [x] 2.1 W `market_data/gateway/` uzyskać token dla odbiorcy `api://tradingcenter-capital-gateway` tożsamością modułu i dołączać go do żądań REST obok klucza (wzór: `workbench/agent/tools/client.py`)
- [x] 2.2 Zostawić zestawienie WebSocketa na samym kluczu i opisać w komentarzu, dlaczego to jedyna taka trasa
- [x] 2.3 Ustawienie odbiorcy w `config.py` — brak wartości oznacza pracę lokalną i sam klucz, nie awarię
- [x] 2.6 `GATEWAY_SCOPE` i `CAPITAL_GATEWAY_SCOPE` w `infra/app-service.tf` — obie aplikacje dostają odbiorcę razem z krokiem 1, a moduł bez tej wartości pracuje jak dotąd
- [x] 2.4 Testy: żądanie REST niesie oba poświadczenia tam, gdzie jest tożsamość; sam klucz tam, gdzie jej nie ma; nieudane uzyskanie tokenu jest raportowane jako odmowa dostępu, nie jako brak danych
- [x] 2.5 `uv run pytest`, `ruff`, `pyright`

## 3. trading-mcp przedstawia token

- [x] 3.1 Dodać `azure-identity` do zależności modułu
- [x] 3.2 W `trading_mcp/client.py` dołączać token dla tego samego odbiorcy obok klucza
- [x] 3.3 Odmowa startu zostaje przy braku klucza; nieuzyskany token nie zatrzymuje modułu, bo rozstrzyga o tym gateway (design.md, "Brak tokenu nie zatrzymuje żądania")
- [x] 3.4 Sprawdzenie demo przed otwarciem portu wykonuje się już z tokenem
- [x] 3.5 Testy: obie odmowy startu, oba poświadczenia na żądaniu, `scripts/contract.py check`
- [x] 3.6 `uv run pytest`, `ruff`, `pyright`

## 4. Wdrożenie kodu i sprawdzenie przed przestawieniem drzwi

- [ ] 4.1 Wypuścić oba moduły; sondy `/health` odpowiadają
- [ ] 4.2 Potwierdzić w logach obu modułów brak ostrzeżenia "no token for …" — gateway nie może tego potwierdzić przed krokiem 5, bo przy `AllowAnonymous` nie czyta tokenu w ogóle

## 5. Drzwi zaczynają wymagać

- [ ] 5.1 `require_authentication = true` i `unauthenticated_action = "Return401"` w `auth_settings_v2` gatewaya; `excluded_paths` bez zmian
- [ ] 5.2 Komentarz przy `excluded_paths` mówi, że `/ws/stream` jest po tej zmianie jedyną trasą bronioną wyłącznie kluczem
- [ ] 5.3 `apply` lokalny operatora

## 6. Sprawdzenie na produkcji

- [ ] 6.1 Żądanie z nieważnym tokenem odbija się od platformy (`WWW-Authenticate`), a nie od modułu
- [ ] 6.2 Zakładka Konta czyta konta i pozycje
- [ ] 6.3 Terminal nadal nie sięga trasą spoza rejestru — próba dostaje odmowę uprawnienia, nie odpowiedź providera
- [ ] 6.4 Strumień świec żyje: `market-data` ma połączenie i archiwum rośnie
- [ ] 6.5 `trading-mcp` wstał, sonda `200`, narzędzie odczytu rachunku odpowiada

## 7. Prawda w plikach

- [ ] 7.1 Poprawić komentarze w `capital_gateway/caller_access.py` i w terminalowym `accountsApi.ts`, które opisują dzisiejszy, nieudany stan
- [ ] 7.2 Uzupełnić `CLAUDE.md` o postać poświadczenia zależną od miejsca — token na produkcji, klucz lokalnie i na strumieniu
- [ ] 7.3 `review.md` z pomiarem: co odpowiedziało przed przestawieniem, co po
