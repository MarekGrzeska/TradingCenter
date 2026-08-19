## REMOVED Requirements

### Requirement: To, co powstaje z czatu, należy do operatora, który o to poprosił

**Reason**: Zdolność opisywała moduł `teams-mcp`, który przestaje istnieć jako proces.

**Migration**: Przeniesione bez zmiany treści do `workbench-team-tools`; zmienia się tylko nazwa tożsamości usługowej, która nie może być właścicielem.

### Requirement: Brak tożsamości operatora zatrzymuje zapis, nie podstawia zastępczej

**Reason**: Warunek „mogła być ustalona" był dwuczłonowy: warstwa uwierzytelniająca przed modułem **albo** zdalny adres modułu `teams`. Drugi człon traci przedmiot — katalog zespołów jest w tym samym procesie i nie ma adresu.

**Migration**: Przeniesione do `workbench-team-tools` z warunkiem jednoczłonowym; scenariusz „Zdalny `teams` bez warstwy uwierzytelniającej przed modułem" odchodzi razem z drugim członem.

### Requirement: Tożsamość operatora jest przenoszona, a nie odgadywana z rozmowy

**Reason**: Zdolność opisywała moduł `teams-mcp`, który przestaje istnieć jako proces.

**Migration**: Przeniesione bez zmiany treści do `workbench-team-tools`. Łańcuch wywołań jest krótszy, wymaganie takie samo.

### Requirement: Moduł nie rozszerza uprawnień, które operator już ma

**Reason**: Zdolność opisywała moduł `teams-mcp`, który przestaje istnieć jako proces.

**Migration**: Przeniesione bez zmiany treści do `workbench-team-tools`. Jest to wymaganie, które wymusza D3 z `design.md` — narzędzia wołają kontrakt powierzchni zespołów, nie jej warstwę składowania.
