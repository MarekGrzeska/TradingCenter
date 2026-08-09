## 1. Wersje przestają być folklorem

- [x] 1.1 `packageManager` w `modules/terminal/package.json`, przypięte do wersji, która napisała `pnpm-lock.yaml` (11.20.0; lockfile w formacie 9.0)
- [x] 1.2 README terminala: jedno zdanie, że wersja `pnpm` jest w `package.json`, a nie w czyjejś pamięci

## 2. Workflow

- [x] 2.1 `.github/workflows/checks.yml`, wyzwalany na `pull_request` do `main` **i** na `push` do `main` — bezpośredni zapis na `main` też się zdarza
- [x] 2.2 `concurrency` anulujące poprzedni przebieg tego samego PR-a; bez tego trzy pushy pod rząd to trzy komplety kontenerów
- [x] 2.3 Zadanie `capital-gateway`: `uv run ruff check .`, `uv run pytest -q`
- [x] 2.4 Zadanie `market-data`: `uv run ruff check .`, `uv run pytest -q` — **bez pomijania testów bazodanowych**; runner ma Dockera, więc testcontainers wstanie i 273 testy `db` po raz pierwszy pojadą na Linuksie. *Uwaga: pominiętych zawsze jest 7 i to są testy `live`, nie `db` — pierwotnie napisałem tu, że to te bazodanowe, i było to nieprawdą; `db` nie pojawiały się w liczniku pominięć nigdy, bo lokalnie Docker chodzi*
- [x] 2.5 Zadanie `terminal`: Node 22 + `pnpm` z `packageManager` + `uv` (bo `contract:check` sięga po Pythona `market-data`), `pnpm install --frozen-lockfile`, potem `contract:check`, `lint`, `typecheck`, `test`
- [x] 2.6 `contract:check` **przed** testami — przestarzały kontrakt unieważnia wnioski, jakie testy wyciągają o drucie
- [x] 2.7 Trzy zadania równolegle, każde z czytelną nazwą; porażka jednego modułu MUST NOT ukrywać wyniku pozostałych
- [x] 2.8 `permissions: contents: read` — workflow niczego nie zapisuje

## 3. Dowód, że działa i że łapie

- [ ] 3.1 Otworzyć PR i zobaczyć **zielony** przebieg wszystkich trzech zadań — w szczególności, że testy `db` faktycznie się wykonały, a nie pominęły
- [ ] 3.2 Zobaczyć **czerwony** przebieg: tymczasowo zepsuć jedną rzecz z każdego rodzaju (test, lint, kontrakt), potwierdzić, że zadanie pada i mówi które, cofnąć
- [ ] 3.3 Odnotować w review.md czas przebiegu i to, czy testy bazodanowe przeszły na Linuksie za pierwszym razem

## 4. Blokada merge'a

- [ ] 4.1 Włączyć branch protection na `main` wymagające trzech kontekstów tego workflow — *to ustawienie repozytorium, nie plik; do wykonania przez właściciela repo*:
      ```sh
      gh api -X PUT repos/MarekGrzeska/TradingCenter/branches/main/protection \
        -H "Accept: application/vnd.github+json" \
        -f 'required_status_checks[strict]=true' \
        -f 'required_status_checks[contexts][]=capital-gateway' \
        -f 'required_status_checks[contexts][]=market-data' \
        -f 'required_status_checks[contexts][]=terminal' \
        -F 'enforce_admins=false' -F 'required_pull_request_reviews=null' \
        -F 'restrictions=null'
      ```
- [ ] 4.2 Potwierdzić, że PR z czerwonym przebiegiem faktycznie nie daje się zmergować

## 5. Domknięcie

- [x] 5.1 Lokalnie: `ruff` i `pytest` w obu modułach Pythona, `lint`/`typecheck`/`contract:check`/`test` w terminalu — to samo, co robi CI, tymi samymi poleceniami *(gateway 140, market-data 435, terminal 224 — wszystko zielone)*
- [x] 5.2 README w korzeniu repo: co się sprawdza automatycznie i gdzie to zobaczyć
- [x] 5.3 `openspec validate checks-run-before-a-merge --strict`
