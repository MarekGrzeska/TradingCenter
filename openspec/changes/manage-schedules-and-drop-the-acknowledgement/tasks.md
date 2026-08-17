## 1. Zgoda znika z modułu

- [x] 1.1 Migracja: `drop_column` `unattended_ack` na `schedules` i `triggers`; `downgrade`
      odtwarza je z `false`, z zapisaną w migracji ceną tego cofnięcia (D1)
- [x] 1.2 `contract.py`: pole z `ScheduleIn`, `ScheduleOut`, `TriggerIn`, `TriggerOut`
- [x] 1.3 `validation.py`: `check_unattended` usunięte wraz z jego testami
- [x] 1.4 `routers/schedules.py`: cztery wywołania `_check_unattended` i sam pomocnik
- [x] 1.5 `store.py`: kolumna z zapytań i z funkcji zapisu obu rodzajów
- [x] 1.6 Sprawdzić, że nadmiarowe `unattended_ack` w ciele zapisu jest **ignorowane**, nie
      odrzucane — to jest okno między wdrożeniem modułu a terminala (design, Risks)

## 2. Usuwanie w module

- [x] 2.1 Migracja (ta sama co 1.1): oba klucze obce `schedule_fires` na `ON DELETE
      CASCADE` (D2)
- [x] 2.2 `store.py`: `delete_schedule` i `delete_trigger`, filtrowane właścicielem w
      zapytaniu, zwracające, czy coś usunięto
- [x] 2.3 `routers/schedules.py`: `DELETE /schedules/{id}` i `DELETE /triggers/{id}` — `204`,
      `404` dla cudzego i nieistniejącego (D3)
- [x] 2.4 Testy `-m db`: usunięcie zabiera historię wyzwoleń, zostawia przebiegi; cudzy wpis
      daje `404` i zostaje nietknięty; wyłączenie dalej jest czym innym niż usunięcie

## 3. Narzędzia w teams-mcp

- [x] 3.1 `pause_schedule` / `resume_schedule` nad `POST /schedules/{id}/disable` i
      `/enable`, i to samo dla wyzwalaczy
- [x] 3.2 `edit_schedule` nad `PUT /schedules/{id}` — zmiana pory bez zakładania drugiego
      wpisu (D4); `edit_trigger` nad `PUT /triggers/{id}`
- [x] 3.3 `delete_schedule` i `delete_trigger`, po jednym wpisie na wywołanie (D5), z
      opisem mówiącym, co znika bezpowrotnie, a co zostaje
- [x] 3.4 Testy: zestaw narzędzi to dokładnie oczekiwana lista; usunięcie woła `DELETE`;
      poprawka woła `PUT`, a nie parę `DELETE`+`POST`
- [x] 3.5 `uv run python scripts/contract.py generate` — snapshot `teams.openapi.json` po
      zmianie kontraktu

## 4. Terminal

- [x] 4.1 `pnpm contract:generate` — przepisany `contract.teams.generated.ts`
- [x] 4.2 Checkbox zgody znika z `ScheduleWizardDialog.tsx`, `SchedulesPanel.tsx` i
      `scheduleDraft.ts`; pole znika z `teamsApi.ts` i z obu draftów
- [x] 4.3 `teamsApi.ts`: `deleteSchedule` i `deleteTrigger`
- [x] 4.4 `SchedulesPanel.tsx`: usuwanie obok wyłączenia, z potwierdzeniem nazywającym
      historię jako stratę i przebiegi jako to, co zostaje (D6)
- [x] 4.5 Testy: usunięcie po potwierdzeniu odczytuje listę na nowo; rezygnacja zostawia
      wpis; wyłączenie dalej działa osobno; nigdzie nie ma już pola zgody

## 5. Domknięcie

- [x] 5.1 `modules/teams`: `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`,
      `uv run pyright`
- [x] 5.2 `modules/teams-mcp`: `uv run pytest`, `uv run ruff check .`, `uv run pyright`,
      `uv run python scripts/contract.py check`
- [x] 5.3 `modules/terminal`: `pnpm test`, `pnpm lint`, `pnpm typecheck`,
      `pnpm contract:check`
- [x] 5.4 `openspec validate manage-schedules-and-drop-the-acknowledgement --strict`
- [x] 5.5 Wdrożenie w kolejności: `teams`, potem `teams-mcp` i terminal

      Wdrożone 17 sierpnia 2026 z `1d5a199`. `teams` i `teams-mcp` odpowiadają 200 na
      `/health`, a że migracja idzie w `lifespan` przed obsługą ruchu, odpowiedź jest
      jednocześnie dowodem, że `0007` przeszła na produkcyjnej bazie.
- [ ] 5.6 Na produkcji: założyć harmonogram z czatu nad zespołem z narzędziami handlowymi —
      ten, którego dotąd nie dało się założyć — i usunąć go z terminala
- [x] 5.7 `review.md`
