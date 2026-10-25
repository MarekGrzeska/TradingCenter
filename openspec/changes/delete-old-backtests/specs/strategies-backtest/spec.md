## ADDED Requirements

### Requirement: Usunięcie uruchomienia nie obniża licznika prób

Pakiet MUST pozwalać usunąć uruchomienie zakończone, nieudane albo anulowane, razem z jego raportem, żądaniem,
pochodzeniem wyniku i transakcjami. Uruchomienie czekające w kolejce albo liczone MUST NOT dać się usunąć. Licznik prób
strategii MUST być sumą jej zakończonych uruchomień i liczby zakończonych uruchomień usuniętych wcześniej, więc
usunięcie MUST NOT go zmniejszyć. Usunięcie nieudanego albo anulowanego uruchomienia MUST NOT go zmienić, bo takie
uruchomienie nie było liczone. Zapis liczby usuniętych prób i usunięcie MUST odbywać się w jednej transakcji. Usunięcie
kilku uruchomień naraz MUST być wszystko albo nic: gdy któreś nie istnieje albo jeszcze czeka lub się liczy, MUST NOT
zostać usunięte żadne.

#### Scenario: Usunięcie zakończonego uruchomienia

- **WHEN** strategia ma cztery zakończone uruchomienia, a jedno z nich zostaje usunięte
- **THEN** jej licznik prób MUST nadal wynosić cztery
- **AND** raport i transakcje usuniętego uruchomienia MUST przestać istnieć

#### Scenario: Usunięcie nieudanego uruchomienia

- **WHEN** strategia ma dwa zakończone i jedno nieudane uruchomienie, a nieudane zostaje usunięte
- **THEN** licznik prób MUST nadal wynosić dwa

#### Scenario: Uruchomienie, które się liczy

- **WHEN** wołający prosi o usunięcie uruchomienia w stanie `running`
- **THEN** usunięcie MUST zostać odrzucone z nazwą uruchomienia i jego stanu
- **AND** żadne uruchomienie MUST NOT zostać usunięte

#### Scenario: Jedno z kilku nie istnieje

- **WHEN** wołający prosi o usunięcie trzech uruchomień, z których jedno nie istnieje
- **THEN** żadne z trzech MUST NOT zostać usunięte, a odmowa MUST nazywać to, które nie istnieje

#### Scenario: Wyścig z końcem uruchomienia

- **WHEN** uruchomienie kończy się dokładnie wtedy, gdy ktoś prosi o jego usunięcie
- **THEN** wynik MUST być albo odmową „liczy się”, albo usunięciem z doliczoną próbą, a MUST NOT być usunięciem bez
  doliczenia
