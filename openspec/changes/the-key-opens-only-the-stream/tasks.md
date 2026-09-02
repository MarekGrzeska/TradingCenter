## 1. Drzwi bramki

- [x] 1.1 `MODULE_CALLER_APPLICATION_IDS` w `config.py`, obok listy przeglądarek; pusta znaczy nikt
- [x] 1.2 `RequireGatewayKey` → `GatewayDoor`: aplikacja rozstrzyga; klucz otwiera trasę HTTP tylko poza produkcją; `/ws/stream` bez zmian
- [x] 1.3 Testy z `GATEWAY_ENV=production`: klucz sam odmówiony, moduł z listy sięga `/orders`, przeglądarka nadal tylko rachunku; test „klucz sięga wszystkiego" zawężony do pracy lokalnej
- [x] 1.4 `uv run pytest`, `ruff`, `pyright`; `scripts/contract.py check` w trading-mcp bez zmian

## 2. Infrastruktura

- [x] 2.1 `MODULE_CALLER_APPLICATION_IDS` w bloku bramki: id `market-data` i `trading-mcp`
- [x] 2.2 `terraform fmt` i `validate`
- [x] 2.3 `apply` operatora **przed** merge — obraz, który czyta pustą listę, odmawia modułom

## 3. Prawda w plikach

- [x] 3.1 README bramki, `.env.example`, akapit o drzwiach w `CLAUDE.md`

## 4. Sprawdzenie na produkcji

- [x] 4.1 Po deployu: strumień świec żyje, `trading-mcp` odpowiada `200` na `/health`
- [ ] 4.2 Żądanie z tokenem terminala na `/orders` odbija się `403` od modułu, jak przed zmianą
