## Why

Nic w tym repo nie sprawdza się samo. Testy, lintery, `typecheck` i `contract:check` istnieją
i przechodzą — ale wyłącznie wtedy, gdy ktoś je wpisze. Nie ma `.github/workflows`, więc jedyną
gwarancją, że `main` jest zielony, jest to, że ktoś pamiętał.

Dla `contract:check` jest to szczególnie kosztowne, bo ono właśnie po to powstało, żeby złapać
rozjazd, którego człowiek nie zauważy. Sprawdzenie chroniące przed cichym błędem, uruchamiane
ręcznie, dziedziczy dokładnie tę wadę, którą miało usunąć: działa, dopóki ktoś o nim pamięta,
a zapomnienie nie daje żadnego sygnału.

Trzy ostatnie PR-y pokazały też, że to nie jest teoria. Refaktor `app.py` przestawił piętnaście
tras, a jedynym dowodem, że schemat się nie ruszył, był zrzut porównany ręcznie przeze mnie.
Gdyby to samo zrobił ktoś inny, w innym tygodniu, nikt by tego nie sprawdził.

## What Changes

- Powstaje workflow GitHuba uruchamiany na każdym pull requeście do `main` oraz na pushu do
  `main`. Sprawdza wszystkie trzy moduły:
  - `capital-gateway`: `ruff check`, `pytest`
  - `market-data`: `ruff check`, `pytest` — **łącznie z testami bazodanowymi**, bo runner ma
    Dockera, a `conftest` pomija je wyłącznie tam, gdzie Dockera nie ma
  - `terminal`: `lint`, `typecheck`, `test` oraz `contract:check`
- Moduły idą osobnymi zadaniami, równolegle — porażka w gatewayu nie ma powodu ukrywać wyniku
  terminala.
- `contract:check` MUST działać w zadaniu, które ma jednocześnie Node i środowisko Pythona
  `market-data`, bo z definicji porównuje jedno z drugim.
- Wersje narzędzi MUST być przypięte, nie brane „najnowsze": to, co CI uruchamia, ma być tym, co
  uruchamia deweloper.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

Brak. Nie zmienia się żadne zachowanie modułu — te same polecenia, te same wyniki, tylko
uruchamiane bez udziału człowieka. `.openspec.yaml` niesie `skip_specs: true`.

## Impact

**Nowe**: `.github/workflows/checks.yml`.

**terminal**: pole `packageManager` w `package.json`. Lokalnie `pnpm` nie jest na PATH,
`corepack` jest zepsuty pod Node 25, a `node_modules` jest podlinkowane ze store'a v11 — dziś
wiedza „użyj `npx pnpm@11`" jest folklorem. Wpisana do `package.json` przestaje nim być i staje
się jednym źródłem prawdy dla CI i dla maszyny.

**Czego to nie robi**: workflow daje *wynik*, nie *blokadę*. Wymaganie zielonego wyniku przed
merge'em to ustawienie repozytorium (branch protection), nie plik w repo — i jest nazwane
w tasks.md jako osobny krok do wykonania przez właściciela repo.
