## ADDED Requirements

### Requirement: Szkic strategii przez REST

Pakiet MUST publikować `GET` i `DELETE` szkicu strategii (`/strategies/{id}/draft`) i szkicu nowej strategii
(`/drafts/new`). Odczyt MUST podawać dokument, chwilę zapisu i numer kolejny szkicu, po którym konsument rozpozna nowy
szkic. Brak szkicu MUST być odpowiedzią 404, nie pustym dokumentem.

#### Scenario: Odczyt szkicu

- **WHEN** konsument czyta szkic strategii, której agent położył szkic
- **THEN** odpowiedź MUST nieść dokument szkicu i jego numer kolejny
