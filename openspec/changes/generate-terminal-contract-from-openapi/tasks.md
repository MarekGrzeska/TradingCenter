## 1. market-data: schemat da się zrzucić bez serwera

- [ ] 1.1 Punkt wejścia drukujący `app.openapi()` jako JSON na stdout (`python -m market_data.openapi`), bez puli połączeń, bez gatewaya, bez sieci
- [ ] 1.2 Test, że zrzut działa w izolacji i zawiera komplet komponentów — dziś 27; asercja na obecność nazw, nie na ich liczbę, żeby dodanie modelu nie było porażką
- [ ] 1.3 README `market-data`: jednym zdaniem, po co to jest i kto to woła

## 2. terminal: generowanie typów

- [ ] 2.1 `openapi-typescript` jako zależność deweloperska
- [ ] 2.2 `npm run contract:generate` — woła zrzut z `market-data`, przepuszcza przez generator, zapisuje `src/data/contract.generated.ts`; nagłówek pliku mówi, że jest generowany i czym
- [ ] 2.3 `npm run contract:check` — regeneruje do pliku tymczasowego i porównuje z zapisanym; kod wyjścia niezerowy, gdy się różnią, z komunikatem wskazującym `contract:generate`
- [ ] 2.4 Wygenerowany plik zacommitowany; `.gitignore` MUST NOT go pomijać, a linter i formatter MUST go ignorować

## 3. terminal: `Raw*` przestają być kopią

- [ ] 3.1 Zamienić 13 interfejsów `Raw*` w `archive.ts` na aliasy do `components["schemas"][...]` — jedna linia na kształt
- [ ] 3.2 Nie ruszać ciał `map*`, `translateMessage` ani `createArchiveSource` — jeśli któreś wymaga zmiany, to znaczy, że ręczna kopia i schemat się różniły; **taki przypadek udokumentować w review.md jako znalezisko**, a nie po cichu poprawić
- [ ] 3.3 `npm run typecheck` przechodzi; pełny pakiet testów terminala przechodzi **bez żadnej zmiany w testach** — to jest dowód, że kontrakt na drucie się nie ruszył

## 4. Dowód, że strażnik działa

- [ ] 4.1 Ręcznie: przemianować pole w `contract.py`, zregenerować, sprawdzić, że `tsc` wskazuje konkretny mapper i konkretne pole; cofnąć zmianę
- [ ] 4.2 Ręcznie: zmienić `contract.py` **bez** regeneracji i sprawdzić, że `contract:check` się przewraca; cofnąć

## 5. Domknięcie

- [ ] 5.1 `ruff` i `pytest` w `market-data`, `lint`, `typecheck` i testy w `terminal`
- [ ] 5.2 README terminala: skąd biorą się typy kontraktu i co uruchomić po zmianie kontraktu po stronie serwera
- [ ] 5.3 `openspec validate generate-terminal-contract-from-openapi --strict`
