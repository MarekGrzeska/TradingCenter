## ADDED Requirements

### Requirement: Reguła nazywa adresata i, gdy adresat ma kilku botów, bota

Reguła MUST nazywać adresata. MAY nazywać też bota, przez którego adresat ma być powiadomiony. Reguła bez bota znaczy
„jedyny bot tego adresata” i MUST tak działać, dopóki adresat ma dokładnie jedno wiązanie; takie są wszystkie reguły
zapisane przed tą zmianą. Reguła bez bota dla adresata o kilku wiązaniach MUST NOT być doręczana po cichu przez któregoś
z nich: MUST być oznaczona na liście jako wadliwa z powodem nazywającym botów, a jej odpalenie MUST zakończyć się odmową
z tym powodem. Zapis MUST odrzucić regułę, która wskazuje bota, przez którego adresat nie jest związany, a także regułę
bez bota dla adresata o kilku wiązaniach — oba powody podane razem z pozostałymi.

#### Scenario: Reguła sprzed zmiany

- **WHEN** reguła zapisana bez bota wskazuje adresata, który ma jedno wiązanie
- **THEN** jej odpalenie MUST dojść przez to wiązanie, bez żadnej zmiany reguły

#### Scenario: Adresat dostaje drugiego bota

- **WHEN** adresat reguły bez bota zostaje związany także przez drugiego bota, a reguła odpala
- **THEN** odpalenie MUST zakończyć się odmową z powodem nazywającym oba boty, a reguła MUST być oznaczona jako wadliwa

#### Scenario: Reguła ze wskazanym botem

- **WHEN** adresat ma dwa wiązania, a reguła wskazuje jednego z botów
- **THEN** wiadomość MUST pójść wyłącznie przez tego bota

#### Scenario: Bot, którego adresat nie ma

- **WHEN** operator zapisuje regułę z botem, przez którego adresat nie jest związany
- **THEN** zapis MUST zostać odrzucony z powodem przy polu bota
