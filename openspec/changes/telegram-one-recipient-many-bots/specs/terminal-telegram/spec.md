## ADDED Requirements

### Requirement: Adresaci są grupowani według nazwy i można ich dodać przez kolejnego bota

Zakładka MUST pokazywać każdego adresata raz, z listą botów, przez których jest związany, i stanem każdego wiązania
osobno. MUST pozwalać dodać tego samego adresata przez kolejnego bota i wtedy MUST wydać odnośnik startowy do tego bota
oraz MUST powiedzieć, że uruchomienie rozmowy z poprzednim botem nie wystarcza. Dodanie drugiego bota adresatowi, na
którego wskazują reguły bez wskazanego bota, MUST ostrzec, że te reguły przestaną doręczać, dopóki nie wskaże się w nich
bota. Usunięcie MUST dotyczyć jednego wiązania i MUST nazywać bota.

#### Scenario: Ten sam adresat przez drugiego bota

- **WHEN** operator dodaje istniejącemu adresatowi drugiego bota
- **THEN** zakładka MUST wydać odnośnik do drugiego bota, pokazać oba wiązania pod jedną nazwą i MUST NOT zmienić stanu pierwszego

#### Scenario: Reguły bez wskazanego bota

- **WHEN** adresat, na którego wskazują reguły bez bota, dostaje drugiego bota
- **THEN** zakładka MUST ostrzec przed zapisem, że te reguły przestaną doręczać
