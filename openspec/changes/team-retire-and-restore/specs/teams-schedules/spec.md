## ADDED Requirements

### Requirement: Zegar nie uruchamia wycofanego zespołu

Zegar MUST NOT przejąć wyzwolenia harmonogramu ani sprawdzenia wyzwalacza, którego zespół jest wycofany —
także wtedy, gdy wiersz jest włączony.

Wycofanie wyłącza harmonogramy, ale to warunek przy samym przejęciu jest tym, co nie zależy od tego, czy każda
droga zapisu o nim pamiętała.

#### Scenario: Włączony harmonogram wycofanego zespołu

- **WHEN** harmonogram jest włączony i należny, a jego zespół jest wycofany
- **THEN** zegar nie przejmuje wyzwolenia i nie uruchamia przebiegu
