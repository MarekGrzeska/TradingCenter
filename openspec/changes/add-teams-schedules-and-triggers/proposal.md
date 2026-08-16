## Why

Zespół z fazy 1 pracuje wyłącznie wtedy, gdy operator kliknie „uruchom". To wystarcza, żeby
sprawdzić, czy definiowalny na froncie zespół produkuje sensowne przebiegi — i nie wystarcza
do niczego, co ma być mierzone w czasie. Eksperyment „czy ten układ ról jest lepszy od tamtego"
wymaga powtarzalności: tego samego zespołu, na tej samej rewizji, o tej samej porze, przez
tydzień. Dziś powtarzalność jest funkcją tego, czy operator siedział przed terminalem o 9:30.

Druga rzecz, której brakuje, jest ostrzejsza: rynek nie pyta o godzinę. Zespół, który ma coś
powiedzieć o wybiciu, musi ruszyć wtedy, gdy wybicie nastąpiło, a nie przy najbliższej wizycie
człowieka.

## What Changes

- **Harmonogram jako dana zespołu**: nowa tabela `schedules` — wyrażenie cron w UTC, właściciel
  skopiowany w momencie zapisu, wskazanie rewizji i flaga włączenia. Moduł budzi się sam
  i uruchamia przebieg bez wołającego z przeglądarki.
- **Harmonogram wskazuje rewizję przypiętą, nie „najnowszą"** — domyślnie. Tryb `latest` istnieje,
  ale jest jawnym wyborem operatora, nie zachowaniem domyślnym.
- **Wyzwalacz warunkowy** (`triggers`): warunek na instrumencie czytany **tymi samymi narzędziami
  `market-mcp`, którymi czyta agent** — bez nowej krawędzi do `market-data`, bez własnych
  wskaźników. Wyzwalacz reaguje na **zbocze** (warunek stał się prawdą), nie na stan, i ma
  własny czas martwy. Ocena warunku MUST NOT kosztować tokenów modelu.
- **Historia wyzwoleń** (`schedule_fires`): osobna tabela, jeden wiersz na każde wyzwolenie —
  także na takie, które przebiegu **nie** uruchomiło. Powód nieuruchomienia (poprzedni przebieg
  wciąż trwa, wyczerpana granica dobowa, rewizja nie do uruchomienia) jest tam zapisany.
- **Zasady pracy bez nadzoru**: pominięte wyzwolenia zwijają się do jednego, przebieg nakładający
  się na poprzedni jest pomijany, a harmonogram po serii nieudanych przebiegów wyłącza się sam
  i mówi dlaczego.
- **Harmonogram nad rewizją z narzędziami zapisującymi jest odmawiany** bez jawnego potwierdzenia
  operatora. Dziś takich narzędzi nie ma — wymaganie jest spełnione w próżni i staje się nośne
  w chwili, w której faza 2 je doda.
- **Terminal**: panel harmonogramów i wyzwalaczy w zakładce `Teams` — lista, edytor, podgląd
  najbliższych wyzwoleń liczony **przez moduł**, oraz historia. Terminal MUST NOT nosić własnego
  parsera cron.
- **Infrastruktura**: `SCHEDULER_ENABLED` w ustawieniach aplikacji, żeby dało się zatrzymać
  budzenie się modułu bez wdrożenia nowego obrazu.

**Poza zakresem, świadomie:** narzędzia tradingowe i dostęp do `capital-gateway` (faza 2 —
powstaje równolegle), analityka porównawcza rewizji i automatyczne układanie grafu (faza 4),
strefy czasowe inne niż UTC, powiadomienia o wyniku przebiegu poza terminalem.

**Praca równoległa z fazą 2.** Obie fazy wychodzą z tego samego przodka i żadna nie zależy od
kodu drugiej. Punkty styku są znane i wyliczone w `design.md` („Punkty styku z fazą 2");
najważniejsza konsekwencja dla zakresu jest tutaj: **ta zmiana nie zmienia ani jednej kolumny
w tabelach fazy 1** — dokłada trzy nowe tabele, więc jej rewizja Alembica jest przemienna
z rewizją fazy 2 i kolejność scalania nie ma znaczenia.

## Capabilities

### New Capabilities
- `teams-schedules`: czym jest harmonogram, do kogo należy, którą rewizję uruchamia, kiedy
  wyzwolenie zostaje pominięte i co zostaje po nim zapisane.
- `teams-triggers`: warunek na rynku jako wyzwalacz przebiegu — skąd moduł bierze wartość, co
  znaczy zbocze zamiast stanu, czas martwy, i czym różni się odmowa od niedostępności.
- `terminal-teams-schedules`: panel operatora — układanie harmonogramu i wyzwalacza, podgląd
  najbliższych wyzwoleń i historia tego, co się wydarzyło bez patrzenia.

### Modified Capabilities

Żadnej — i to jest wynik sprawdzenia, nie założenie. Wymagania fazy 1 (`teams-runs`,
`teams-usage`, `teams-browser-access`, `terminal-teams`) leżą wciąż w zmianie
`add-teams-module`, nie w `openspec/specs/`, więc delty do nich nie ma do czego przyłożyć.
Rzeczy, które wyglądają na zmianę tamtych wymagań, nią nie są: przebieg uruchomiony
z harmonogramu jest zwykłym przebiegiem — ta sama tabela, ten sam ślad, ten sam limit kosztu —
a wszystko, co go odróżnia, jest zapisane po stronie harmonogramu.

## Impact

**Nowy kod:** `modules/teams/teams/scheduler/` (zegar, przejęcie wyzwolenia, ocena warunku),
`routers/schedules.py`, migracja `modules/teams/migrations/versions/*_schedules.py` — trzy
tabele: `schedules`, `triggers`, `schedule_fires`. Nowa zależność modułu: `croniter`.

**Zmieniany kod:** `teams/contract.py` (modele harmonogramu, wyzwalacza i historii — dopisywane
na końcu pliku), `teams/config.py` (ustawienia `SCHEDULER_*`), `teams/app.py` (zegar startuje
i gaśnie w `lifespan`, jeden `include_router`), `teams/store.py` (zapytania nowych tabel).

**Terminal:** `src/teams/SchedulePanel.tsx` i sąsiedzi jako nowe pliki, jedna linia montująca
w `TeamsView.tsx`, `src/data/contract.teams.generated.ts` przegenerowany (`pnpm
contract:generate`, nigdy ręcznie).

**Infrastruktura:** `infra/app-service.tf` — jedno ustawienie aplikacji. `always_on` jest już
włączone, więc zegar w procesie nie wymaga nic ponadto.

**Bez zmian:** `capital-gateway`, `market-data`, `market-mcp` i `agent` nie zmieniają ani wiersza.
`market-mcp` dostaje więcej wywołań tych samych narzędzi — z tej samej tożsamości, co dziś.
