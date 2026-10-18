## ADDED Requirements

### Requirement: Adresat z przypisaniem nie znika po cichu

Usunięcie adresata, któremu przypisany jest cel, przedrostek celu albo przypisanie domyślne, MUST
być odmową nazywającą te przypisania. Moduł MUST NOT usuwać przypisań kaskadowo.

#### Scenario: Usunięcie adresata domyślnego

- **WHEN** operator prosi o usunięcie adresata, który jest przypisaniem domyślnym
- **THEN** moduł MUST odmówić, nazywając przypisanie domyślne, a adresat MUST dalej odbierać
