## 1. Moduł liczy pięć okien

- [x] 1.1 `changes.py`: `WINDOWS` bez 15m i 12h; `MIN_TOLERANCE` nietknięte, bo istnieje dla okna 5m
- [x] 1.2 `contract.py`: `Literal` bez dwóch wartości
- [x] 1.3 Testy zmian: pięć okien zamiast siedmiu; test, że zestaw jest jednym źródłem, nie listą przepisaną w teście
- [x] 1.4 `uv run pytest`, `ruff check .`, `pyright`

## 2. Terminal podąża za kontraktem

- [x] 2.1 `pnpm contract:generate`; `WindowName` zawęża się sam, `tsc -b` wskazuje każde miejsce zakładające siedem
- [x] 2.2 Testy terminala mówiące o siedmiu oknach — nie było takich: `WindowName` jest wyprowadzony z kontraktu, a testy używają dwóch okien przykładowo. To zasługa tamtego wyprowadzenia, nie zbieg okoliczności
- [x] 2.3 `pnpm test`, `lint`, `typecheck`, `contract:check`

## 3. Zwijanie i słupki (zwykły UI, bez wymagania)

- [x] 3.1 Wydarzenie zwija się do jednego wiersza — trzy stany, nie dwa: zwinięte, lista wyników, wyniki z oknami i wykresem
- [x] 3.2 Prawdopodobieństwo ma przedstawienie graficzne obok liczby; skala 0..1 pozostaje nazwana
- [x] 3.3 Stan zwinięcia przeżywa odświeżenie listy
- [x] 3.4 Testy: trzy stany, słupek oddaje wartość, brak ceny nie rysuje słupka o zerowej długości jako wartości
- [x] 3.5 `pnpm test`, `lint`, `typecheck`

## 4. Prawda w plikach

- [x] 4.1 README modułu i `docs/architecture.md` — bezprzedmiotowe, żaden nie wymienia liczby okien. Wymieniał ją opis narzędzia `get_price_changes`, który model czyta, i to zostało poprawione
- [ ] 4.2 `review.md`
