# terminal-alerts Specification

## Purpose
Zakładka Alerty w terminalu: reguły, ich historia i kreator, w którym operator niczego nie wpisuje z
pamięci. Do tego pole na zdanie, które wypełnia kreator za operatora.

## Requirements

### Requirement: Regułę można zmienić zdaniem

Każda reguła MUST mieć „Zmień zdaniem…”, gdy szkice są dostępne. Wynik MUST otworzyć formularz edycji tej reguły
wypełniony zmienioną postacią, z tym, jak zdanie zostało zrozumiane; reguła MUST zmienić się dopiero po zapisie
formularza przez operatora.

#### Scenario: Zmiana zdaniem

- **WHEN** operator wpisuje zdanie przy regule i prosi o zmianę
- **THEN** MUST otworzyć się formularz edycji z propozycją, a lista reguł MUST pozostać bez zmian do zapisu
