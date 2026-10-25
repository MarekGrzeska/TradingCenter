## MODIFIED Requirements

### Requirement: Interwały nazywają się jednakowo w całym terminalu

Terminal MUST nazywać interwały świec `m1`, `m5`, `m15`, `m30`, `h1`, `h4`, `day`, `week` — w polu
wyboru na wykresie, na liście archiwizowanych instrumentów, w kreatorze dodawania, w historii
dociągania i w każdym komunikacie, który interwał wymienia. Nazwy, jakimi interwały jeżdżą po
drucie (`MINUTE_5`, `HOUR_4`), MUST NOT docierać na ekran: ten sam interwał pod dwiema nazwami
w dwóch zakładkach każe operatorowi tłumaczyć jedną na drugą w głowie.

Jedynym wyjątkiem jest tekst dokumentu strategii w edytorze zakładki Strategies. To tekst języka formuł, w którym
interwał ma nazwę języka (`close @ HOUR_4`), więc edytor MUST pokazywać go dokładnie tak, jak jest zapisany. Gdyby
terminal przepisał w nim nazwy, zmieniłby dokument, który operator zapisuje. Podpowiedź nazwy interwału w edytorze MUST
pokazywać obok nazwę terminala. Wszystko poza tym tekstem, w tym streszczenie, MUST używać nazw terminala.

#### Scenario: Wybór interwału na wykresie

- **WHEN** operator otwiera pole wyboru interwału
- **THEN** widzi `m1`, `m5`, `m15`, `m30`, `h1`, `h4`, `day`, `week`
- **AND** MUST NOT widzieć nazwy z kontraktu

#### Scenario: Ten sam interwał w dwóch zakładkach

- **WHEN** ten sam interwał jest pokazany na wykresie i na liście archiwizowanych instrumentów
- **THEN** w obu miejscach nazywa się tak samo

#### Scenario: Interwał w dokumencie strategii

- **WHEN** edytor pokazuje formułę `ema(20) @ HOUR_4`, a obok stoi jej streszczenie
- **THEN** tekst w edytorze MUST zostać `HOUR_4`, podpowiedź MUST pokazywać `HOUR_4` z `h4` obok
- **AND** streszczenie i lista strategii MUST mówić `h4`
