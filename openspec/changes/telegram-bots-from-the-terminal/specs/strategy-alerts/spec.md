## MODIFIED Requirements

### Requirement: Brak bramy nie zatrzymuje oceniania

Moduł MUST wysyłać powiadomienie o decyzji z celem `strategy.setup`, a nie do nazwanego adresata.
Moduł MUST oceniać obserwacje i zapisywać decyzje normalnie, gdy brama odpowiada, że cel nie ma
adresata. Powiadamianie MUST być wtedy pominięte bez wpływu na decyzję i bez błędu.

Platforma strategii decyduje, a wykonaniem zajmuje się kto inny — więc niemożność powiedzenia o
decyzji MUST NOT być powodem, żeby jej nie podjąć.

#### Scenario: Brama nieskonfigurowana

- **WHEN** cel `strategy.setup` nie ma adresata, a przebieg kończy się decyzją o zagraniu
- **THEN** decyzja MUST zostać zapisana, a przebieg MUST zakończyć się powodzeniem
