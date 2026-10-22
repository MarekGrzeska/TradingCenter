## Why

Jak często pętla YouTube sprawdza kanały, ile filmów jedno wyszukiwanie tematu kieruje do przesiewu i co jaki czas temat
jest wyszukiwany — to dziś ustawienia procesu (`YOUTUBE_POLL_INTERVAL_SECONDS`, `_TOPIC_DEFAULT_INTERVAL_MINUTES`,
`_TOPIC_DEFAULT_MAX_VIDEOS`). Zmiana któregokolwiek to edycja `.env` na serwerze i wdrożenie, a operator chce to
robić z terminala, tak jak prompty.

## What Changes

- Nowa sekcja **Ustawienia** w zakładce YouTube terminala (obok Filmów, Kanałów, Tematów, Kandydatów i Promptów) z trzema
  wartościami: **odstęp między przebiegami pętli** (kanały, transkrypcje, odczyty, ogłoszenia), **domyślny odstęp
  wyszukiwania tematu** i **domyślna liczba filmów z jednego wyszukiwania tematu**.
- Wartości leżą w bazie (jeden wiersz). Dopóki operator niczego nie zapisał, obowiązują ustawienia procesu — brak wiersza
  jest działającą konfiguracją, nie błędem.
- Pętla czyta odstęp po każdym przebiegu. Zmiana działa od razu: odliczanie zaczyna się od końca ostatniego przebiegu
  z nową długością, bez restartu. Tętno pętli (`expected_seconds`) idzie za odstępem, żeby `stale` nie alarmowało po
  skróceniu ani nie milczało po wydłużeniu.
- Domyślne wartości tematu dotyczą tematów dopisywanych **bez własnych granic** (przez terminal i przez agenta).
  Tematy już na liście zachowują swoje.
- Granice: odstęp pętli 5–1440 min (kanały kosztują jednostkę dzienną każdy, więc krótszy odstęp zjadłby dzienny budżet
  źródła), odstęp tematu 15 min – 7 dni, filmów z wyszukiwania 1–20 — te same granice, które dziś stosuje dopisanie tematu.

Poza zakresem: odstęp osobny dla każdego kanału; edycja granic tematu już dopisanego; pozostałe limity pętli
(`discover_batch_limit`, dzienne budżety) — zostają ustawieniami procesu.

Pominięte artefakty: `design.md` (decyzje mieszczą się powyżej), `review.md` (bez migracji przepisujących dane — tabela
jest nowa i pusta). Delta spec to jedna nowa zdolność; zdolności zmieniane przez niezarchiwizowane `youtube-*` nie są
jeszcze w `openspec/specs/`, więc ich zapisy zmienią się przy archiwizacji w tej samej kolejności co zmiany, z których
powstały.

## Capabilities

### New Capabilities

- `youtube-data-settings`: ustawienia pętli i domyślne granice tematu jako dane edytowane przez operatora.

### Modified Capabilities

Brak w `openspec/specs/`.

## Impact

- `modules/workbench`: migracja `0005` w łańcuchu `youtube` (tabela `loop_settings`), `youtube_data/loop_settings.py`,
  `store.py`, `ingest.py`, `watchlist.py`, `contract.py`, `routers/settings.py`, README.
- `modules/terminal`: `contract.youtube.generated.ts` (skill `contract-sync`), `youtube/` (sekcja Ustawienia).
- Produkcja: migracja wykonuje się sama przy starcie; bez nowych sekretów i infrastruktury.
