# market-mcp-transport Specification

## Purpose
Jak klient sięga po moduł — dwiema drogami, jednym zestawem narzędzi — i kto ma prawo go
zawołać, gdy stoi w sieci, a nie na biurku operatora.
## Requirements
### Requirement: Dwa transporty, jeden zestaw narzędzi

Moduł MUST być osiągalny dwiema drogami: po sieci, dla klienta stojącego w innym procesie
i innym kontenerze, oraz przez strumienie procesu, dla klienta uruchamiającego moduł
lokalnie. Obie drogi MUST publikować ten sam zestaw narzędzi o tych samych opisach i tych
samych sufitach.

Zestaw narzędzi MUST być opisany raz. Transport rozstrzyga o tym, jak żądanie dociera, i
o niczym więcej.

#### Scenario: Ten sam zestaw obiema drogami

- **WHEN** klient prosi o listę narzędzi po sieci, a drugi klient przez strumienie procesu
- **THEN** obie listy MUST zawierać te same narzędzia z tymi samymi opisami

#### Scenario: Narzędzie dołożone do zestawu

- **WHEN** do modułu trafia nowe narzędzie
- **THEN** jest widoczne obiema drogami bez osobnej rejestracji dla którejkolwiek z nich

### Requirement: Żądanie z sieci niesie tożsamość wołającego

Gdy moduł jest wystawiony w sieci, MUST wymagać, żeby żądanie niosło tożsamość wołającego,
i MUST odmówić obsługi żądaniu, które jej nie niesie. Wymóg ten MUST dać się wyłączyć
wyłącznie dla pracy lokalnej, tak samo jak w archiwum, a jego wyłączenie MUST być
świadomym ustawieniem, nie wartością domyślną w środowisku zdalnym.

Moduł MUST zapisywać w dzienniku fakt odmowy i tożsamość, dla której wywołanie przeszło —
nigdy zaś treści żądania ani wartości poświadczenia.

#### Scenario: Wołanie bez tożsamości przy włączonym wymogu

- **WHEN** żądanie po sieci nie niesie tożsamości wołającego, a moduł jej wymaga
- **THEN** moduł MUST odmówić obsługi
- **AND** MUST NOT wykonać żadnego narzędzia

#### Scenario: Praca lokalna

- **WHEN** moduł jest uruchomiony lokalnie z wyłączonym wymogiem tożsamości
- **THEN** narzędzia działają, a dziennik odnotowuje wywołanie bez tożsamości jako takie

### Requirement: Zdrowie modułu da się sprawdzić bez sesji MCP

Moduł MUST odpowiadać na sondę zdrowia po drodze niewymagającej nawiązania sesji MCP ani
wywołania narzędzia. Platforma, na której moduł stoi, restartuje kontener na podstawie tej
odpowiedzi i nie zna protokołu MCP.

Sonda MUST odpowiadać także wtedy, gdy archiwum nie odpowiada: moduł, który stoi i mówi,
że archiwum leży, jest w innym stanie niż moduł, który nie stoi.

#### Scenario: Sonda bez sesji

- **WHEN** platforma odpytuje sondę zdrowia
- **THEN** moduł MUST odpowiedzieć bez nawiązywania sesji MCP

#### Scenario: Sonda przy niedostępnym archiwum

- **WHEN** archiwum nie odpowiada, a platforma odpytuje sondę zdrowia
- **THEN** moduł MUST nadal odpowiedzieć, że stoi
