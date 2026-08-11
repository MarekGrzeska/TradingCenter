## Why

Terminal rysuje surowe świece i nic poza tym. Każda analiza — od średniej po położenie ceny
w zakresie — dzieje się dziś w głowie operatora albo w cudzej platformie, a archiwum jest
jedynym miejscem, w którym policzenie tego **raz i tak samo dla każdego konsumenta** jest
w ogóle możliwe: ono jest właścicielem świec.

Produktem tej zmiany jest powtarzalność, nie liczba wskaźników. Ta sama para, rozdzielczość
i zakres mają dawać tę samą wartość dziś, po restarcie i za pół roku — inaczej wskaźnik nie
nadaje się ani do decyzji, ani do przyszłego backtestu.

## What Changes

- Nowy obszar w `market-data`: jądro liczące, katalog wskaźników i router `/indicators`.
  Bez własnego magazynu i bez migracji — wskaźniki liczą się przy odczycie.
- **Katalog jest danymi**: terminal buduje wybierak z odpowiedzi modułu, więc kolejny
  wskaźnik nie wymaga zmiany w terminalu. Wymaga jej dopiero nowy *sposób rysowania*.
- Cztery kształty wyjścia od początku: linie, markery, strefy, poziomy. Etap pierwszy
  produkuje tylko linie, ale pozostałe trzy istnieją w modelu — dołożenie ich później
  byłoby zmianą łamiącą.
- Kurowany zestaw ~50 pozycji zamiast pełnego katalogu z researchu: ATR i pochodne, pełna
  geometria świecy, położenie w zakresie, estymatory zmienności z OHLC, miary reżimu,
  ~10 średnich, ~8 oscylatorów, wstęgi, punkty zwrotne, poziomy z wyższego interwału,
  skupiska ekstremów, luki cenowe, okna sesji i profil czasowy.
- **Rozgrzewka jest jawna i wyliczona**, nie przyjęta na oko: moduł czyta więcej świec, niż
  zapytano, i mówi, dokąd sięgnął oraz czy wartość jest już ustabilizowana.
- Sufit żądania: iloczyn świec i linii, powyżej którego moduł odmawia, zamiast blokować
  pętlę zdarzeń dzieloną ze strumieniem świec.
- Terminal: nakładki na panelu ceny, osobne panele oscylatorów, odczyt wartości pod
  kursorem, wybór wskaźników zapamiętany w slocie siatki.
- **Nie-cel, zapisany świadomie:** żaden wskaźnik nie orzeka. Moduł podaje miary
  i geometrię (`bar_range_atr`, `last_swing_high`, luka cenowa); pojęcia jednej szkoły
  — order block, break of structure, sweep — składa z nich przyszły moduł strategii.
  Próg jest decyzją konsumenta, nie stałą w kontrakcie.
- **Nie-cel:** wskaźniki wolumenowe. Wolumen świec pochodnych jest w tym archiwum
  strukturalnie pusty (`rollups.py`), a nie tylko wątpliwy.
- **Nie-cel:** wskaźniki relacyjne wymagające drugiego instrumentu (korelacja, beta,
  iloraz, SMT). Liczymy zawsze na jednej serii.

Nic się nie psuje: same nowe zasoby, istniejące odpowiedzi bez zmian.

Realizacja jest przyrostowa. Zmiana zostaje otwarta przez wszystkie etapy, a każdy z nich
wchodzi osobno na gałąź `add-technical-indicators`; do `main` trafia dopiero całość, po
lokalnym przetestowaniu i review.

## Capabilities

### New Capabilities

- `market-data-indicators`: obliczanie wskaźników na serii archiwum i kontrakt, którym są
  publikowane — determinizm, rozgrzewka, katalog, kształty wyjścia, sufit żądania.
  Kontrakt trzymany razem z obliczeniem, a nie doklejony do `market-data-api`: poza
  wskaźnikami nie ma on żadnego znaczenia, a tamta spec opisuje czytanie świec
  i zarządzanie zbieraniem.

### Modified Capabilities

- `terminal-chart`: wykres rysuje wskaźniki wybrane przez operatora — nakładki, osobne
  panele, markery i strefy — i podaje ich wartości pod kursorem obok OHLC.
- `terminal-grid`: slot pamięta własny zestaw wskaźników, tak jak pamięta instrument
  i interwał.

## Impact

- `modules/market-data`: nowy pakiet `market_data/indicators/`, nowy router, nowe modele
  w `market_data/contract.py`. Nowa zależność runtime: `numpy`. Bez migracji, bez zmian
  w `models.py`, `store.py` i `hub.py`.
- `modules/terminal`: `src/data/contract.generated.ts` do przegenerowania, nowy adapter
  w warstwie danych, nowe prymitywy rysowania (strefy, promienie, profil), rozszerzony
  stan slotu w `gridStore`.
- CI: zmiana w `market_data/contract.py` uruchamia też job terminala — to jest zamierzone.
- `infra/`: bez zmian. Brak nowego kontenera i brak zmiany SKU planu.
- Podstawa: `docs/wskazniki-techniczne.html` (research), `docs/wskazniki-plan-wdrozenia.html`
  (plan etapów).
