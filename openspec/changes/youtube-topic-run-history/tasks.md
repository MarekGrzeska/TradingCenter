## 1. Baza i zapis

- [x] 1.1 Migracja `0007` w łańcuchu `youtube`: `topic_runs` (wynik, liczby, przyczyny), indeksy `(topic_id, ran_at DESC)` i `(ran_at)`; `downgrade`
- [x] 1.2 `models.py` i `store.py`: `TopicRun`, zapis wpisu z retencją 30 dni w jednej transakcji, `skipped` raz na temat na dobę UTC, odczyt (od najnowszego, filtr po temacie, limit), ostatni wynik per temat
- [x] 1.3 Testy store i migracji (`-m db`): retencja, `skipped` raz na dobę, odczyt, ostatni per temat, wpis przeżywa usunięty temat

## 2. Pętla

- [x] 2.1 `_screen` zwraca powód braku werdyktów (`no_model`, `day_spent`, `unusable`, `failed`)
- [x] 2.2 `_discover`: wpis przebiegu dla `found`, `nothing_new`, `failed` (błąd źródła i limit), `skipped` (dzień nie starcza); liczby raportu z `_propose`
- [x] 2.3 Testy pętli: cztery wyniki, liczby raportu, przyczyna nieprzesiania, `skipped` raz na dobę i ponownie po północy, porażka nie przesuwa terminu

## 3. REST i kontrakt

- [x] 3.1 `contract.py`: `TopicRunOut`, `TopicRunsOut`, ostatni przebieg w `TopicOut`; trasa `GET /topic-runs` (filtr po temacie, limit); `caller_access`
- [x] 3.2 Testy REST: odczyt z filtrem, ostatni przebieg w `GET /topics`, odmowa złego limitu
- [x] 3.3 README `youtube_data`: historia przebiegów, wyniki, retencja

## 4. Terminal

- [x] 4.1 Skill `contract-sync`: `contract.youtube.generated.ts`
- [x] 4.2 `youtubeApi.ts` i `present.ts`: odczyt historii, etykiety wyników i przyczyn po polsku
- [x] 4.3 `CandidatesPanel.tsx`: widok Historia z filtrem po temacie; `WatchPanels.tsx`: ostatni wynik przy temacie
- [x] 4.4 Testy widoku: lista przebiegów z przyczyną porażki, pusta historia, filtr po temacie, ostatni wynik w Tematach

## 5. Zamknięcie

- [x] 5.1 `openspec validate youtube-topic-run-history --strict`, `uv run pytest`, `ruff`, `pyright`, `vitest`, `eslint`, `tsc`, `contract:check`, `db-cost-check`
- [x] 5.2 `review.md`
