## 1. Pomiar, od którego zależy gałąź w projekcie

- [ ] 1.1 Zmierzyć na demo, co zwraca odczyt jednej świecy `DAY` dla US100 tuż po zamknięciu
  okresu: świecę właśnie zamkniętą czy już rozpoczętą nową. Test `live` w `capital-gateway`,
  w duchu `tests/test_live.py`, uruchamiany wyłącznie z `--run-live`.
- [ ] 1.2 Zapisać wynik w `design.md` pod decyzją o zasiewie i wybrać gałąź degradacji dla
  zadania 3.4. Wynik odwrotny nie zmienia delt ani podejścia — zmienia jedną gałąź.
- [ ] 1.3 W tym samym pomiarze potwierdzić, czy odczyt REST sięgający teraźniejszości zwraca
  świecę okresu, który jeszcze trwa — dla rozdzielczości ze stałą długością okresu i dla
  `DAY`. To potwierdzenie zachowania providera, nie warunek: grupa 4 jest poprawna w obie
  strony.
- [ ] 1.4 Sprawdzić przy okazji, czy `marketStatus` dla US100 zmienia się zgodnie z sesją,
  bo na nim opiera się rozstrzygnięcie dla `DAY` i `WEEK`.

## 2. capital-gateway: koniec historii wymaga zebranej świecy

- [x] 2.1 W `capital_gateway/history.py` powiązać ustawienie `history_ended` z tym, czy
  odczyt zebrał już jakąkolwiek świecę — pusta odpowiedź na okno przed pierwszą zebraną
  świecą kończy odczyt bez stwierdzania końca historii.
- [x] 2.2 Test: pierwsze okno wraca `None`, odczyt zwraca pustą serię i `history_ended`
  fałszywe.
- [x] 2.3 Test: pierwsze okno wraca świece, drugie `None` poza podłogą — `history_ended`
  prawdziwe, czyli zachowanie sprzed zmiany zostaje.
- [x] 2.4 Test: podłoga konsumenta nadal nie ustawia `history_ended` (regresja na
  `on_the_floor`).
- [x] 2.5 `uv run pytest`, `uv run ruff check .`, `uv run pyright`.

## 3. capital-gateway: zasiew granicy okresu dla `DAY` i `WEEK`

- [x] 3.1 Dodać `Room` wstrzykiwaną funkcję odczytu bieżącej świecy dla pary, tym samym
  wzorcem co `UpstreamFactory` — `stream/` nie może zacząć znać transportu.
- [x] 3.2 W `stream/forming.py` rozdzielić „nie znam granicy" od „mam świecę": rozdzielczość
  bez stałej granicy okresu przyjmuje granicę z zewnątrz, zamiast czekać na zamkniętą świecę.
- [x] 3.3 Zablokować rozciąganie świecy zamkniętej: po zamknięciu okresu przez providera
  kolejne kwotowanie MUST NOT dokleić się do tamtej świecy.
- [x] 3.4 Wpiąć przeładowanie granicy w trzy zdarzenia: otwarcie pokoju, pierwsze kwotowanie
  po zamknięciu świecy, ponowne połączenie po zerwaniu. Gałąź degradacji według wyniku 1.2.
- [x] 3.5 Test: pokój `DAY` otwarty bez ani jednej zamkniętej świecy publikuje świecę
  w budowie po pierwszym kwotowaniu.
- [x] 3.6 Test: kwotowanie po zamknięciu świecy otwiera nowy okres, a świeca zamknięta
  zostaje nietknięta.
- [x] 3.7 Test: odczyt granicy, który zawiódł, nie publikuje świecy w budowie, a kwotowania
  idą dalej.
- [x] 3.8 Test: rozdzielczości ze stałą granicą okresu zachowują się dokładnie jak dotąd —
  żadnego dodatkowego odczytu.
- [x] 3.9 `uv run pytest`, `uv run ruff check .`, `uv run pyright`.

## 4. capital-gateway: odczyt historii mówi, który okres jeszcze trwa

- [x] 4.1 W `capital_gateway/dtos.py` dodać na `Candle` pole mówiące, czy okres się domknął.
  To zmiana kontraktu między modułami — sprawdzić, czy `openapi.py` opisuje ją tam, gdzie
  trzeba.
- [x] 4.2 Wyznaczanie dla rozdzielczości o stałej długości okresu: arytmetyka na
  `PERIOD_SECONDS`, które `history.py` już trzyma.
- [x] 4.3 Wyznaczanie dla `DAY` i `WEEK`: rozstrzyga stan rynku instrumentu (`tradeable`
  z `mapping.py`), nigdy arytmetyka na granicy sesji.
- [x] 4.4 Odczyt zakotwiczony w przeszłości nie oznacza żadnej świecy jako trwającej.
- [x] 4.5 Test: odczyt do chwili bieżącej na `MINUTE_5` — najnowsza świeca oznaczona jako
  trwająca, wszystkie starsze jako zamknięte.
- [x] 4.6 Test: `DAY` przy rynku otwartym — najnowsza trwająca; przy rynku zamkniętym —
  wszystkie zamknięte.
- [x] 4.7 Test: odczyt z `before` w przeszłości — wszystkie świece zamknięte, niezależnie od
  stanu rynku.
- [x] 4.8 `uv run pytest`, `uv run ruff check .`, `uv run pyright`.

## 5. market-data: granica powstaje z pomiaru i daje się unieważnić

