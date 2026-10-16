## MODIFIED Requirements

### Requirement: Zakładanie, kasowanie i wiązanie są wyłącznie w REST

Trasy zmieniające listę botów, listę adresatów, przypisania celów oraz logujące i wylogowujące konto
MUST być osiągalne wyłącznie przez kontrakt REST. Powierzchnia narzędziowa MUST NOT ich publikować w
żadnej postaci.

To ta sama granica, którą `polymarket-data` postawiło wokół kasowania historii: akt, którego skutku
nie da się cofnąć rozmową, nie należy do rozmowy.

#### Scenario: Model próbuje sięgnąć po zarządzanie

- **WHEN** przeszukuje się powierzchnię narzędziową modułu
- **THEN** MUST NOT znaleźć się w niej narzędzie zakładające, kasujące lub rotujące bota, wiążące adresata, zmieniające przypisanie ani logujące konto

### Requirement: Moduł mówi, czego mu brakuje

Moduł MUST publikować trasę stanu, która mówi, czy konto-właściciel jest zalogowane (i jakie, albo
dlaczego nie), czy ustawiony jest klucz sesji, ilu zna botów, ilu związanych adresatów, czy istnieje
przypisanie domyślne i ile znanych celów nie ma adresata. Trasa MUST odpowiadać także wtedy, gdy
moduł nie ma ani jednego bota.

Brama, która nie ma adresata, wygląda z zewnątrz dokładnie tak samo jak brama zepsuta — dopóki nie
powie tego wprost.

#### Scenario: Brama bez adresatów

- **WHEN** brama nie zna ani jednego adresata
- **THEN** trasa stanu MUST odpowiedzieć powodzeniem i MUST powiedzieć, że adresatów jest zero

#### Scenario: Cele bez adresata

- **WHEN** brama zna trzy cele, a przypisanie ma tylko jeden i nie ma przypisania domyślnego
- **THEN** trasa stanu MUST powiedzieć, że dwa cele nie mają adresata
