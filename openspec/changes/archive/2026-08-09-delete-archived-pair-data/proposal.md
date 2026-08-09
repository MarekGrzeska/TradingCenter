## Why

Zdjęcie pary z archiwizowania nie kasuje dziś niczego: `untrack` przestawia wiersz na `untracked`,
a świece i `coverage_ranges` zostają. Operator, który zdjął instrument i dodał go ponownie z
krótszym zakresem, nadal widzi w panelu zasięg starych danych — i słusznie, bo one tam są. Nie ma
dziś żadnej drogi, którą operator mógłby usunąć zebrane dane; jedyną jest wejście do bazy ręcznie.

Skutek jest gorszy niż mylący napis. Zostawione pokrycie sprawia, że kolejne zlecenie uznaje ten
zakres za już pobrany i nie ściąga nic — operator, który chciał zacząć zbieranie od nowa, dostaje
stare dane i puste zlecenie, bez śladu, dlaczego.

## What Changes

- **BREAKING** Przycisk `Stop` w zakładce `Instruments` znika i zastępuje go `Delete`. Jedna
  operacja: przestaje zbierać **oraz** kasuje świece i pokrycie pary. Dotyczy obu wariantów —
  pojedynczego interwału i całego instrumentu.
- **BREAKING** `DELETE /pairs/{symbol}` przestaje być samym zaprzestaniem zbierania. Kasuje świece
  i zakresy pokrycia pary i odpowiada liczbą usuniętych świec. Konsument sprzed tej zmiany dostaje
  po tym żądaniu inny skutek niż dotychczas, więc zmiana jest łamiąca mimo niezmienionej ścieżki.
- Potwierdzenie w terminalu mówi, że dane zostaną skasowane i że jest to nieodwracalne. Dotychczasowe
  zapewnienie „zebrane świece pozostają w archiwum" znika — po tej zmianie byłoby nieprawdą.
- Skasowanie zostaje odnotowane trwale i pokazane w zakładce `Data History` jako osobny rodzaj
  wpisu: kiedy, jaka para, ile świec zniknęło. Zlecenia dociągania tej pary zostają w historii —
  bez nich nie dałoby się zobaczyć, dlaczego zasięg danych się cofnął.
- Zasada, którą ta zmiana odwraca, zostaje odwrócona **w miejscu jej zapisania**, a nie obudowana
  wyjątkiem: w spec `market-data-tracking`, w spec `terminal-data-manager`, w kontrakcie i w README
  obu modułów. To, co z niej zostaje, brzmi teraz: archiwum MUST NOT kasować danych samo z siebie
  ani przy zmianie konfiguracji — kasuje wyłącznie na jawne, potwierdzone żądanie operatora.

## Capabilities

### New Capabilities

Brak — zmiana odwraca i rozszerza zachowania już opisane.

### Modified Capabilities

- `market-data-tracking`: usunięcie pary przestaje zachowywać świece i zaczyna je kasować wraz z
  pokryciem; skasowanie jest trwale odnotowane
- `market-data-api`: `DELETE /pairs` kasuje dane i odpowiada liczbą usuniętych świec; odnotowane
  skasowania są odczytywalne przez kontrakt
- `market-data-store`: skasowanie danych pary zdejmuje też jej zakresy pokrycia, w jednej
  niepodzielnej operacji
- `terminal-data-manager`: `Stop` zastąpione przez `Delete`, potwierdzenie mówi o skasowaniu i o
  jego nieodwracalności
- `terminal-collection-history`: skasowanie widoczne w historii obok dociągnięć

## Impact

**Zależność.** Zmiana zakłada, że `rework-instrument-collection` zostanie zarchiwizowany wcześniej:
stamtąd pochodzi zakładka `Data History` (`terminal-collection-history`), zdejmowanie osobno
interwału i całego instrumentu oraz pojęcie zlecenia, do którego dokładany jest nowy rodzaj wpisu.

**market-data**: `tracking.untrack` i jego docstring, nowa ścieżka kasowania świec i
`coverage_ranges` w jednej transakcji, migracja pod tabelę odnotowanych skasowań, `DELETE /pairs`
i jego model odpowiedzi, odczyt historii w kontrakcie, README.

**terminal**: `InstrumentsView` (przycisk i oba potwierdzenia), warstwa danych (`ArchiveAdmin`,
`archive.ts`), widok `Data History` o nowy rodzaj wiersza, README.

**Nieodwracalność.** Operacja usuwa dane, których nikt nie odtworzy bez ponownego pobrania z
providera — a to, czego provider już nie ma, nie wróci wcale. Potwierdzenie jest jedynym
zabezpieczeniem i musi mówić wprost, co znika.
