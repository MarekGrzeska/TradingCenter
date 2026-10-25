## Context

`compare.compare()` już trzyma regułę porównywalności i listę metryk (`METRICS`); narzędzie `compare_runs` dokłada przed
nią sprawdzenie liczby i istnienia. Trasy uruchomień są w `routers/runs.py`, w tym `GET /runs/{run_id}` z parametrem
liczbowym.

## Goals / Non-Goals

**Goals:** jedna reguła dla rozmowy i ekranu; kształt porównania znany wygenerowanemu kontraktowi.

**Non-Goals:** porównanie krzywych kapitału na jednym wykresie; ranking; porównanie uruchomień nieporównywalnych „mimo
wszystko”.

## Decisions

**`GET` z powtórzonym `run_id`, nie `POST` z ciałem.** Porównanie niczego nie zapisuje, a pięć liczb mieści się w adresie.
`POST /runs/compare` łatwiej rozszerzyć, ale nie ma czego rozszerzać, a `GET` zostawia odczyt odczytem dla rozróżnienia
ról (`viewer` dostaje tylko `GET`, choć dziś pakiet strategii jest i tak tylko dla `admin`).

**Trasa zarejestrowana przed `/runs/{run_id}`.** FastAPI dopasowuje trasy po kolei; `compare` pasuje do wzorca
`{run_id}` i skończyłoby się 422 walidacji liczby zamiast porównaniem.

**Nazwany model `ComparedRunOut` z polem na każdą metrykę zamiast `dict[str, Any]`.** Wymaganie „Raport ma kształt w
kontrakcie” mówi to samo o raporcie; słownik dałby w TypeScripcie `Record<string, unknown>` i tabela zgadywałaby typy.
Narzędzie agenta może zostać przy swoim `Comparison` — jego czyta model, nie kontrakt.

**Sprawdzenie 2–5 i powtórzeń w `compare.py`.** Dziś siedzi w narzędziu; trasa skopiowałaby je, a zasada mówi, że reguła
domenowa jest testowana raz, w najniższej warstwie. Brak uruchomienia zostaje po stronie wołającego, bo trasa odpowiada na
niego 404, a narzędzie odmową.

**Odmowa jako `ProblemsOut` z jednym problemem na różnicę.** Tak odmawia `POST /runs`; terminal już umie pokazać listę
problemów, więc nie trzeba nowego kształtu błędu.

## Risks / Trade-offs

- [Zaznaczenie znika przy zmianie filtra strategii] → zaznaczenie trzyma identyfikatory, nie wiersze, i przeżywa
  przełączenie listy; czyszczone jest jawnie.
- [Parametry różnych strategii mają różne nazwy] → kolumna pokazuje parametry swojego uruchomienia jako `nazwa=wartość`,
  bez próby wyrównania ich w wiersze.
