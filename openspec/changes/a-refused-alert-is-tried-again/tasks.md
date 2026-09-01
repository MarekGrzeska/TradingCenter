## 1. Decyzja niesie swój znacznik

- [x] 1.1 `notified_at` w `_DECISION_COLUMNS` i na `RecordedDecision`; kontrakt REST zostaje nietknięty, bo `_out` odwzorowuje pola po nazwie
- [x] 1.2 Test: odczyt decyzji po `mark_decision_notified` niesie znacznik, a przed nim `None`

## 2. Powtórzenie po nieudanej wysyłce powiadamia

- [x] 2.1 `is_new_setup` czyta `previous.notified_at`: ten sam kierunek jest zmianą, gdy o poprzedniej nie powiedziano
- [x] 2.2 Test: ten sam setup po odmowie bramy jest zapowiadany na następnej świecy
- [x] 2.3 Test: ten sam setup po **udanej** wysyłce dalej milczy — deduplikacja nie słabnie
- [x] 2.4 Test: brama podłączona przy stojącym wejściu zapowiada je przy pierwszym przebiegu
- [x] 2.5 Testy istniejące: `test_the_same_setup_standing_from_the_previous_bar_is_not_announced` i jego bliźniak przez pętlę dostają poprzednią decyzję **z** znacznikiem, bo to jest przypadek, który opisują

## 3. Sprawdzenie

- [x] 3.1 `uv run pytest` · `ruff check .` · `pyright` w `modules/strategy`
- [x] 3.2 `openspec validate a-refused-alert-is-tried-again --strict`
