## ADDED Requirements

### Requirement: Formularz wybiera adresata i bota osobno

Formularz reguły MUST mieć obok pola „Kogo powiadomić” pole „Którym botem”, w którym MUST być tylko boty, przez które
wybrany adresat jest związany. Gdy adresat ma jednego bota, pole MUST go podpowiadać i MAY go pozostawić pustym; gdy
kilku, MUST wymagać wyboru i MUST domyślnie podpowiadać bota, którego wiązanie odbiera. Lista reguł MUST mówić, przez
którego bota reguła idzie, a regułę bez bota o dwuznacznym adresacie MUST pokazywać jako wadliwą z tym powodem.

#### Scenario: Adresat z kilkoma botami

- **WHEN** operator wybiera adresata związanego przez trzy boty
- **THEN** pole bota MUST wymagać wyboru jednego z tych trzech i MUST NOT oferować innych botów

#### Scenario: Reguła sprzed zmiany

- **WHEN** reguła zapisana bez bota wskazuje adresata o jednym wiązaniu
- **THEN** lista MUST pokazać ją jako działającą, a edycja MUST wypełnić pole bota tym jedynym botem
