## REMOVED Requirements

### Requirement: Odpowiedź ma sufit, a odcięcie nie jest ciche

**Reason**: Moduł `market-mcp` przestaje istnieć; kształt odpowiedzi dla modelu jest odtąd
kształtem odpowiedzi archiwum.
**Migration**: `market-data-answers`, wymaganie o tej samej nazwie, z dopisanym akapitem:
sufity obowiązują niezależnie od tego, że dane są o wywołanie funkcji stąd — granica jest
tam, gdzie jest, ze względu na to, ile model uniesie w turze, nie ze względu na koszt
dowiezienia.

### Requirement: Niepewność archiwum jedzie w treści odpowiedzi

**Reason**: Jak wyżej.
**Migration**: `market-data-answers`, wymaganie o tej samej nazwie, treść bez zmian.

### Requirement: Trzy rodzaje „nie wiem" są rozróżnione

**Reason**: Jak wyżej, i jedno z trzech rozróżnień zmienia przedmiot: „archiwum nie
odpowiedziało" opisywało wywołanie po sieci, którego już nie ma.
**Migration**: `market-data-answers`, wymaganie o tej samej nazwie. Trzeci rodzaj brzmi
odtąd „odczyt się nie powiódł" i obejmuje bazę, która nie odpowiada, oraz obliczenie, które
padło. Rozróżnienie zostaje w całości: awaria MUST NOT czytać się jako cisza rynku.

### Requirement: Odmowa jest odpowiedzią o jednym kształcie

**Reason**: Jak wyżej, i z tego samego powodu co przy „trzech rodzajach": odmowa archiwum
nie przyjeżdża już po sieci jako odpowiedź HTTP.
**Migration**: `market-data-answers`, wymaganie o tej samej nazwie. Obowiązek przepisania
odmowy w słowach, w których padła, zostaje — tyle że jej źródłem jest wyjątek podniesiony
w tym samym procesie, nie treść odpowiedzi zdalnej.
