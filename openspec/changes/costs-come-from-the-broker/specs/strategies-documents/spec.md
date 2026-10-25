## ADDED Requirements

### Requirement: Strategia pamięta swoją rozmowę

Strategia MAY mieć przypisaną jedną rozmowę z agentem, zapisaną jako identyfikator rozmowy. Pakiet MUST pozwalać ją
przypisać i zmienić przez REST i MUST podawać ją w odczycie strategii. Pakiet MUST NOT czytać rozmowy ani sprawdzać jej
istnienia: to identyfikator w cudzym pakiecie, a skasowana rozmowa oznacza tylko, że okno zacznie nową. Przypisanie
MUST NOT tworzyć rewizji ani zmieniać licznika prób.

#### Scenario: Przypisanie rozmowy

- **WHEN** okno tworzenia przypisuje strategii 7 rozmowę 42
- **THEN** odczyt strategii 7 MUST podawać rozmowę 42, a liczba rewizji MUST pozostać bez zmian
