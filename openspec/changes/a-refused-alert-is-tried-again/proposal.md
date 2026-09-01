## Why

`a-notification-reaches-the-operator` obiecało w dwóch miejscach — `design.md` („Decisions") i
uzasadnieniu wymagania `strategy-alerts` — że brak znacznika **jest** mechanizmem ponowienia:
brama nie pamięta niczego, co wysłała, więc nieudana wysyłka zostawia rzecz niezapowiedzianą, a
następny przebieg próbuje jeszcze raz. W `social-data` tak działa. W `strategy` nie.

Przegląd tamtej zmiany (`review.md`, Findings) zmierzył to: `notified_at` w `strategy` jest
**kolumną tylko do zapisu**. O powiadomieniu decyduje wyłącznie `is_new_setup(decision, previous)`,
które porównuje kierunek z poprzednią **zapisaną** decyzją i nigdy nie pyta, czy tamta dojechała.
Skutek jest wąski i cichy: odmowa bramy dokładnie na tej świecy, na której setup powstał, nie jest
ponawiana — następna świeca z tym samym kierunkiem czyta się jako „nie zmiana" — więc setup stojący
dziesięć świec nie zostaje zapowiedziany ani razu. Zostaje wpis w logu na poziomie `warning` i
decyzja w bazie, o której operator nie wie.

Asymetria widać w samych nazwach testów: `social-data` ma
`test_a_failed_delivery_leaves_no_marker_and_the_next_pass_retries`, `strategy` ma
`test_a_failed_delivery_leaves_the_decision_recorded_and_unmarked` — i na tym kończy.

To jest zmiana OpenSpec, a nie zwykła poprawka, z jednego powodu: normatywne zdanie wymagania
„Ta sama decyzja nie powiadamia dwa razy" mówi dziś, że powiadomienie MUST wyjść **wyłącznie**
wtedy, gdy decyzja jest zmianą względem poprzedniej zapisanej. Ponowienie jest z definicji drugim
powiadomieniem o decyzji, która zmianą nie jest, więc naprawa bez ruszenia wymagania byłaby kodem
sprzecznym ze specyfikacją, którą `--strict` przepuszcza.

## What Changes

- **Wymaganie `strategy-alerts` → „Ta sama decyzja nie powiadamia dwa razy" dostaje drugi warunek.**
  Powtórzona decyzja MUST NOT powiadamiać drugi raz **wtedy, gdy o poprzedniej rzeczywiście
  powiedziano**. Poprzednia bez znacznika znaczy, że operator nie wie o niczym — więc powtórzenie
  jest pierwszym powiadomieniem, nie drugim.
- **`RecordedDecision` zaczyna nieść `notified_at`**, a `is_new_setup` je czyta. To cała poprawka:
  `previous` jest już wczytywane przez `evaluate_once` przed oceną, więc nie dochodzi żadne
  zapytanie na przebieg.
- **Deduplikacja nie słabnie.** Udane powiadomienie stawia znacznik w tej samej sekundzie, więc
  setup stojący dziesięć świec dalej mówi raz. Zmienia się wyłącznie to, co się dzieje, gdy tego
  jednego razu nie było.
- **Skutek uboczny, nazwany, bo jest widoczny**: brama skonfigurowana *po* tym, jak setup już stał,
  zapowie go przy pierwszym przebiegu — poprzednia decyzja nie ma znacznika, bo nie było komu
  powiedzieć. To jest zachowanie chciane: świeżo podłączony kanał mówi, co stoi teraz, zamiast
  milczeć do następnej zmiany kierunku.
- **Poza zakresem: `social-data`.** Tam znacznik jest czytany i ponowienie działa; jedyne, co ta
  zmiana o nim mówi, to że jego okno ma termin ważności (`COLLECT_WINDOW_HOURS`), i to zostaje
  zapisane w `review.md` tamtej zmiany, a nie zmieniane tutaj.
- **Poza zakresem: kolejka w bramie.** Powód jest ten sam, dla którego jej nie ma —
  `a-notification-reaches-the-operator`, `design.md`, „Decisions".

## Capabilities

### Modified Capabilities

- `strategy-alerts`: jedno wymaganie — kiedy powtórzona decyzja jednak powiadamia.

## Impact

- **Zmieniane**: `modules/strategy/strategy/store.py` (`notified_at` w kolumnach odczytu i w
  `RecordedDecision`), `modules/strategy/strategy/alerts.py` (`is_new_setup`),
  `modules/strategy/tests/test_alerts.py`.
- **Bez zmian**: kontrakt REST — `routers/decisions.py` odwzorowuje pola po nazwie, więc nowe pole
  na dataclassie nie wychodzi na wire i nie rusza wygenerowanego kontraktu terminala. Migracji nie
  ma: kolumna `notified_at` istnieje od `0004_the_announced_marker`.
- **Operator**: nic. Żadnego `apply`, żadnego ustawienia.

`design.md` nie powstaje: nie ma tu wyboru między podejściami do wytłumaczenia. Alternatywa —
osobny znacznik „ostatnio zapowiedziany kierunek" obok decyzji — to druga kopia stanu, który już
jest w tabeli, i odrzucenie jej mieści się w jednym zdaniu powyżej. `review.md` powstanie po
zadaniach.
