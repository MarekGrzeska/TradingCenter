## Why

Po usunięciu platformy strategii (`remove-strategy-platform`) system nie ma żadnego sposobu, żeby sprawdzić
pomysł na historii. Operator chce modułu do badań, w którym silnik powstaje raz, a strategie są dokumentami
w bazie, które powstają i zmieniają się bez zmiany kodu i bez wdrożenia. Research, cztery poziomy języka i
osiem decyzji operatora z 24.10.2026: `docs/strategie/strategie-i-backtesty-research.html` (sekcje 10 i 12).

## What Changes

- Nowy, opcjonalny pakiet workbencha **`strategies`** pod `/strategies`, z własną bazą `strategies`,
  łańcuchem migracji pod kluczem blokady `8130` i ustawieniami `STRATEGIES_*`. Montowany tylko wtedy, gdy
  `STRATEGIES_DATABASE_URL` jest ustawione. Nazwa starej platformy (`strategy`) zostaje wycofana. Dlaczego,
  wyjaśnia design.md.
- **Strategia to dokument**: jeden instrument, interwał decyzji, parametry z zakresami, zmienne nazwane,
  wejścia, wyjścia, rozmiar i limity. Wewnątrz są formuły tekstowe. Dokument jest sprawdzany przy zapisie,
  a każdy zapis tworzy niezmienną rewizję.
- **Język formuł**: składnia wyrażeń Pythona parsowana bez wykonywania, z zamkniętą listą konstrukcji i
  funkcji. Wskaźniki pochodzą z katalogu `/market`. Formuła może czytać inne interwały tego samego
  instrumentu i inne instrumenty jako filtr (`close @ HOUR_4`, `close @ US500`). Przyszłości nie da się
  zapisać, a każda wartość jest widoczna dopiero od chwili, w której była dostępna.
- **Silnik backtestu**: decyzja na zamkniętej świecy interwału strategii, wypełnienia rozstrzygane na serii
  `MINUTE`, jedna pozycja naraz. Model kosztów jest obowiązkowy i ma spread z profilem godzinowym, poślizg,
  finansowanie overnight i luki. Uruchomienie to zadanie w tle z limitami.
- **Raport bez werdyktu**: wynik w R i w procentach kapitału nominalnego, transakcje z przyczyną wyjścia i
  rozbiciem kosztów oraz dwa punkty odniesienia (kup i trzymaj, losowe wejście z tymi samymi wyjściami).
  Każdy raport zapisuje, z czego powstał, tak żeby dało się go odtworzyć.
- **Złote strategie w CI**: dokumenty referencyjne z zapisanym wynikiem na zamrożonych danych. Poprawka
  silnika, która zmienia wynik, musi podnieść jego wersję.
- Pakiet **nie ma żadnej drogi do rachunku**: nie składa zleceń i nie publikuje decyzji.

**Poza zakresem:** zakładka w terminalu, edytor i agent piszący strategię z opisu (etap 2). Walk-forward,
siatka parametrów, Monte Carlo i Deflated Sharpe (etap 3). Narzędzia `/mcp`, portfel i rotacja, pętla na
żywo, nowe źródła serii (ropa, rentowności), skrypty w piaskownicy. Do etapów 2 i 3 ten pakiet jest już
właściwym miejscem, a etap 3 ma na czym liczyć, bo każde uruchomienie zostaje zapisane.

## Capabilities

### New Capabilities
- `strategies-documents`: kształt dokumentu strategii, walidacja przy zapisie, niezmienne rewizje,
  archiwizacja.
- `strategies-language`: język formuł: składnia, lista konstrukcji i funkcji, serie i przesunięcia, inny
  interwał i inny instrument, czas dostępności, zakaz przyszłości, stan pozycji.
- `strategies-backtest`: silnik: oś decyzji, zlecenia i wypełnienia na `MINUTE`, wyjścia, rozmiar, model
  kosztów, rozstrzyganie pesymistyczne, determinizm, uruchomienie jako zadanie z limitami.
- `strategies-reports`: zawartość raportu, metryki, punkty odniesienia, brak werdyktu, pochodzenie wyniku.
- `strategies-api`: kontrakt REST, dostęp wołających i ról, brak drogi do rachunku.

### Modified Capabilities
- `workbench-process`: pakiet strategii jest obecny z konfiguracji albo nieobecny.

## Impact

- `modules/workbench`: nowy pakiet `strategies/` (z `README.md`), `alembic-strategies.ini` i
  `migrations/strategies/`, montaż w `workbench/app.py`, wpis w `tests/test_layering.py`, blok
  `STRATEGIES_*` w `.env.example`. Odczyt świec i wskaźników przez REST `/market` w procesie
  (`tc_runtime.caller_access.in_process`), bez importu `market_data`.
- `scripts/dev.py` (`LOGICAL_DATABASES`, łańcuch), `scripts/tests/test_pool_budget.py`,
  `deploy/postgres/ensure-databases.sh`, `deploy/docker-compose.yml`, `deploy/env.required`
  (`STRATEGIES_DB_PASSWORD`), `deploy/scripts/backup.sh` i `backup-check.sh` (instalowane przez Ansible,
  patrz review `remove-strategy-platform`), środowisko GitHub `vps`.
- `CLAUDE.md` (tabela pakietów, klucze blokad), `modules/workbench/README.md`, `docs/architecture.md`.
- Bez zmian w kontrakcie terminala: wygenerowany kontrakt dojdzie z etapem 2.
- `review.md` powstanie po zadaniach. Zmiana wnosi nowy język interpretowany na danych od agenta i nową
  bazę na produkcji, więc zasługuje na przegląd.
