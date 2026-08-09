## 1. market-data: schemat da się zrzucić bez serwera

- [x] 1.1 Punkt wejścia drukujący `app.openapi()` jako JSON na stdout (`python -m market_data.openapi`), bez puli połączeń, bez gatewaya, bez sieci
- [x] 1.2 Test, że zrzut działa w izolacji i zawiera komplet komponentów — dziś 27; asercja na obecność nazw, nie na ich liczbę, żeby dodanie modelu nie było porażką
- [x] 1.3 README `market-data`: jednym zdaniem, po co to jest i kto to woła

## 2. terminal: generowanie typów

- [x] 2.1 `openapi-typescript` jako zależność deweloperska
- [x] 2.2 `npm run contract:generate` — woła zrzut z `market-data`, przepuszcza przez generator, zapisuje `src/data/contract.generated.ts`; nagłówek pliku mówi, że jest generowany i czym
- [x] 2.3 `npm run contract:check` — regeneruje do pliku tymczasowego i porównuje z zapisanym; kod wyjścia niezerowy, gdy się różnią, z komunikatem wskazującym `contract:generate`
- [x] 2.4 Wygenerowany plik zacommitowany; `.gitignore` MUST NOT go pomijać, a linter i formatter MUST go ignorować

## 3. terminal: `Raw*` przestają być kopią

- [x] 3.1 Zamienić 13 interfejsów `Raw*` w `archive.ts` na aliasy do `components["schemas"][...]` — jedna linia na kształt
- [x] 3.2 Nie ruszać ciał `map*`, `translateMessage` ani `createArchiveSource` — jeśli któreś wymaga zmiany, to znaczy, że ręczna kopia i schemat się różniły; **taki przypadek udokumentować w review.md jako znalezisko**, a nie po cichu poprawić — *żadne ciało nie wymagało zmiany; wypadł natomiast alias `RawTrackedPairResult`, bo istniał wyłącznie po to, by odwoływał się do niego drugi interfejs*
- [x] 3.3 `npm run typecheck` przechodzi; pełny pakiet testów terminala przechodzi **bez żadnej zmiany w testach** — to jest dowód, że kontrakt na drucie się nie ruszył *(221 passed, zero zmian w plikach testowych)*

## 4. Dowód, że strażnik działa

- [x] 4.1 Ręcznie: przemianować pole w `contract.py`, zregenerować, sprawdzić, że `tsc` wskazuje konkretny mapper i konkretne pole; cofnąć zmianę
- [x] 4.2 Ręcznie: zmienić `contract.py` **bez** regeneracji i sprawdzić, że `contract:check` się przewraca; cofnąć

## 5. Domknięcie

- [x] 5.1 `ruff` i `pytest` w `market-data` (423 passed, 7 skipped), `lint`, `typecheck`, `contract:check` i testy w `terminal` (221 passed, bez zmian w testach)
- [x] 5.2 README terminala: skąd biorą się typy kontraktu i co uruchomić po zmianie kontraktu po stronie serwera
- [x] 5.3 `openspec validate generate-terminal-contract-from-openapi --strict`
