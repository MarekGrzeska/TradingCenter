## REMOVED Requirements

### Requirement: Producent adresuje celem, a cel jest otwarty
**Reason**: O tym, kto słyszy jakie zdarzenie, decyduje reguła pakietu alertów, która nazywa adresata wprost. Cel i przypisanie były drugą, tekstową warstwą tej samej decyzji.
**Migration**: Producenci publikują zdarzenia do pakietu alertów (`alerts-events`), a pakiet alertów wysyła przez bramę po nazwie adresata. Istniejące przypisania stają się regułami przy pierwszym starcie pakietu alertów.

### Requirement: Brama pamięta cele, nie wiadomości
**Reason**: Katalogiem tego, o czym system umie mówić, są typy zdarzeń ogłaszane w pakiecie alertów — ze schematem atrybutów, nie tylko z nazwą.
**Migration**: `alerts-events`: ogłoszenie typu zdarzenia.

### Requirement: Jeden cel ma co najwyżej jednego adresata
**Reason**: Adresata wskazuje reguła, a jedno zdarzenie może trafić do wielu adresatów przez wiele reguł.
**Migration**: `alerts-rules`.

### Requirement: Rozstrzyga najdłuższy pasujący przedrostek
**Reason**: Dopasowanie po przedrostku nazwy zastępuje filtr reguły na atrybutach zdarzenia.
**Migration**: `alerts-events`: filtr reguły. Przypisanie przedrostka migruje do reguły na typie, który odpowiadał przedrostkowi, z filtrem tylko tam, gdzie klucz wskazywał źródło.

### Requirement: Cel bez adresata to odpowiedź, nie awaria
**Reason**: Brama nie przyjmuje już celów. Zdarzenie, do którego nie pasuje żadna reguła, jest w pakiecie alertów zwykłym zdarzeniem bez odpalenia.
**Migration**: Producent stawia znacznik po przyjęciu zdarzenia przez pakiet alertów, niezależnie od tego, czy pasuje do niego jakaś reguła.

### Requirement: Przypisania zmienia tylko operator
**Reason**: Przypisań już nie ma.
**Migration**: `alerts-rules`: „Reguły zmienia tylko operator”.
