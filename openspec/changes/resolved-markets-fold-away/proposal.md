## Why

Wydarzenie o rynkach datowanych — „August 2", „August 3", … — rozstrzyga je po kolei, a każdy
rozstrzygnięty zostaje na ekranie na zawsze. Operator zobaczył dziesięć takich rynków pod
jednym wydarzeniem, każdy z dwoma wynikami i pięcioma oknami: **sto wierszy, z których żaden
nie mówi nic o teraz.**

Gorzej, bo to nie jest tylko hałas — to hałas udający odczyt. Rozstrzygnięty rynek stoi na
0% i 100%, więc każde okno pokazuje `0.0 pp`, a starsze `no coverage`. Pierwsze czyta się jak
„rynek się nie ruszył", drugie jak „archiwum ma dziurę". Prawda jest inna i jest trzecia:
**po rozstrzygnięciu nie ma czego mierzyć.** Widok, który tego nie mówi, robi dokładnie to,
przed czym ta zakładka broni się wszędzie indziej — podaje liczbę tam, gdzie nie ma zjawiska.

## What Changes

- **Rozstrzygnięte rynki są domyślnie zwinięte** wewnątrz wydarzenia, z licznikiem i sposobem
  ich pokazania. Zwinięte, nie usunięte: ich historia jest tym, po co ten moduł powstał,
  a rynek rozstrzygnięty wczoraj jest najciekawszym materiałem, jaki ma.
- **Rozstrzygnięty rynek nie pokazuje okien w ogóle.** Zamiast pięciu wartości, z których
  żadna nie jest pomiarem, jedno zdanie: czym się rozstrzygnął. To zmiana warta więcej niż
  samo zwijanie, bo dotyczy także rynku pokazanego świadomie.
- **Zwinięty wiersz wydarzenia cytuje rynek nierozstrzygnięty.** Dziś wybiera pierwszy
  z brzegu, więc wydarzenie z jednym żywym rynkiem i dziewięcioma zamkniętymi kwotuje 100%
  na czymś, co skończyło się w sierpniu.
- **Wydarzenie, którego wszystkie rynki są rozstrzygnięte**, mówi to w nagłówku, zamiast
  wyglądać na puste po zwinięciu.

## Capabilities

### Modified Capabilities

- `terminal-polymarket`: scenariusz „Wydarzenie o wielu rynkach" mówi bezwarunkowo, że widok
  pokazuje każdy rynek wraz z jego wynikami. Rozstrzygnięte MUST móc być domyślnie zwinięte —
  i MUST pozostać osiągalne, bo to jest ta połowa, która czyni z tego zwijanie, a nie
  ukrywanie. Do tego samego wymagania dochodzi zdanie o oknach: dla rynku rozstrzygniętego
  MUST NOT być pokazana wartość zmiany, bo `0.0 pp` twierdzi coś o rynku, a nie o jego końcu.

**Bez `design.md`.** Jedyna decyzja z alternatywą — usunąć rozstrzygnięte z widoku zamiast je
zwinąć — jest rozstrzygnięta w jednym zdaniu wyżej i nie unosi osobnego dokumentu.

## Impact

**Terminal.** `EventCard.tsx` — podział rynków na żywe i rozstrzygnięte, ujawnianie tych
drugich, brak okien dla nich; `CollapsedSummary` wybiera spośród żywych. Nic poza tym
katalogiem.

**Czego ta zmiana nie rusza.** `polymarket-data` — moduł już publikuje `resolved_outcome` na
rynku i stan `resolved` na zbieraniu, więc widok ma z czego to wyczytać i żadna trasa,
kontrakt ani migracja się nie zmieniają. Infrastruktury też nie.
