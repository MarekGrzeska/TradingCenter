## Context

Patrz `proposal.md` — Why. Stan dzisiaj, w trzech miejscach, które ta zmiana rusza:

- `routers/schedules.py::_first_fire_at` i `scheduler/clock.py::_next_fire_and_skipped` wołają
  `croniter` z `datetime.now(UTC)`, więc wyrażenie znaczy godzinę UTC. Kolumna
  `schedules.next_fire_at` jest `timestamptz`, czyli sam zapis jest już strefowo poprawny —
  zmienia się wyłącznie to, w czym liczona jest kolejna godzina.
- `GET /schedules/{id}/next-fires` odpowiada tylko dla harmonogramu zapisanego; kreator
  potrzebuje odpowiedzi dla szkicu.
- `POST /teams/{id}/runs` uruchamia najnowszą rewizję i jest już używane przez katalog
  (`TeamCatalogue.tsx`). Widok przebiegów woła to samo, więc po stronie modułu nie ma tu nic
  do zrobienia.

Wiążące ograniczenia z istniejących specyfikacji: terminal nie nosi własnego parsera wyrażeń
czasowych (`terminal-teams-schedules`), a wybieraki biorą treść z modułu — pilnuje tego test
`pickersComeFromTheModule.test.ts`. Okna modalne przechodzą przez `ModalShell`, czego pilnuje
`dialogsComeFromOnePlace.test.ts`.

## Goals / Non-Goals

**Goals:**

- Jedna implementacja zamiany rytmu na wyrażenie czasowe — w module.
- Podgląd najbliższych wyzwoleń dla szkicu tą samą drogą co dla harmonogramu zapisanego.
- Brak migracji bazy.

**Non-Goals:**

- Wybór strefy przez operatora. Strefa jest stałą modułu; kolumna byłaby polem, którego
  dzisiaj nikt nie ustawia, i drugim wymiarem w każdym teście zegara.
- Wyzwalacze (`teams-triggers`). Wyzwalacz nie ma godziny — ma warunek i odstęp w sekundach,
  więc strefa go nie dotyczy, a jego formularz zostaje, jaki jest.
- Wybór rewizji przy „Uruchom teraz". Uruchamia najnowszą, tak jak katalog.

## Decisions

### Strefa jako stała modułu, nie kolumna

`SCHEDULE_TIMEZONE = ZoneInfo("Europe/Warsaw")` w jednym miejscu (`scheduler/clock.py`),
używane przez obie ścieżki liczenia. `croniter` dostaje `datetime.now(SCHEDULE_TIMEZONE)`
i zwraca moment świadomy strefy, który idzie do bazy jako `timestamptz` — czyli w UTC.
Wyrażenie znaczy godzinę ścienną w Polsce, a wszystko poza modułem widzi dalej UTC.

Rozważone: kolumna `timezone` na `schedules`, wypełniona `Europe/Warsaw`. Odrzucone —
jeden operator, jedna strefa, a kolumna kosztowałaby migrację, pole w dwóch modelach
kontraktu i podwojenie przypadków w testach zegara. Jeśli kiedyś pojawi się drugi operator
w innej strefie, kolumna dokłada się bez zmiany kształtu odpowiedzi: stała staje się
wartością domyślną.

### Rytm jest na drucie, wyrażenie czasowe zostaje zapisem wykonawczym

`ScheduleIn` przyjmuje `recurrence` **albo** `cron_expression` — dokładnie jedno z dwóch,
sprawdzane walidatorem tak, jak `revision_mode`/`pinned_revision_id` już jest. Moduł zamienia
`recurrence` na wyrażenie i zapisuje wyrażenie; kolumna zostaje ta sama. `ScheduleOut` niesie
oba: `cron_expression` oraz `recurrence` odczytane z tego wyrażenia z powrotem, albo `null`,
gdy wyrażenie nie jest żadnym z rytmów.

`Recurrence` to jeden model z polem `kind` (`every_minutes`, `hourly`, `daily`, `weekly`,
`monthly`) i polami, których ten rytm używa (`minutes`, `hour`, `minute`, `weekdays`,
`day_of_month`). Zamiana w obie strony jest tabelką na kilkanaście linii i mieszka
w `teams/scheduler/recurrence.py`.

