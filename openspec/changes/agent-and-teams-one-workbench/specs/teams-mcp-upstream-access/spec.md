## REMOVED Requirements

### Requirement: Tryb połączenia jest wybrany jednoznacznie, nie zgadnięty

**Reason**: Nie ma połączenia do skonfigurowania — ani adresu, ani tożsamości wobec niego.

**Migration**: Bez następcy.

### Requirement: Kontrakt modułu `teams` jest sprawdzany, nie zakładany

**Reason**: Migawka istniała, bo kontrakt jechał przez sieć między dwoma obrazami. Schemat w tym samym procesie nie ma jak być nieświeży.

**Migration**: Bez następcy. Migawka `contract/teams.openapi.json` i skrypt jej pilnujący znikają wraz z powodem.

### Requirement: Wołanie modułu `teams` ma skończony czas

**Reason**: Granica czasu chroniła przed procesem, który nie odpowiada. Takiego procesu nie ma.

**Migration**: Bez następcy jako ustawienie. Zakaz ponawiania zapisu po własnej awarii nie znika — nie ma awarii transportu, po której miałby być ponowiony.

### Requirement: Odmowa modułu `teams` jest odróżnialna od jego niedostępności

**Reason**: Rozróżnienie zostaje, ale przestaje być wymaganiem o połączeniu.

**Migration**: Przeniesione w treści do `workbench-team-tools` — kształt odmowy i przenoszenie powodu słowami powierzchni zespołów są tam wymagane wprost.
