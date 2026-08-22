## Why

Siedem okien zmiany (5m, 15m, 1h, 4h, 12h, 24h, 7d) zostało wybranych, zanim ktokolwiek
zobaczył je na ekranie. Po pierwszym dniu używania zakładki operator nazwał pięć, które
faktycznie czyta: **5m, 1h, 4h, 24h, 7d**. Pozostałe dwa nie są niedokładne — są nieczytane.

Kosztują przy tym w każdym odczycie. Każde okno to osobne zapytanie o punkt bazowy, na wynik,
więc wydarzenie o dwóch wynikach to czternaście zapytań tam, gdzie wystarczy dziesięć, a
zmierzone wydarzenie o 128 rynkach — setki. Kontrakt obiecuje przy tym coś, czego nikt nie
chce, a obietnica w kontrakcie jest zobowiązaniem: dopóki tam stoi, konsument ma prawo się
na niej oprzeć.

## What Changes

- **Zestaw okien schodzi z siedmiu do pięciu: 5m, 1h, 4h, 24h, 7d.** Znikają 15m i 12h.
- **BREAKING dla konsumenta kontraktu**, w praktyce nikogo poza terminalem: `WindowChange.window`
  przestaje przyjmować dwie wartości. Terminal jest jedynym czytelnikiem tej trasy i idzie
  w tej samej zmianie; narzędzie `get_price_changes` oddaje to, co moduł liczy, więc model
  dostaje pięć okien bez zmiany w opisie narzędzia.
- **Sufit tolerancji zostaje nietknięty.** `MIN_TOLERANCE` wynosi trzy minuty i istnieje ze
  względu na okno **5-minutowe**, które zostaje — usunięcie 15m i 12h nie rusza ani jednej
  z mierzonych wartości.
- Wybór pięciu nie jest symetryczny i to jest celowe: gęsto przy teraz (5m, 1h, 4h), rzadko
  dalej (24h, 7d). Rynek predykcyjny rusza się wolno, więc drugie okno kwadransowe mówi to,
  co pierwsze, a półdobowe leży między dwoma, które i tak się czyta.

**Poza zakresem, choć jedzie tą samą gałęzią:** dwie poprawki UI z tej samej rundy uwag —
zwijanie wydarzenia do jednego wiersza i graficzne przedstawienie prawdopodobieństwa zamiast
samego tekstu. Nie dokładają wymagania (`terminal-shell` i `terminal-polymarket` mówią, co
zakładka MUST pokazywać, nie jak to wygląda), więc jadą zwykłą ścieżką i są tu wymienione
tylko po to, żeby wspólny PR nie wyglądał na szerszy niż zmiana, którą opisuje ten dokument.

**Bez `design.md`.** Nie ma tu decyzji z alternatywami do zważenia: które pięć okien, jest
odpowiedzią operatora po dniu używania, a nie wnioskiem z pomiaru, i zapisanie jej w osobnym
dokumencie byłoby przepisaniem jednego zdania z „What Changes".

## Capabilities

### Modified Capabilities

- `polymarket-data-api`: wymaganie „Zmiany w oknach są liczone przy odczycie" wylicza siedem
  okien z nazwy i jeden z jego scenariuszy mówi „w siedmiu oknach". Liczba i lista MUST zejść
  do pięciu. Reszta wymagania — liczenie przy odczycie, brak nazywający przyczynę zamiast zera,
  tolerancja i moment punktu bazowego — zostaje słowo w słowo, bo nic z tego nie zależało od
  tego, ile okien jest.

**Czego ta zmiana w specyfikacjach nie rusza, choć wyglądało, że ruszy.** `terminal-polymarket`
mówi, że widok pokazuje zmianę „w oknach, których dostarcza kontrakt modułu" — właśnie po to,
żeby liczba okien nie była zapisana w dwóch miejscach. Widok podąża za kontraktem bez jednego
słowa zmiany, i to jest zasługa tamtego sformułowania, nie zbieg okoliczności.
`polymarket-data-tools` nie wymienia okien z nazwy.

## Impact

**Moduł.** `polymarket_data/changes.py` — dwie linie z krotki `WINDOWS`. `contract.py` —
`Literal` bez dwóch wartości. Testy zmian liczą dziś siedem.

**Kontrakt terminala.** `contract.polymarket.generated.ts` regenerowany; `WindowName`
w `polymarketApi.ts` jest z niego wyprowadzony, więc zawęża się sam i `tsc` wskaże każde
miejsce, które zakładało siedem.

**Czego ta zmiana nie rusza.** Bazy, zbierania, próbkowania, uzupełniania przeszłości,
infrastruktury ani żadnego innego modułu. Nie ma migracji: okna nie są niczym przechowywanym.
