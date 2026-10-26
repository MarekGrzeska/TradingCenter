## Why

Lista uruchomień w zakładce Backtests na wąskim ekranie jest nieczytelna (zrzut operatora z 26.10.2026): nagłówki i
liczby zlewają się bez odstępów („72671,39%” to 7267 transakcji i 1,39% zwrotu), nazwy i zakresy łamią się w każdym
wierszu, trzy kolumny w R stoją puste dla strategii bez stopu, a każdy wiersz ma dwa nieopisane pola zaznaczenia, jedno
do porównania i drugie do usunięcia, które w ciemnym motywie wyglądają jak szare kwadraty.

## What Changes

- Jedno pole zaznaczenia na wiersz zamiast dwóch. Zaznaczyć można każde uruchomienie poza czekającym i liczonym.
  „Porównaj” działa, gdy zaznaczone są od dwóch do pięciu i wszystkie są zakończone; „Usuń” działa dla każdego
  zaznaczenia. Pasek nad listą mówi, dlaczego porównanie jest wyłączone.
- Lista układa się według szerokości miejsca, a nie ekranu: szeroka jest tabelą z odstępami i liczbami wyrównanymi do
  prawej, wąska jest kartą na uruchomienie (numer, strategia, stan, zakres, zlecający, metryki z nazwami).
- Kolumny w R znikają, gdy żadne uruchomienie na liście nie ma wyniku w R. Pole zaznaczenia dostaje kolor akcentu
  terminala.

## Capabilities

### New Capabilities
Brak.

### Modified Capabilities
- `terminal-strategies`: „Porównanie zaznaczonych uruchomień w Backtests” — zaznaczenie jest wspólne z usuwaniem, a
  porównanie wymaga, żeby wszystkie zaznaczone były zakończone.

`design.md` pominięty: jedyną decyzją jest wspólne zaznaczenie, opisane tutaj; reszta to układ ekranu.

## Impact

- `modules/terminal`: `RunsPanel.tsx`, `BacktestsView.tsx`, ich testy. Bez zmiany kontraktu, pakietu i danych.
