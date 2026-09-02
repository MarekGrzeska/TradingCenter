## Why

Moduł `strategy` powstał po to, żeby jego decyzja budziła zespół. Publikuje cztery narzędzia,
a jego README nazywa `pending_setups` „tym, co czytają wyzwalacze workbencha". Zmierzone
1 września 2026: workbench nie ma `STRATEGY_MCP_URL`, a w katalogach `agent/`, `teams/` i
`workbench/` słowo „strategy" nie pada ani razu. Decyzja rdzenia dociera dziś wyłącznie na
telefon operatora (`strategy-alerts`), a zespół, który miał się z nią spierać, nie ma jak się o
niej dowiedzieć.

Połowa szwu już istnieje, i to jest powód, dla którego ta zmiana jest mała: infrastruktura
`strategy` od `the-screen-is-mostly-refusals` nazywa tożsamość workbencha w obu miejscach —
`allowed_applications` i `TOOL_CALLER_APPLICATION_IDS` — więc drzwi są otwarte dla wołającego,
który nigdy nie zapukał. Brakuje drugiej połowy pary: ustawienia po stronie workbencha.

To jest zmiana OpenSpec z dwóch powodów mechanicznych: dotyka `infra/app-service.tf` i dodaje
wymaganie do `teams-triggers`.

## What Changes

- **Szósta para `STRATEGY_MCP_URL` / `STRATEGY_MCP_SCOPE` w workbenchu**, czytana przez obie
  powierzchnie na tych samych warunkach, co pięć poprzednich: adres i tożsamość albo pętla
  zwrotna, oba naraz odmową startu, brak adresu stanem wspieranym.
- **Żadnego nowego rodzaju wyzwalacza.** Wyzwalacz już nazywa narzędzie i ścieżkę pola, a zegar
  już pyta każdy skonfigurowany serwer, który z nich ogłasza tę nazwę. `pending_setups` z polem
  `pending` staje się źródłem warunku w chwili, w której serwer jest w rejestrze — ten sam
  przebieg, ten sam zapis wyzwoleń, ten sam czas martwy. Co zmienia się w kodzie, to rejestr,
  ustawienia i dwa komunikaty, które nazywały dwa serwery w dniu, w którym było ich pięć.
- **Infrastruktura**: dwa ustawienia w bloku workbencha. Po stronie `strategy` nic — obie listy
  już nazywają workbench.
- **Jeden test przez pętlę**: stand-in ogłaszający `pending_setups`, wyzwalacz `pending >= 1`,
  zespół budzi się dokładnie raz, a wiersze zużycia przed wyzwoleniem to zero.

## Capabilities

### Modified Capabilities

- `teams-triggers`: decyzja platformy strategii jest źródłem warunku, tą samą drogą, co każda
  inna wielkość — bez osobnego klienta i bez osobnego rodzaju wyzwalacza.

## Impact

- **Kod**: `workbench/config.py`, `agent/config.py`, `teams/config.py`,
  `agent/tools/registry.py`, `teams/tools/client.py`, `teams/scheduler/clock.py`,
  `teams/validation.py`, `.env.example`, `README.md` workbencha; `scripts/dev.py` i jego test;
  trzy testy wyliczające serwery i jeden nowy w `test_scheduler_triggers.py`.
- **Infrastruktura**: `infra/app-service.tf`, blok `workbench` — para ustawień. Operator:
  `apply` i restart. Kolejność jest tu łagodniejsza niż przy `polymarket-data`: brak ustawienia
  jest stanem wspieranym, więc obraz może wylądować przed `apply` bez przerwy w pracy. Do
  `apply` wyzwalacza nazywającego `pending_setups` nie da się zapisać — zapis odmawia, bo żaden
  skonfigurowany serwer nie ogłasza tej nazwy — i to jest właściwa odmowa, nie awaria.
- **Terminal**: nic. `TriggerIn` nie zmienia kształtu, `contract:check` nie ma czego zobaczyć.
- **Powierzchnia rozmowy** dostaje narzędzia strategii przy okazji, bo ustawienie jest jedno na
  proces — tak samo, jak dostała pięć poprzednich. Żadne wymaganie `agent-*` się nie zmienia.
- **Poza zakresem**: rysunek szwu w `docs/architecture.md`. Zdanie o nim stoi w README modułu
  `strategy` i tam jest od dziś prawdziwe.

`design.md` nie powstaje: jedyny wybór z alternatywą — szósty serwer w rejestrze czy osobny
klient platformy strategii — rozstrzyga istniejące wymaganie `teams-triggers` („Warunek jest
czytany narzędziami serwera narzędzi"), które drugiej drogi zabrania. `tasks.md` powstaje, bo
zmiana dotyka jedenastu plików w trzech miejscach repozytorium.
