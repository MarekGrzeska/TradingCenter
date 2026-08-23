# Tasks — an-observation-is-collected-or-gone

## 1. Moduł: usunięcie zamiast zakończenia

- [ ] 1.1 Migracja 0003: usuń wydarzenia z `tracking_ended_at IS NOT NULL` (kaskady zabierają
      historię), potem zdejmij kolumnę — w tej kolejności, odwrotna nie działa
- [ ] 1.2 `store.py`: `remove_event` na kaskadzie; usuń `end_tracking`, `include_ended` i każdy
      warunek na `tracking_ended_at`
- [ ] 1.3 `models.py`, `views.py`, `contract.py`: znika `tracking_ended_at`, `Event.tracking`
      i stan `ended` w `CollectionOut`
- [ ] 1.4 `routers/observations.py`: `DELETE /events/{provider_event_id}` zamiast
      `DELETE /events/{provider_event_id}/tracking`; 404 nazywa, czego nie ma

## 2. Moduł: zestaw narzędzi

- [ ] 2.1 Zdejmij `untrack_event`; `mcp_app.py` przestaje je wymieniać
- [ ] 2.2 Odmowa `track_event` przy suficie odsyła do operatora, nie do narzędzia
- [ ] 2.3 Test „zestaw zmienia wyłącznie listę obserwacji" obejmuje także usunięcie; sufit
      powierzchni narzędzi przeliczony

## 3. Moduł: testy

- [ ] 3.1 Usunięcie zabiera wydarzenie, rynki, wyniki, próbki i zakresy — jedną czynnością
- [ ] 3.2 Ponowne objęcie obserwacją po usunięciu rusza z pustym archiwum
- [ ] 3.3 Migracja: zastane `ended` znikają wraz z historią, reszta nietknięta

## 4. Terminal

- [ ] 4.1 `contract.polymarket.generated.ts` regenerowany
- [ ] 4.2 `polymarketApi.ts`: `removeEvent` zamiast `endTracking` i `deleteHistory`
- [ ] 4.3 `EventCard`: zwinięty wiersz to tytuł, grupa, stan i usunięcie; `CollapsedSummary`
      znika
- [ ] 4.4 `EndTrackingDialog` znika; `DeleteHistoryDialog` staje się `RemoveEventDialog`
      nazywającym całość
- [ ] 4.5 Testy widoku: trzy na dialog, plus „zwinięty wiersz nie niesie procentu"

## 5. Domknięcie

- [ ] 5.1 `CLAUDE.md`: dwa narzędzia piszące, nie trzy
- [ ] 5.2 `modules/polymarket-data/README.md`, jeśli mówi o zakończeniu obserwacji
- [ ] 5.3 `review.md` wg szablonu repo
