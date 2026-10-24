## Why

Historia przebiegów wyszukiwania pokazuje sto najnowszych wpisów. Gdy temat jest szukany co kilka godzin, a pominięcia i porażki
zapisują się raz na dobę, to wystarczy na dni, nie na tygodnie — a operator, który pyta „co się działo we wtorek”, nie ma jak
tam dojść poza przewijaniem wszystkiego, co nowsze.

## What Changes

- `GET /topic-runs` przyjmuje opcjonalny zakres czasu `since` / `until`, tak jak `GET /videos`: znacznik bez strefy jest UTC,
  początek jest włączony, koniec wyłączony, a zakres odwrócony lub pusty jest odmawiany z powodem. Zakres łączy się z filtrem po temacie.
- Widok Historia w terminalu dostaje pola **Od** i **Do** (dni w czasie lokalnym operatora, oba końce włącznie) i przycisk
  czyszczenia; bez nich widok działa jak dotąd.

Poza zakresem: zmiana limitu stu wpisów; filtr po wyniku (`failed`, `skipped`); stronicowanie.

Pominięte artefakty: `design.md` — nie ma decyzji z realną alternatywą, a konwencja zakresu jest z `/videos`.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `youtube-data-topic-runs`: odczyt historii przyjmuje zakres czasu; widok w terminalu pozwala go wybrać.

## Impact

- `modules/workbench`: `youtube_data/store.py` (`list_runs`), `routers/runs.py`, `views.py` (jeden publiczny pomocnik), README.
- `modules/terminal`: `contract.youtube.generated.ts` (skill `contract-sync`), `youtube/youtubeApi.ts`, `RunsPanel.tsx`.
- Produkcja: bez migracji, sekretów i infrastruktury; odczyt po istniejących indeksach.
