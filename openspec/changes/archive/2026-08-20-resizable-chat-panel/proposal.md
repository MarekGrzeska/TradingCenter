## Why

Panel agenta ma jedną szerokość, wpisaną w kod (`w-115` w `AgentChat.tsx`), i ta jedna
szerokość obsługuje dwie różne prace. Czytanie odpowiedzi z tabelą albo z kodem chce
panelu szerszego; pilnowanie wykresu w trakcie rozmowy chce go węższego. Dziś jedynym
ruchem operatora jest zwinąć panel do zera i rozwinąć z powrotem — wybór między „całość
albo nic" tam, gdzie potrzebna jest miara.

## What Changes

- Krawędź panelu staje się chwytem: operator ciągnie ją i zabiera albo oddaje szerokość
  temu, co jest po lewej — zakładce, nie warstwie pod panelem, bo panel odsuwa treść, a
  nie ją zakrywa.
- Szerokość MUST przeżyć przeładowanie terminala, tak jak przeżywa je stan zwinięcia.
- Szerokość MUST być ograniczona z obu stron: panel węższy od własnego nagłówka i panel
  zabierający cały ekran to dwa sposoby na to samo — zgubić drugą połowę terminala bez
  drogi powrotnej.
- Chwyt MUST być osiągalny klawiaturą, nie tylko myszą.

## Capabilities

### New Capabilities

Brak — to jest miara dołożona do panelu, który już ma swój zbiór wymagań.

### Modified Capabilities

- `terminal-agent-chat`: operator ustawia szerokość panelu, ustawienie przeżywa
  przeładowanie, a panel oddaje i zabiera szerokość zakładce zamiast ją zakrywać.

## Impact

- `modules/terminal`: `agent/AgentChat.tsx` (chwyt i szerokość), `agent/agentChatStore.ts`
  (szerokość w stanie i w `localStorage`, obok stanu zwinięcia), `app/Shell.tsx`
  (potwierdzenie, że kolumna oddaje szerokość sąsiadowi).
- Wykres nie wymaga niczego: `ResizeObserver` w `useChartInstance` już bierze nową
  szerokość, tak jak bierze ją przy zwijaniu panelu.
- Brak zmian w module, w kontrakcie i w infrastrukturze. Bez migracji.
- `design.md` powstanie: jest jedna decyzja z alternatywami — gdzie mieszka szerokość i co
  dokładnie oddaje miejsce. `review.md` po wykonaniu.
