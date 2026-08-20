## Why

Odpowiedź agenta, raz zaczęta, nie ma dziś końca innego niż własny: operator, który widzi
po dwóch zdaniach, że model odpowiada nie na to pytanie, może zamknąć panel albo
przeładować terminal — i tura poleci dalej, do końca, płacona i zapisana w całości.
Jest to zachowanie celowe (`agent-chat`, "Wołający rozłącza się w trakcie"), postawione
przeciwko zerwanemu łączu, i to samo zachowanie zabiera operatorowi jedyny hamulec.
Brakuje odróżnienia dwóch rzeczy, które dziś wyglądają tak samo: **wołający zniknął** —
tura ma się dokończyć — i **operator powiedział dość** — tura ma się skończyć.

## What Changes

- Moduł dostaje sposób na zatrzymanie tury, która trwa: żądanie zatrzymania kierowane do
  konkretnej rozmowy, odróżnione od porzucenia strumienia.
- Tura zatrzymana kończy się na tym, co model zdążył wypowiedzieć. Częściowa wypowiedź
  jest zapisana w transkrypcie z **własnym oznaczeniem** — odróżnialnym od wypowiedzi
  urwanej błędem modelu, którą moduł umie oznaczać dziś.
- Zużycie MUST zostać zapisane tak samo jak w turze dokończonej: pieniądze zostały wydane
  i rachunek nie ma o tym milczeć.
- Strumień domyka się zdarzeniem oznaczającym zatrzymanie — odróżnialnym od domknięcia
  odpowiedzi i od błędu. Wołający, który tego zdarzenia nie zna, MUST móc je pominąć.
- Zatrzymanie w chwili, gdy trwa wywołanie narzędzia, działa na najbliższej granicy:
  wywołanie, które już poszło, dochodzi do końca i trafia do transkryptu, a następna runda
  modelu już nie startuje. Wywołanie wysłane MUST NOT zostać porzucone bez zapisu — po tej
  stronie są narzędzia, które piszą.
- Terminal dostaje przycisk Stop w miejscu, w którym w czasie tury i tak nie da się wysłać
  następnego pytania, oraz mówi w transkrypcie, że to operator przerwał, a nie model padł.

## Capabilities

### New Capabilities

Brak — zatrzymanie jest brakującym zakończeniem tury, którą oba istniejące zbiory wymagań
już opisują, a nie osobną zdolnością.

### Modified Capabilities

- `agent-chat`: zatrzymanie tury na żądanie operatora — trzecie zakończenie strumienia
  obok domknięcia i błędu, zapis częściowej wypowiedzi z własnym oznaczeniem, zapis
  zużycia, granica przy trwającym wywołaniu narzędzia.
- `terminal-agent-chat`: operator zatrzymuje odpowiedź z panelu i widzi w transkrypcie, że
  została zatrzymana.

## Impact

- `modules/workbench`: `agent/routers/sessions.py` (trasa zatrzymania, rejestr trwających
  tur, nowe zdarzenie strumienia), `agent/turn.py` (granica zatrzymania, zapis wypowiedzi
  i zużycia), `agent/graph.py` (przerwanie między rundami), `agent/contract.py` i
  `agent/models.py` (oznaczenie wypowiedzi), `agent/store/messages.py`, migracja bazy
  `agent`.
- `modules/terminal`: `agent/AgentChat.tsx` (przycisk), `agent/agentChatStore.ts` (stan
  tury i zatrzymanie), `agent/agentApi.ts` (wywołanie trasy), `agent/stream.ts` (nowe
  zdarzenie), `data/types.ts`. Kontrakt rozmowy nie jest generowany — po tej stronie
  pilnują go własne testy terminala, nie `pnpm contract:generate`.
- Zakłada jeden proces obsługujący rozmowy: plan App Service ma jednego workera
  (`infra/app-service.tf`). Założenie jest w `design.md` wraz z tym, co przestaje działać,
  gdy przestanie być prawdziwe.
- `docs/` bez zmian. `review.md` powstanie po wykonaniu, nie teraz.
