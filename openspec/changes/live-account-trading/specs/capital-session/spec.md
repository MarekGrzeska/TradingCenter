## RENAMED Requirements

- FROM: `### Requirement: Wyłącznie środowisko demo`
- TO: `### Requirement: Środowisko jest jawnym wyborem, a domyślnym jest demo`

## MODIFIED Requirements

### Requirement: Środowisko jest jawnym wyborem, a domyślnym jest demo

Moduł MUST pracować w środowisku demo, chyba że konfiguracja jawnie wybiera środowisko realne (`capital-live-account`).
W środowisku demo moduł MUST odmówić pracy z hostem capital.com innym niż host demo; w środowisku realnym — z hostem
innym niż host realny. Sprawdzenie MUST nastąpić przy starcie, przed wysłaniem jakiegokolwiek żądania. Moduł MUST NOT
wnioskować środowiska z adresu: host realny w konfiguracji, która nie wybiera jawnie środowiska realnego, MUST
zatrzymać start tak samo jak dotąd.

Środowisko, które moduł publikuje w swoich możliwościach, MUST wynikać z hosta, z którym moduł
jest związany, a MUST NOT być wartością wpisaną niezależnie od niego. Konsument pyta o
środowisko po to, żeby wiedzieć, do czego jest podłączony; odpowiedź, która nie może być inna,
nie niesie tej informacji, tylko ją udaje.

#### Scenario: Skonfigurowany host produkcyjny

- **WHEN** konfiguracja nie wybiera środowiska realnego, a skonfigurowany adres bazowy albo adres strumienia nie jest
  hostem demo
- **THEN** moduł odmawia startu i stwierdza, że bez jawnego wyboru dozwolone jest wyłącznie środowisko demo

#### Scenario: Publikowane możliwości nazywają środowisko

- **WHEN** konsument odczytuje możliwości modułu
- **THEN** odpowiedź nazywa środowisko jako `demo` albo `live`
- **AND** nazwa ta jest wyprowadzona z hosta, z którym moduł jest związany

#### Scenario: Wybór środowiska spoza listy

- **WHEN** konfiguracja wybiera środowisko inne niż demo albo realne
- **THEN** moduł odmawia startu, wyliczając dozwolone wartości
