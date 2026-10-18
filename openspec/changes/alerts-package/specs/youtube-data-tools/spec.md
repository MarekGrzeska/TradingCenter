## MODIFIED Requirements

### Requirement: Zestaw dopisuje, ale nie usuwa

Zestaw MUST zawierać narzędzia czytające archiwum oraz narzędzia zapisujące wyłącznie: dopisanie
kanału, dopisanie tematu i wskazanie filmu do analizy. Żadne narzędzie MUST NOT zdejmować
obserwacji, kasować filmów ani odczytów, zmieniać ustawień modułu, ustawiać niczego, co decyduje o
powiadomieniach, ani sięgać po cokolwiek związanego z rachunkiem. Ograniczenie MUST być sprawdzane
testem.

#### Scenario: Lista narzędzi

- **WHEN** klient prosi o listę narzędzi
- **THEN** MUST NOT być na niej narzędzia usuwającego cokolwiek, dotykającego rachunku ani ustawiającego powiadomienia
