## Why

Prompt zapisany przez operatora przez `PUT /prompt` jest po cichu przykrywany przez
następne wdrożenie, które niesie migrację zasiewającą prompt. Zreprodukowane na prawdziwej
bazie, nie wywnioskowane z kodu.

Składają się na to dwie rzeczy, i obie są potrzebne, żeby to zrozumieć:

**Kolizja wersji jest gwarantowana, nie możliwa.** Migracje zasiewają `v4 → v5 → … → v11`,
każda o jeden więcej. `_next_prompt_version` robi **to samo `+1` od najnowszej**. Wersja,
którą operator dostaje zapisując raz, jest więc *zawsze dokładnie tą*, której użyje
następna migracja zasiewająca. `prompt_revisions` nie ma unikatu na `version`, więc oba
wiersze wchodzą bez słowa.

**A pod tym leży rzecz ogólniejsza.** `latest_prompt_revision` to `ORDER BY id DESC LIMIT 1`
— „najnowszy" prompt jest rozstrzygany **kolejnością wstawienia, nie numerem wersji**.
Zasiew z migracji zawsze ma wyższe `id` niż wcześniejszy zapis operatora, więc wygrywa
nawet wtedy, gdy jego numer wersji jest niższy. Kolizja to tylko najostrzejszy przypadek.

Skutek uboczny wart nazwania: `downgrade()` każdej migracji zasiewającej kasuje
`WHERE version = _SEED_VERSION`. Przy kolizji skasowałby **oba** wiersze — razem z tekstem,
który napisał operator.

Nic tego nie sprawdzało. `agent-prompt-management` żąda, żeby zapis nigdy nie nadpisywał
istniejącej wersji, i formalnie to jest spełnione — nowy wiersz naprawdę powstaje. Nie
powstało wymaganie o rzeczy, która okazała się naprawdę potrzebna: że **zasiew nie
przykrywa tego, co napisał człowiek**.

## What Changes

- `prompt_revisions` dostaje kolumnę **`source`** (`seed` | `operator`) — dotąd nie dało się
  odróżnić wiersza wstawionego przez migrację od wiersza zapisanego przez operatora, a cała
  poprawka na tym rozróżnieniu stoi.
- **Migracja zasiewająca wstawia się tylko wtedy, gdy najnowszy wiersz sam jest zasiewem.**
  Gdy operator cokolwiek zapisał, nowy zasiew go nie przykrywa. Reguła jest jednym `WHERE`
  w `INSERT ... SELECT`, wspólnym helperem, żeby następna migracja nie pisała go od nowa.
- **Unikat na `version`** — po deduplikacji w tej samej migracji, więc nie może wywrócić
  startu modułu. Kolejność jest tu load-bearing: migracje biegną w `lifespan`, więc
  ograniczenie, które pada, to moduł, który nie wstaje.
- `create_prompt_revision` zapisuje `source = 'operator'`.

**Czego nie zmieniamy.** Migracje `0003`–`0012` zostają dokładnie takie, jakie są —
są już zaaplikowane wszędzie, a przepisywanie zaaplikowanej migracji jest gorsze od błędu,
który naprawia. Poprawka działa od następnej migracji zasiewającej. Domyślny prompt zostaje
w migracji, nie wraca do kodu: to była druga rozważana droga i jest osobną decyzją o tym,
czym prompt *jest*, a nie naprawą tego, że ginie.

## Capabilities

### Modified Capabilities

`agent-prompt-management` — jedno nowe wymaganie: zasiew nie przykrywa zapisu operatora.
Istniejące wymagania zostają bez zmian, łącznie ze scenariuszem „odczyt zwraca treść
zasianą przy migracji i wersję v4", który nadal jest prawdą dla świeżej bazy.

## Impact

**Kod.** `agent`: nowa migracja, `store/prompt.py`, `models.py` (`PromptRevision.source`),
helper zasiewu dla przyszłych migracji.

**Baza.** Kolumna, backfill i unikat na `prompt_revisions`. Backfill jest wyprowadzalny,
nie zgadywany — patrz `design.md`, D2.

**Czego nie dotyka.** Żadnego kontraktu na drucie, żadnego innego modułu, `infra/` ani
terminala.

## Artefakty tej zmiany

`design.md` — **tak**: dwie decyzje z alternatywami, z których jedna dotyczy danych, których
nie da się odzyskać. `tasks.md` — **tak**. `review.md` — **do decyzji po wdrożeniu**.
