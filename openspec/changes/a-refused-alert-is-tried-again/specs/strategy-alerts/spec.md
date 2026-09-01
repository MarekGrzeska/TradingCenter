## MODIFIED Requirements

### Requirement: Ta sama decyzja nie powiadamia dwa razy

Moduł MUST powiadamiać wtedy, gdy decyzja dla danej obserwacji jest zmianą względem poprzedniej
zapisanej dla niej decyzji, **oraz** wtedy, gdy jest jej powtórzeniem, a o tamtej nie zdołano
powiedzieć. Decyzja powtórzona w kolejnym przebiegu MUST NOT wywoływać drugiego powiadomienia, o ile
poprzednia dostała znacznik zapowiedzenia.

Pętla ocenia obserwację przy każdej zamkniętej świecy, więc jedno wejście, które jest ważne przez
dziesięć świec, jest dziesięcioma identycznymi decyzjami — i to jest powód pierwszej połowy reguły.
Druga połowa jest tym, co czyni znacznik mechanizmem ponowienia, a nie samą deduplikacją: brama nie
pamięta niczego, co wysłała, więc poprzednia decyzja bez znacznika znaczy, że operator nie wie o
niczym. Powtórzenie jest wtedy **pierwszym** powiadomieniem, nie drugim.

Cena jest ta sama co w `social-data-alerts` i nazwana tam tak samo: wysyłka, która się udała, a
której znacznik nie został zapisany, zapowie ten sam setup drugi raz. Powtórzone powiadomienie jest
tańsze niż zgubione.

#### Scenario: Wejście utrzymuje się przez kolejne przebiegi

- **WHEN** kolejny przebieg dochodzi do tej samej decyzji co poprzedni dla tej samej obserwacji, a
  poprzednia została zapowiedziana
- **THEN** moduł MUST NOT wysłać drugiego powiadomienia

#### Scenario: Powtórzenie po nieudanej wysyłce

- **WHEN** kolejny przebieg dochodzi do tej samej decyzji co poprzedni dla tej samej obserwacji, a
  poprzednia nie dostała znacznika zapowiedzenia
- **THEN** moduł MUST wysłać powiadomienie o tej decyzji

#### Scenario: Brama podłączona przy stojącym wejściu

- **WHEN** adres bramy zostaje ustawiony w chwili, gdy ostatnia zapisana decyzja wskazuje zagranie i
  nie ma znacznika zapowiedzenia
- **THEN** pierwszy przebieg po ustawieniu MUST wysłać powiadomienie o tym zagraniu