Rozważone: kolumna `recurrence` w bazie, z wyrażeniem liczonym w locie. Odrzucone — dwa
zapisy tej samej rzeczy w wierszu rozjeżdżają się przy pierwszym `UPDATE`, który dotknie
jednego z nich, a wyrażenie i tak musi zostać, bo jest tym, co potrafi wyrazić rytm spoza
kreatora. Rozważone też: mapowanie rytm↔wyrażenie w terminalu — odrzucone przez
`terminal-teams-schedules`, „Terminal nie liczy czasu wyzwolenia sam", i dlatego, że wtedy
podgląd pokazywałby wynik innego kodu niż ten, który wykonuje zegar.

### Podgląd szkicu: `POST /schedules/next-fires`

Nowa trasa bez `{id}`, przyjmująca to samo `recurrence` albo `cron_expression` co `ScheduleIn`
i odpowiadająca tym samym `NextFiresOut`. `POST`, nie `GET` z parametrami, bo `recurrence`
jest obiektem — a to samo ciało, które za chwilę pójdzie do zapisu, jest tu jedynym sposobem,
żeby podgląd i zapis nie rozjechały się na walidacji. Istniejące
`GET /schedules/{id}/next-fires` zostaje nietknięte.

### „Uruchom teraz" nie dokłada trasy

`TeamRunsView` woła `api.startRun(teamId)` — tę samą, którą woła katalog — i pokazuje
`ConfirmDialog` przed wywołaniem. Potwierdzenie nazywa rewizję: numer najnowszej rewizji
czyta `api.latestRevision(teamId)`, już używane przez `SchedulesPanel`. Po starcie widok
ustawia nowy przebieg jako oglądany i przeładowuje listę.

## Risks / Trade-offs

- **Zmiana czasu zjada albo dubluje godzinę ścienną.** Harmonogram codzienny o 2:30 nie ma
  swojego momentu w nocy przejścia na czas letni, a w nocy powrotu ma dwa. → `croniter`
  rozstrzyga to sam i deterministycznie; skutek jest opisany w `README` modułu przy strefie,
  a test zegara przechodzi obie noce i utrwala to, co moduł naprawdę robi.
- **Budżet dobowy resetuje się o północy UTC, wyzwolenia liczą się w Warszawie.** →
  Świadomie: patrz `teams-schedules`, wymaganie o jednym zegarze. Odstęp między resetem
  a porannym wyzwoleniem zmienia się o godzinę dwa razy w roku i nie ma to wpływu na to,
  ile zespół może wydać.
- **Harmonogramy zapisane dotąd przesuwają się o dwie godziny wstecz w UTC.** → Wdrożenie
  jest jednorazowym przesunięciem, nie cichą zmianą w czasie; operator ma jeden zespół
  z harmonogramami i jest tą samą osobą, która to zamawia. Wiersze zostają nietknięte,
  wyrażenia zostają te same.
- **`recurrence` odczytane z wyrażenia może nie zgadzać się z tym, co operator wpisał
  ręcznie w „Zaawansowane".** → Odczyt jest zawężony: wyrażenie mapuje się na rytm tylko
  wtedy, gdy jest dokładnie tym, co ten rytm generuje. Wszystko inne wraca jako `null`
  i jest pokazane jako wyrażenie.

## Migration Plan

Bez migracji bazy. Wiersze `schedules` zostają, `cron_expression` zostaje, zmienia się
wyłącznie strefa, w której moduł liczy kolejny moment.

Zapisane `next_fire_at` sprzed wdrożenia wciąż niesie moment policzony w UTC, więc pierwsze
wyzwolenie po wdrożeniu wypada tam, gdzie wypadało dotąd; każde następne jest już liczone
w strefie polskiej. Świadomie: przeliczanie wszystkich wierszy przy starcie byłoby zapisem
do cudzych harmonogramów wykonanym przez migrację, a różnica dotyczy jednego wyzwolenia.

Wycofanie: cofnięcie obrazu wystarcza — schemat się nie zmienił, a `recurrence` jest polem,
którego stary kod nie czyta. Harmonogram zapisany kreatorem zostaje w bazie zwykłym
wyrażeniem czasowym i działa dalej, znów w UTC.
