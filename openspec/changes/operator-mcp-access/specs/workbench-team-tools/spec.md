## ADDED Requirements

### Requirement: Zestaw jest osiągalny przez sieć w imieniu osoby z tokenu

Ten sam zestaw narzędzi zespołów MUST być osiągalny przez sieć pod `/team-tools/mcp`, wyłącznie dla wołających
wymienionych na liście wołających narzędzi (`operator-tool-access`). Tożsamość operatora, w której imieniu narzędzie
działa, MUST pochodzić z osoby, którą drzwi procesu ustaliły z tokenu wołającego — nigdy z argumentu ani z nagłówka,
który wołający mógł sam napisać. Wywołanie przez sieć MUST podlegać tym samym odmowom i granicom co wywołanie z
rozmowy, a to, co powstaje, MUST należeć do tej osoby i być widoczne w terminalu.

#### Scenario: Zespół założony z klienta operatora

- **WHEN** wołający z listy woła przez sieć narzędzie zakładające zespół, z tokenem operatora
- **THEN** zespół należy do osoby z tokenu i jest na jej liście w terminalu

#### Scenario: Wołający spoza listy

- **WHEN** wołający, którego lista nie wymienia, sięga po `/team-tools/mcp`
- **THEN** proces odmawia z 403 bez wywołania narzędzia

#### Scenario: Wywołanie przez sieć bez tożsamości osoby

- **WHEN** przed procesem stoi warstwa uwierzytelniająca, a wywołanie przez sieć dociera bez ustalonej osoby
- **THEN** narzędzie odmawia, nazywając brak tożsamości, i nic nie powstaje
