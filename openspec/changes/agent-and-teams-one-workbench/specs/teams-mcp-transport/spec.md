## REMOVED Requirements

### Requirement: Jeden transport, wybrany bez pytania wołającego

**Reason**: Nie ma transportu do wyboru: narzędzia są warstwą w procesie, który je wykonuje.

**Migration**: Bez następcy. Powierzchnia narzędzi jest osiągalna tak, jak proces, w którym stoi.

### Requirement: Wołający jest jeden i jest nazwany

**Reason**: Jedynym wołającym była powierzchnia czatu, która jest teraz w tym samym procesie. Lista wołających nie ma kogo wyliczać.

**Migration**: Bez następcy po stronie sieci. To, kto może użyć narzędzia, rozstrzyga wymaganie o tożsamości operatora w `workbench-team-tools`.

### Requirement: Jedno wejście odpowiada bez poświadczenia

**Reason**: Wejście zdrowia przestaje należeć do modułu, który znika, i zaczyna należeć do procesu, który zostaje.

**Migration**: Przeniesione do `workbench-process`, „Jedno wejście odpowiada bez poświadczenia".