- [x] 5.1 W `coverage.py` dodać zdejmowanie granicy dla pary — zdjęcie flagi `history_ended`
  bez ruszania zakresów pokrycia i bez ruszania świec.
- [x] 5.2 W `jobs/runner.py` zapisywać granicę z najstarszej odebranej świecy, a nie
  z `chunk.chunk_start`; kawałek bez ani jednej świecy nie zapisuje granicy wcale.
- [x] 5.3 W `jobs/plan.py` przestać czytać `earliest_reachable` i przestać przycinać —
  `effective_from` równe `requested_from`.
- [x] 5.4 W `routers/pairs.py` zdejmować granicę przed planowaniem, gdy żądana data początku
  jest wcześniejsza niż zapisana granica. Wyłącznie ta ścieżka zapisuje; `/jobs/estimate`
  nie rusza niczego.
- [x] 5.5 Test: para z zapisaną granicą i prośbą starszą od niej planuje pełny zakres,
  a granica znika.
- [x] 5.6 Test: wycena tej samej prośby daje ten sam zakres i **nie** zdejmuje granicy.
- [x] 5.7 Test: kawałek z `history_ended` zapisuje granicę na najstarszej odebranej świecy,
  nie na krawędzi okna.
- [x] 5.8 Test: kawałek pusty z `history_ended` nie zapisuje granicy.
- [x] 5.9 Test: hurtowe pomijanie starszych kawałków w obrębie zlecenia działa dalej —
  regresja na `skip_chunks_beyond_history`.
- [x] 5.10 Przejrzeć testy opierające się na starym przycinaniu (`tests/test_jobs_plan.py`,
  `tests/test_coverage.py`) i przepisać je na nową regułę zamiast rozluźniać.
- [x] 5.11 `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`, `uv run pyright`.

## 6. market-data: archiwum przestaje utrwalać okres, który trwa

- [x] 6.1 W `market_data/gateway/history.py` czytać pole z odpowiedzi gatewaya zamiast
  wpisywać „zamknięta" na sztywno.
- [x] 6.2 Sprawdzić, że `store.write_candles` odrzuca taką świecę — reguła istnieje, chodzi
  o potwierdzenie, że wreszcie ma na czym zadziałać, a nie o nowy kod.
- [x] 6.3 Rozstrzygnąć, gdzie odsiać świecę w budowie, żeby `FormingCandleRejected` nie
  wywracało całego wsadu: `fill_gap` i `execute_chunk` filtrują serię przed zapisem, tak jak
  już filtrują po `chunk_start`. Zakres pokrycia zostaje niezmieniony — okres był sprawdzony.
- [x] 6.4 Test: odczyt historii ze świecą trwającą zapisuje wszystkie pozostałe, a tamtej
  nie.
- [x] 6.5 Test: pokrycie po takim zapisie obejmuje ten sam zakres co dotąd.
- [x] 6.6 Test regresji na `bars_to_close_gap`: para, której najnowsza świeca jest zamknięta,
  a bieżący okres trwa, prosi o uzupełnienie zamiast uznać się za bieżącą.
- [x] 6.7 Sprawdzić rollupy: `refresh_all` liczy z tego, co zapisane, więc odsianie świecy
  minutowej w budowie nie może zostawić kubełka zbudowanego z niepełnych danych.
- [x] 6.8 `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`, `uv run pyright`.

## 7. terminal: „od kiedy faktycznie zebrano" bez nowego pola na wire

- [x] 7.1 W historii zbierania wyliczyć zakres faktycznie objęty z kawałków, które już
  przychodzą (`chunks`): najstarszy `chunk_start` wśród tych w stanie `done`.
- [x] 7.2 Pokazać go obok daty, o którą poproszono, żeby wiersz „0 świec" dał się odróżnić
  od awarii.
- [x] 7.3 Test komponentu na obu przypadkach: zebrano płycej, niż proszono, i zebrano
  wszystko.
- [x] 7.4 `pnpm test`, `pnpm lint`, `pnpm typecheck`. `pnpm contract:generate` nie jest
  potrzebne — kontrakt `market-data` się nie zmienia; potwierdzić przez `pnpm contract:check`.

## 8. Domknięcie

- [x] 8.1 `openspec validate history-boundary-and-live-daily-candle --strict`.
- [x] 8.2 Wdrożyć w kolejności z `design.md`: `capital-gateway` w całości → **`alembic
  upgrade head`** → `market-data`. Migracja nie jedzie ani z obrazem, ani z workflow,
  a bez niej nowy `market-data` odpowiada pięćsetką na każdy odczyt pokrycia
  (`/candles`, `/coverage`, `/jobs/estimate`, `POST /pairs`). **Zrobione w złej
  kolejności** — migracja poszła po wdrożeniu, ręcznie, po awarii; opis w `review.md`.
- [x] 8.3 Odzyskać US100: poprosić o dane od 2024-01-01 dla siedmiu rozdzielczości
  i sprawdzić `GET /coverage/US100?resolution=DAY`.
- [x] 8.4 Sprawdzić na wykresie, że `DAY` i `WEEK` pokazują bieżącą świecę zaraz po
  otwarciu i że jej cena się rusza, a nie stoi.
- [x] 8.5 Sprawdzić w archiwum, że bieżący okres dzienny **nie** jest zapisany, a poprzedni
  jest — `GET /candles/US100?resolution=DAY` przy otwartym rynku.
- [x] 8.6 Napisać `review.md` — bez niego zmiany nie da się zarchiwizować.
