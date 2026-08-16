## 1. Blokada i migracja w module agenta

- [x] 1.1 `agent/db.py`: kontekst blokady doradczej na `pg_try_advisory_lock` w pętli, ze stałym kluczem i kresem czekania, zwalniający blokadę także po błędzie
- [x] 1.2 `agent/migrate.py`: `command.upgrade(config, "head")` w wątku roboczym, `Config` budowany w pamięci ze ścieżką do `migrations/` wyliczoną z `__file__`
- [x] 1.3 `agent/config.py`: ustawienie z kresem czekania na blokadę, domyślnie 5 minut
- [x] 1.4 `agent/app.py`: wywołanie w `lifespan` przed `verify`, przed wpuszczeniem ruchu
- [x] 1.5 Testy jednostkowe: kres czekania zwraca odmowę, błąd migracji zwalnia blokadę
- [x] 1.6 Testy `-m db`: pusta baza dochodzi do głowy; baza na głowie nie wykonuje zapisu; dwa równoległe starty migrują raz
- [x] 1.7 `uv run ruff check .`, `uv run pyright`, `uv run pytest -m db`

## 2. To samo w market-data

- [x] 2.1 `market_data/db.py`: bliźniak blokady z 1.1, własna wartość klucza
- [x] 2.2 `market_data/migrate.py`: bliźniak 1.2
- [x] 2.3 `market_data/config.py`: kres czekania, domyślnie 30 minut
- [x] 2.4 `market_data/app.py`: wywołanie w `lifespan` przed `verify` i **przed startem zbierania**
- [x] 2.5 Testy jednostkowe i `-m db` jak w 1.5–1.6, plus: zbieranie nie rusza przed końcem migracji
- [x] 2.6 `uv run ruff check .`, `uv run pyright`, `uv run pytest -m db`

## 3. Komentarze i dokumentacja, które dziś mówią coś przeciwnego

- [x] 3.1 `modules/agent/Dockerfile` i `modules/market-data/Dockerfile`: komentarz o `CMD` — powodem odwrócenia jest blokada, nie zmiana zdania
- [x] 3.2 `modules/agent/README.md`, `modules/market-data/README.md`: sekcja o ręcznej migracji na produkcji znika; zostaje lokalne `alembic upgrade head` i zdanie o tym, że produkcja migruje sama
- [x] 3.3 `agent/schema_version.py`, `market_data/schema_version.py`: docstring mówi teraz, czego ten check pilnuje po zmianie
- [x] 3.4 `CLAUDE.md`: akapit o spłacanym długu znika z sekcji „Migrations are never the operator's job"

## 4. Infrastruktura i wdrożenie

- [x] 4.1 `infra/app-service.tf`: `excluded_paths = ["/health"]` w `auth_settings_v2` agenta, z komentarzem wskazującym na bliźniacze wyłączenia
- [x] 4.2 `infra/app-service.tf`: `WEBSITES_CONTAINER_START_TIME_LIMIT` dla `market-data` powyżej jego kresu blokady
- [x] 4.3 `.github/workflows/deploy-agent.yml`: smoke check pyta `/health` zamiast czytać stan site'u
- [x] 4.4 `terraform plan` na PR przechodzi i nie dotyka `azuread_*`

## 5. Krok operatora na produkcji, wykonywany raz

- [x] 5.1 `scripts/grant-schema-ownership.sql`: przeniesienie własności wszystkich tabel, sekwencji i widoków schematu `public` oraz `alembic_version` na wskazaną rolę, plus `GRANT CREATE ON SCHEMA public`
- [x] 5.2 Zapytanie kontrolne w tym samym pliku: obiekty, których właścicielem nie jest rola aplikacji — MUST zwrócić zero wierszy
- [ ] 5.3 Wykonanie na bazie `agent` i sprawdzenie kontrolne
- [ ] 5.4 Wykonanie na bazie `tradingcenter` i sprawdzenie kontrolne

## 6. Wdrożenie i potwierdzenie

- [ ] 6.1 `terraform apply` ręką operatora (4.1, 4.2)
- [ ] 6.2 Merge agenta; wdrożenie kończy się zielono, `/health` odpowiada, log niesie linię o rewizji
- [ ] 6.3 Merge `market-data` po tym, jak agent przeżył; to samo potwierdzenie
- [ ] 6.4 Przejście ręką: migracja na testowej rewizji celowo zepsutej — wdrożenie MUST skończyć się czerwono, a poprzednia wersja MUST serwować dalej
- [ ] 6.5 `review.md`
