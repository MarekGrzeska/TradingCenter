## Verdict

Wdrożone: moduły zwinięte do procesów wyznaczonych granicą bezpieczeństwa — workbench jako jeden proces z pakietami,
które się nie importują, `capital-gateway`, `trading-mcp`; reguła i trzy warunki współdzielenia źródeł w
`docs/architecture.md` i `CLAUDE.md`, pilnowane testem warstw.

Świadomie niedokończone i już nieaktualne: 5.2 (`DROP ROLE` dla `app-tradingcenter-telegram-gateway` i
`app-tradingcenter-teams` w Azure PostgreSQL) — 14 października 2026 produkcja przeszła na VPS, a zasoby Azure poza
Entra i stanem Terraform zostały usunięte razem z tą bazą, więc ról nie ma do usunięcia.

## Verified

- Przy archiwizacji tylko stan repozytorium: `modules/workbench/tests/test_layering.py` i `workbench/assembly.py` są tym,
  co zmiana opisała. Bramki pomiarowe z `tasks.md` zostały zapisane przy ich wykonaniu (historia `tasks.md` w git);
  w tym przebiegu nie były powtarzane.

## Gaps

- Liczby z każdej bramki nie zostały zebrane w tym pliku — są w historii `tasks.md` i w `docs/` („Trzy procesy zamiast ośmiu”).
