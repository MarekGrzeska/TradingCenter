## Purpose

Kontrakt REST bramy: co się przez niego robi, które trasy piszą, i co moduł mówi o sobie, gdy ktoś
pyta, czy w ogóle jest w stanie cokolwiek wysłać.

## ADDED Requirements

### Requirement: Kontrakt rozdziela wysyłanie od zarządzania

Kontrakt MUST rozdzielać wysłanie wiadomości od zarządzania botami i adresatami. Wysyłanie MUST być
dostępne każdemu wywołującemu, którego moduł zna; zakładanie i kasowanie bota oraz wiązanie i
usuwanie adresata MUST być osobnymi trasami.

#### Scenario: Wywołujący wysyła

- **WHEN** moduł-wywołujący prosi o wysłanie wiadomości
- **THEN** MUST mu się to udać bez sięgania po jakąkolwiek trasę zarządzającą

### Requirement: Zakładanie, kasowanie i wiązanie są wyłącznie w REST

Trasy zmieniające listę botów i listę adresatów MUST być osiągalne wyłącznie przez kontrakt REST.
Powierzchnia narzędziowa MUST NOT ich publikować w żadnej postaci.

To ta sama granica, którą `polymarket-data` postawiło wokół kasowania historii: akt, którego skutku
nie da się cofnąć rozmową, nie należy do rozmowy.

#### Scenario: Model próbuje sięgnąć po zarządzanie

- **WHEN** przeszukuje się powierzchnię narzędziową modułu
- **THEN** MUST NOT znaleźć się w niej narzędzie zakładające bota, kasujące bota ani wiążące adresata

### Requirement: Moduł mówi, czego mu brakuje

Moduł MUST publikować trasę stanu, która mówi, czy ma skonfigurowaną sesję konta do zakładania
botów, ilu zna botów i ilu związanych adresatów. Trasa MUST odpowiadać także wtedy, gdy moduł nie
ma ani jednego bota.

Brama, która nie ma adresata, wygląda z zewnątrz dokładnie tak samo jak brama zepsuta — dopóki nie
powie tego wprost.

#### Scenario: Brama bez adresatów

- **WHEN** brama nie zna ani jednego adresata
- **THEN** trasa stanu MUST odpowiedzieć powodzeniem i MUST powiedzieć, że adresatów jest zero

### Requirement: Trasa żywotności nie sięga do bazy ani do Telegrama

Trasa, po której platforma i wdrożenie poznają, że proces wstał, MUST odpowiadać bez odpytywania
bazy i bez odzywania się do Telegrama.

Wdrożenie pyta o to, czy proces w kontenerze się podniósł; baza pod obciążeniem odpowiadałaby wtedy
za coś innego.

#### Scenario: Wdrożenie sprawdza moduł

- **WHEN** wdrożenie odczytuje trasę żywotności
- **THEN** MUST dostać odpowiedź nazywającą ten moduł, niezależnie od stanu bazy i Telegrama
