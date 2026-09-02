# A decision and a report can be read

## Why

`the-screen-is-mostly-refusals` zbudowało podstronę Strategie i poszło do archiwum 2 września
2026 bez dwóch wymagań, które od początku czekały na coś do obejrzenia: podglądu odczytów, na
których stanęła decyzja, i widoku zachowanych raportów backtestu. W dniu archiwizacji platforma
nie miała jeszcze ani jednej decyzji o wejściu, ani jednego raportu — widoku nad pustym zbiorem
nie da się ani sprawdzić, ani zaprojektować uczciwie. Spec główny nie niesie wymagania bez
ekranu, więc oba wymagania czekają tutaj, w brzmieniu, w jakim były w tamtej delcie.

To jest zmiana OpenSpec, bo dodaje dwa wymagania do `terminal-strategy`.

## What Changes

- **Szczegóły decyzji sięgają odczytów.** Poziomy, kierunek i stosunek zysku do ryzyka są już w
  wierszu listy; dochodzi podgląd faktów, na których decyzja stanęła, i wersji parametrów, którą
  została policzona.
- **Widok zachowanych raportów backtestu** z modelem kosztów, wersją parametrów i zakresem danych.
  Klient terminala czyta już `/backtests`; brakuje ekranu. Bez akcji uruchamiającej przebieg —
  to jest komenda i ma nią zostać.
- Bez zmian w `modules/strategy` i bez zmian w kontrakcie: obie trasy istnieją.

Warunek wejścia: pierwsza decyzja o wejściu i pierwszy raport na produkcji. Wcześniej ta zmiana
stoi celowo.

## Capabilities

### Modified Capabilities

- `terminal-strategy`: dwa nowe wymagania — „Decyzję da się przeczytać do tego, na czym
  stanęła" i „Raporty backtestu są czytane, a nie uruchamiane".

## Impact

- `modules/terminal/src/strategy/**`: podgląd odczytów przy decyzji, widok raportów.
- `design.md` pominięte celowo: kształt podstrony jest w archiwum
  `the-screen-is-mostly-refusals`, a jej decyzje projektowe — odmowy jako treść, typy z
  generatora, jeden zakres na moduł — stoją bez zmian.
