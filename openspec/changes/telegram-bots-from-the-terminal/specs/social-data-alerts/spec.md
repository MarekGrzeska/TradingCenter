## MODIFIED Requirements

### Requirement: Brak bramy jest stanem wspieranym

Moduł MUST wysyłać powiadomienie o poście z celem `social.post`, a nie do nazwanego adresata. Moduł
MUST zbierać i wzbogacać normalnie, gdy brama odpowiada, że cel nie ma adresata. MUST NOT odmawiać
startu, MUST NOT przerywać zbiórki, MUST NOT stawiać znacznika „już powiedziane” i MUST powiedzieć
przez własną trasę stanu, że jego cel nie ma adresata.

#### Scenario: Brama nieskonfigurowana

- **WHEN** cel `social.post` nie ma adresata, a zbiórka napotyka post powyżej progu
- **THEN** moduł MUST zapisać post normalnie, MUST NOT postawić znacznika i MUST NOT potraktować tego jako błędu
