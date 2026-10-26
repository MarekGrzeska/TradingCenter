## MODIFIED Requirements

### Requirement: Narzędzia strategii dostaje tylko rozmowa

Narzędzia pakietu MUST trafiać do rejestru rozmowy jako funkcje w procesie. MUST NOT trafiać do rejestru zespołów ani do
katalogu narzędzi, z którego czytają reguły alertów.

Pakiet MUST serwować ten sam zestaw przez sieć pod `/strategies/mcp`, wyłącznie wołającym wymienionym na liście wołających
narzędzi (`operator-tool-access`); pusta lista MUST odmawiać każdemu. Wywołanie przez sieć MUST podlegać tym samym
odmowom, licznikowi prób i jednemu uruchomieniu agenta naraz co wywołanie z rozmowy — uruchomienie zlecone przez sieć
jest zapisane jako zlecone przez agenta.

#### Scenario: Narzędzia dla agenta zespołu

- **WHEN** operator przydziela narzędzia agentowi w zespole
- **THEN** wśród dostępnych narzędzi MUST NOT być żadnego narzędzia strategii

#### Scenario: Klient operatora pod `/strategies/mcp`

- **WHEN** wołający z listy wołających narzędzi nawiązuje sesję pod `/strategies/mcp`
- **THEN** dostaje ten sam zestaw narzędzi co rozmowa

#### Scenario: Wołający spoza listy

- **WHEN** wołający, którego lista nie wymienia, sięga po `/strategies/mcp`
- **THEN** pakiet odmawia z 403
