Wchodzi po `add-technical-indicators`. Każdy etap kończy się zielonym `uv run pytest`,
`uv run ruff check .`, `uv run pyright` w `market-data` oraz `pnpm test`, `pnpm lint`,
`pnpm typecheck`, `pnpm contract:check` w terminalu.

## 1. Kontrakt

- [ ] 1.1 `market_data/contract.py`: `error: str | None` w `IndicatorResultOut`, z opisem odróżniającym je od `settled`
- [ ] 1.2 `_exactly_one_shape` → dokładnie jeden kształt bez `error` albo zero kształtów z `error`; kształt i `error` naraz odrzucone
- [ ] 1.3 Test: model z kształtem i `error` naraz nie daje się zbudować
- [ ] 1.4 Test: model bez kształtu i bez `error` nadal nie daje się zbudować

## 2. Router: porażka per wpis

- [ ] 2.1 Odczyt serii grubszej (`higher_resolution`) zapisuje przyczynę pod rozdzielczością zamiast podnosić `HTTPException`
- [ ] 2.2 To samo dla serii drobnej (`needs_minute_series`)
- [ ] 2.3 `_result_out` zwraca wynik z `error`, gdy seria, której wpis potrzebuje, ma zapisaną przyczynę
- [ ] 2.4 Sufit serii drobnej, nieznany identyfikator, parametr poza zakresem, odwrócony zakres i sufit żądania zostają odmową całości — potwierdzić, że żadna nie przeszła przypadkiem do 2.1–2.3
- [ ] 2.5 Odczyt serii pomocniczej dalej jeden na rozdzielczość, nie jeden na wpis

## 3. Testy modułu

- [ ] 3.1 Wskaźnik bez serii drobnej obok wskaźnika z serii rysowanej: 200, jeden policzony, jeden z przyczyną
- [ ] 3.2 To samo dla serii grubszej (`htf_levels_day` bez serii dziennej)
- [ ] 3.3 Wszystkie zamówione wskaźniki bez serii: nadal 200, przyczyna przy każdym
- [ ] 3.4 Nieznany identyfikator obok policzalnych: 422 dla całości
- [ ] 3.5 Parametr poza zakresem obok policzalnych: 422 dla całości, z nazwanym zakresem
- [ ] 3.6 Powtórzenie tego samego żądania przy niezmienionym archiwum daje tę samą odpowiedź
- [ ] 3.7 Trzy okna sesji w jednym żądaniu czytają serię drobną raz

## 4. Terminal

- [ ] 4.1 `pnpm contract:generate`
- [ ] 4.2 `src/data/types.ts` + `src/data/archive.ts`: `error` na kształcie terminala, snake_case → camelCase
- [ ] 4.3 `Chart.tsx`: wynik z `error` nie idzie do rysowania — żadnej serii, żadnego prymitywu
- [ ] 4.4 Plakietka nazywa nieudane wskaźniki po identyfikatorze, z przyczyną
- [ ] 4.5 Toast nazywa nieudane wskaźniki, po tym samym kluczu slotu co dziś
- [ ] 4.6 Nieudany wskaźnik zostaje zaznaczony w wybieraku i zapisany w slocie siatki

## 5. Testy terminala

- [ ] 5.1 Część policzona, część z przyczyną: policzone rysują się, nieudany nazwany
- [ ] 5.2 Nieudany wskaźnik nie zostaje odznaczony ani usunięty ze slotu
- [ ] 5.3 Kolejne dopytanie, w którym wskaźnik już się liczy, rysuje go bez ponownego wyboru
- [ ] 5.4 Wynik z `error` nie zostawia po sobie pustej serii ani prymitywu na wykresie

## 6. Domknięcie

- [ ] 6.1 `modules/market-data/README.md` — sekcja o wskaźnikach: odpowiedź częściowa i granica odmów
- [ ] 6.2 `openspec validate indicator-result-names-its-own-failure --strict`
- [ ] 6.3 Test lokalny: para bez serii minutowej, wskaźniki mieszane, na działającym stosie
- [ ] 6.4 `review.md`
- [ ] 6.5 Pull request do `main` — po `add-technical-indicators`
