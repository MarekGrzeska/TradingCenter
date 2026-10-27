## Purpose

Kto i jak sięga po powierzchnie narzędziowe produkcji spoza systemu: które z nich niesie krawędź, czym wołający się
przedstawia, która osoba i która aplikacja są wpuszczane, i jak operator dostaje token do swojego klienta MCP.

## ADDED Requirements

### Requirement: Krawędź niesie powierzchnie narzędziowe hosta API, a nie bramy

Krawędź MUST przepuszczać żądania do `/<pakiet>/mcp` każdego pakietu workbencha, który publikuje powierzchnię
narzędziową, oraz do `/trading/mcp`, które MUST trafiać do trading-mcp. Na hoście bramy krawędź MUST dalej odpowiadać
404 na każdą ścieżkę `/mcp`. Każde przepuszczone żądanie MUST nieść znacznik krawędzi, tak jak każde inne żądanie z
zewnątrz.

#### Scenario: Klient MCP pod adresem archiwum

- **WHEN** klient MCP z zewnątrz nawiązuje sesję pod `https://<API_HOST>/market/mcp`
- **THEN** żądanie dociera do workbencha ze znacznikiem krawędzi i jest rozstrzygane przez drzwi procesu

#### Scenario: Ścieżka MCP na hoście bramy

- **WHEN** żądanie z zewnątrz trafia na `/mcp` na hoście bramy
- **THEN** krawędź odpowiada 404 i nic nie trafia do bramy

### Requirement: Narzędzia z zewnątrz wymagają tokenu, roli admin i aplikacji z listy

Żądanie z zewnątrz do powierzchni narzędziowej MUST nieść ważny token Entra wydany dla API procesu, który je obsługuje:
workbencha dla `/<pakiet>/mcp`, bramy dla `/trading/mcp`. Osoba w tokenie MUST mieć rolę `admin`; rola `viewer` ani brak
roli MUST NOT otworzyć żadnej powierzchni narzędziowej. Aplikacja, dla której token wydano, MUST być wymieniona
imiennie na liście wołających narzędzi; lista MUST być wyliczona, a pusta lista MUST odmawiać każdemu.

Przeglądarkowe aplikacje operatora (terminal, pocket) MUST NOT być na liście wołających narzędzi: ich tokeny nie
otwierają `/mcp`.

#### Scenario: Token admina z aplikacji operatora

- **WHEN** żądanie niesie ważny token z rolą `admin`, wydany aplikacji z listy wołających narzędzi
- **THEN** sesja MCP zostaje nawiązana, a narzędzia są wypisane

#### Scenario: Token przeglądarki terminala

- **WHEN** żądanie do `/<pakiet>/mcp` niesie ważny token admina wydany terminalowi
- **THEN** proces odmawia z 403, nie ujawniając listy narzędzi

#### Scenario: Viewer

- **WHEN** żądanie niesie token osoby z rolą `viewer`
- **THEN** proces odmawia z 403 na każdej powierzchni narzędziowej

#### Scenario: Brak tokenu

- **WHEN** żądanie z zewnątrz nie niesie tokenu albo token jest nieważny
- **THEN** proces odmawia z 401, zanim cokolwiek dotrze do narzędzia

#### Scenario: Token wydany dla workbencha na `/trading/mcp`

- **WHEN** żądanie do `/trading/mcp` niesie token z audiencją workbencha
- **THEN** trading-mcp odmawia z 401

### Requirement: Operator dostaje token bez interakcji w kliencie

Repozytorium MUST dostarczać operatorowi helper, który wypisuje nagłówek z tokenem dla API wskazanego przy rejestracji
serwera w kliencie MCP (`/trading/mcp` → brama, reszta → workbench), a nie zgadywanego z adresu. Helper wywołany przez klienta MUST
NOT otwierać przeglądarki ani czekać na operatora: bez tokenu w pamięci podręcznej MUST zakończyć się błędem, który
mówi, którą komendą się zalogować. Logowanie interaktywne MUST być osobną komendą. Konfiguracja serwerów w kliencie
MUST NOT być wpisana do repozytorium tak, żeby każda sesja pracująca nad kodem dostawała narzędzia produkcji.

#### Scenario: Token jest w pamięci podręcznej

- **WHEN** klient MCP uruchamia helper dla adresu `/market/mcp`, a operator był zalogowany
- **THEN** helper wypisuje obiekt JSON z nagłówkiem `Authorization: Bearer …` dla API workbencha

#### Scenario: Operator nie był zalogowany

- **WHEN** klient MCP uruchamia helper, a w pamięci podręcznej nie ma tokenu ani tokenu odświeżania
- **THEN** helper kończy się błędem nazywającym komendę logowania i nie otwiera przeglądarki
