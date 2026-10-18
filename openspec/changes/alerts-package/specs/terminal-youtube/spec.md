## MODIFIED Requirements

### Requirement: Operator edytuje listę obserwacji

Zakładka MUST pozwalać dopisać kanał adresem albo uchwytem, dopisać temat, spauzować i zdjąć
obserwację oraz wskazać pojedynczy film do analizy. Zakładka MUST NOT decydować o powiadomieniach z
kanału ani tematu — MUST natomiast odsyłać do zakładki Alerty. Odmowa kontraktu (sufit, nieznany
kanał) MUST być pokazana z powodem.

#### Scenario: Kanał nie istnieje

- **WHEN** operator dopisuje adres, który nie jest kanałem
- **THEN** ekran MUST pokazać powód odmowy i MUST NOT dodać pozycji do listy
