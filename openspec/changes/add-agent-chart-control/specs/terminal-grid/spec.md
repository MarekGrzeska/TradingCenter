## ADDED Requirements

### Requirement: Aktywny slot stosuje to, co ustawił agent

Terminal MUST stosować polecenie agenta do **aktywnego slotu**: jego zestaw wskaźników,
symbol i interwał. Pozostałe sloty MUST zostać nietknięte, tak samo jak przy zmianie
ręcznej.

Zastosowane polecenie MUST być zapamiętane tak samo jak zmiana ręczna — slot po
odświeżeniu MUST rysować to, co agent ustawił, aż operator to zmieni.

Terminal MUST pamiętać numer ostatnio zastosowanego polecenia i MUST NOT stosować tego
samego polecenia dwa razy. Zmiana ręczna po poleceniu agenta MUST zostać, a nie zostać
cofnięta przy następnym odczycie.

Polecenie MUST być stosowane w granicach, które slot już ma: symbol MUST być
instrumentem archiwizowanym, a interwał MUST być rozdzielczością, w której ten instrument
jest zbierany. Polecenie spoza tych granic MUST NOT zostać zastosowane — moduł agenta
odmawia go wcześniej, a terminal, gdyby takie do niego dotarło, MUST je pominąć i
powiedzieć o tym, zamiast pokazywać wykres bez danych.

Aktywny slot pusty MUST przyjąć symbol z polecenia jak każdy inny — polecenie jest właśnie
wyborem instrumentu.

#### Scenario: Agent ustawia wskaźniki aktywnego slotu

- **WHEN** agent ustawia zestaw wskaźników, a operator ma aktywny slot z instrumentem
- **THEN** ten slot rysuje ten zestaw
- **AND** pozostałe sloty rysują to, co rysowały

#### Scenario: Ustawienie agenta przeżywa odświeżenie

- **WHEN** operator odświeża stronę po tym, jak agent ustawił wskaźniki
- **THEN** slot rysuje je dalej

#### Scenario: To samo polecenie nie stosuje się dwa razy

- **WHEN** operator wyłącza wybierakiem wskaźnik ustawiony przez agenta i odświeża stronę
- **THEN** wskaźnik zostaje wyłączony, bo tamto polecenie zostało już zastosowane

#### Scenario: Agent zmienia symbol i interwał

- **WHEN** agent ustawia symbol i interwał, w których archiwum zbiera dane
- **THEN** aktywny slot pokazuje ten instrument w tym interwale
