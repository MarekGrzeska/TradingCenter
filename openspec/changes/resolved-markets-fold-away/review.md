## Verdict

Weszło w całości i jest wdrożone. Rozstrzygnięte rynki chowają się za licznikiem, a pokazane
świadomie nie mają okien.

Ta druga połowa jest ważniejsza od pierwszej i to jest jedyny wniosek warty wyniesienia:
zwijanie usuwa hałas z ekranu, ale **hałas był w kształcie odczytu**. Rozstrzygnięty rynek
stoi na 0% i 100%, więc każde okno wychodziło `0.0 pp` albo `no coverage` — pierwsze czyta się
jako „rynek się nie ruszył", drugie jako „archiwum ma dziurę", a prawda jest trzecia i żadne
z nich jej nie mówiło. To dokładnie ta pomyłka, przed którą ta zakładka broni się wszędzie
indziej.

## Verified

```
terminal   tsc -b --noEmit    (czysto)
           eslint .           (czysto)
           vitest run         765 passed
```

Na wydanym bundlu produkcyjnym:

```
"resolved market"                          obecne
"settled on"                               obecne
"Every market of this event has resolved"  obecne
"what was collected is still here"         obecne
```

Pięć scenariuszy ze specyfikacji ma po teście, w tym ten, który mówi, że zwinięcie **nie jest
usunięciem**: seria rozstrzygniętego rynku zostaje osiągalna w wybieraku wykresu. Test asertuje
to dopasowaniem dokładnym, bo wybierak wymienia „August 6 · Yes" i luźne dopasowanie
przechodziłoby niezależnie od tego, czy wiersz się schował.

## Findings

Nic. Przegląd tej zmiany nie znalazł usterki — jest mała, dotyka jednego pliku widoku i nie
rusza ani modułu, ani kontraktu, ani infrastruktury.

Jedna decyzja warta zapisania, bo wygląda na przeoczenie i nie jest: wybierak wyniku
w wykresie **dalej wymienia rynki rozstrzygnięte**. Ich historia jest tym, czego dostawca nie
odda, więc jest najcenniejszym, a nie najmniej ważnym, co archiwum trzyma. Chowa się wiersz,
nie dane.
