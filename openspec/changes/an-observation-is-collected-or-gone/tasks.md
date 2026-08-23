# Tasks — an-observation-is-collected-or-gone

## 1. Moduł: usunięcie zamiast zakończenia

- [x] 1.1 Migracja 0003: usuń wydarzenia z `tracking_ended_at IS NOT NULL` (kaskady zabierają
      historię), potem zdejmij kolumnę — w tej kolejności, odwrotna nie działa
- [x] 1.2 `store.py`: `remove_event` na kaskadzie; usuń `end_tracking`, `include_ended` i każdy
      warunek na `tracking_ended_at`
- [x] 1.3 `models.py`, `views.py`, `contract.py`: znika `tracking_ended_at`, `Event.tracking`
      i stan `ended` w `CollectionOut`
- [x] 1.4 `routers/observations.py`: `DELETE /events/{provider_event_id}` zamiast
      `DELETE /events/{provider_event_id}/tracking`; 404 nazywa, czego nie ma

## 2. Moduł: zestaw narzędzi

- [x] 2.1 Zdejmij `untrack_event`; `mcp_app.py` przestaje je wymieniać
- [x] 2.2 Odmowa `track_event` przy suficie odsyła do operatora, nie do narzędzia
- [x] 2.3 Test „zestaw zmienia wyłącznie listę obserwacji" obejmuje także usunięcie; sufit
      powierzchni narzędzi przeliczony

## 3. Moduł: testy

- [x] 3.1 Usunięcie zabiera wydarzenie, rynki, wyniki, próbki i zakresy — jedną czynnością
- [x] 3.2 Ponowne objęcie obserwacją po usunięciu rusza z pustym archiwum
- [x] 3.3 Migracja: zastane `ended` znikają wraz z historią, reszta nietknięta

## 4. Terminal

- [x] 4.1 `contract.polymarket.generated.ts` regenerowany
- [x] 4.2 `polymarketApi.ts`: `removeEvent` zamiast `endTracking` i `deleteHistory`
- [x] 4.3 `EventCard`: zwinięty wiersz to tytuł, grupa, stan i usunięcie; `CollapsedSummary`
      znika
- [x] 4.4 `EndTrackingDialog` znika; `DeleteHistoryDialog` staje się `RemoveEventDialog`
      nazywającym całość
- [x] 4.5 Testy widoku: pięć na dialog, plus „zwinięty wiersz nie niesie procentu"
- [ ] 4.6 Ręczna próba: usunąć zastany wiersz z ekranu i zobaczyć, że znika z listy
      *(operatorska — wymaga uruchomionego stacku; kontener bazy i porty są współdzielone
      między worktree. Kształty po obu stronach drutu pokryte testami, migracja przejechana
      przeciwko prawdziwemu PostgreSQL-owi.)*

## 5. Domknięcie

- [x] 5.1 `CLAUDE.md`: dwa narzędzia piszące, nie trzy
- [x] 5.2 `modules/polymarket-data/README.md`: „osiem narzędzi, dwa piszące", i obserwacja
      zbierana albo usunięta
- [x] 5.3 `review.md` wg szablonu repo
