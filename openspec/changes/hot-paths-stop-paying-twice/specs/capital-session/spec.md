## MODIFIED Requirements

### Requirement: Wyłącznie środowisko demo

Moduł MUST odmówić pracy z hostem capital.com innym niż host demo. Sprawdzenie MUST nastąpić przy
starcie, przed wysłaniem jakiegokolwiek żądania.

Środowisko, które moduł publikuje w swoich możliwościach, MUST wynikać z hosta, z którym moduł
jest związany, a MUST NOT być wartością wpisaną niezależnie od niego. Konsument pyta o
środowisko po to, żeby wiedzieć, do czego jest podłączony; odpowiedź, która nie może być inna,
nie niesie tej informacji, tylko ją udaje.

#### Scenario: Skonfigurowany host produkcyjny

- **WHEN** skonfigurowany adres bazowy albo adres strumienia nie jest hostem demo
- **THEN** moduł odmawia startu i stwierdza, że dozwolone jest wyłącznie środowisko demo

#### Scenario: Publikowane możliwości nazywają środowisko

- **WHEN** konsument odczytuje możliwości modułu
- **THEN** odpowiedź nazywa środowisko jako `demo`
- **AND** nazwa ta jest wyprowadzona z hosta, z którym moduł jest związany
