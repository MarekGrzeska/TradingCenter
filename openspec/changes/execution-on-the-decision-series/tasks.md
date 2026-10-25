## 0. Kolejność

- [x] 0.1 Zarchiwizować `a-trade-held-through-the-session` (jest wdrożona), bo ta zmiana modyfikuje jej wersję
  „Raport mówi, z czego powstał”.

## 1. Seria wykonania

- [x] 1.1 Funkcja serii wykonania z dokumentu (D1), test jednostkowy na każdy rodzaj poziomu, który przełącza na `MINUTE`.
- [x] 1.2 `requirements.needs`: `MINUTE` tylko wtedy, gdy seria wykonania to `MINUTE`.
- [x] 1.3 `engine.simulate`: pętla wykonania na serii wykonania (D2); `ENGINE_VERSION` 4.
- [x] 1.4 Złoty plik nagrany pod wersją 4; żaden wynik się nie ruszył, także `session_without_a_stop`, który wykonuje się
  teraz na M5. Równość transakcji na obu seriach sprawdza osobny test silnika (strategia z nieosiągalnym stopem).
- [x] 1.5 Test: strategia bez poziomów bez żadnej serii `MINUTE` daje transakcję każdego dnia sesji.

## 2. Brak minut i limit

- [x] 2.1 `queue._prepare`: świece decyzji bez minut przy serii `MINUTE` kończą uruchomienie z przyczyną (liczba, trzy
  pierwsze luki, pierwsza minuta), zanim cokolwiek się policzy (D3); test z dziurą i test z jedną brakującą minutą.
- [x] 2.2 `check_request` liczy świece serii wykonania; `max_minute_bars` → `max_execution_bars` w ustawieniach, trasach,
  narzędziu i `.env.example`; stara nazwa w `RETIRED_SETTINGS`.

## 3. Raport i kontrakt

- [x] 3.1 `provenance.execution` zapisywane w kolejce i oddawane przez `read_backtest`.
- [x] 3.2 `reports.daily_equity` i `buy_and_hold` na serii wykonania (D4).
- [x] 3.3 `RevisionOut.execution` i `HealthOut.max_execution_bars` w `contract.py`; skill `contract-sync`.
- [x] 3.4 `RunForm.tsx`: świece serii wykonania z nazwą serii wobec sufitu; test zakresu ponad sufit na `MINUTE` i
  dziesięciu lat na M5.

## 4. Dokumentacja i zamknięcie

- [x] 4.1 `strategies/README.md`: seria wykonania, sprawdzenie minut, podłoga kapitału na M5 (ryzyko z design.md).
- [ ] 4.2 Po wdrożeniu: ponowić backtest US100 M5 od 1.01.2026 i sprawdzić, że ma transakcję w każdy dzień sesji.
- [x] 4.3 `review.md` po angielsku według szablonu.
