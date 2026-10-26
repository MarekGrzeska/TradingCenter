## MODIFIED Requirements

### Requirement: Moduł ma jeden zegar i sam publikuje najbliższe wyzwolenia

Każdy harmonogram MUST nieść strefę czasową, w której jest czytany — nazwę ze strefowej bazy IANA, na przykład
`America/New_York`. Harmonogram zapisany bez strefy MUST dostać `Europe/Warsaw`, a harmonogram ze strefą, której
baza nie zna, MUST zostać odrzucony przy zapisie z komunikatem nazywającym tę strefę. Godzina, minuta i dni
tygodnia harmonogramu MUST być czytane jako czas ścienny w jego strefie, a czas wyzwolenia MUST być publikowany
w UTC. Godzina harmonogramu MUST NOT przesuwać się przy zmianie czasu w jego strefie: harmonogram opisany na 9:35
w `America/New_York` wyzwala się o 9:35 czasu nowojorskiego zarówno w czasie letnim, jak i zimowym, również
w tygodniach, w których Polska zmieniła już czas, a Nowy Jork jeszcze nie. Moduł MUST publikować moment
najbliższego wyzwolenia harmonogramu i jego strefę, a wyliczenie momentu MUST NOT być zadaniem odbiorcy kontraktu.
Podgląd najbliższych wyzwoleń niezapisanego harmonogramu MUST przyjmować strefę tak samo jak zapis. Budzenie się
modułu MUST dać się wyłączyć ustawieniem aplikacji, bez wdrażania nowego obrazu; wyłączenie MUST NOT zabrać
możliwości uruchomienia przebiegu ręcznie.

Operator pracuje w jednej strefie — swojej — i dlatego jest ona domyślna. Rynek, który zespół gra, pracuje
w swojej: sesja nowojorska liczona po polsku przesuwała się o godzinę przez kilka tygodni w roku, bo USA i Europa
zmieniają czas w różne niedziele. Cena zostaje ta sama co dotąd: granica dobowa kosztu nadal liczy się od północy
UTC, więc odstęp między resetem budżetu a wyzwoleniem zmienia się o godzinę przy zmianie czasu. To jest odstęp,
którego nikt nie ogląda.

#### Scenario: Operator pyta o najbliższe wyzwolenia

- **WHEN** operator otwiera harmonogram
- **THEN** dostaje z modułu moment najbliższego wyzwolenia i kolejnych, w UTC
- **AND** dostaje strefę, w której harmonogram jest czytany

#### Scenario: Zmiana czasu

- **WHEN** harmonogram codzienny na 9:00 bez podanej strefy przechodzi przez zmianę czasu letniego na zimowy
- **THEN** wyzwala się dalej o 9:00 czasu polskiego
- **AND** publikowany moment wyzwolenia w UTC przesuwa się o godzinę

#### Scenario: Harmonogram w strefie rynku, gdy strefy zmieniają czas w różne dni

- **WHEN** harmonogram w dni robocze na 9:35 w strefie `America/New_York` wyzwala się w tygodniu między
  zmianą czasu w Polsce a zmianą czasu w Nowym Jorku
- **THEN** wyzwala się o 9:35 czasu nowojorskiego
- **AND** dni tygodnia są dniami tygodnia w Nowym Jorku

#### Scenario: Nieznana strefa

- **WHEN** operator zapisuje harmonogram ze strefą, której baza IANA nie zna
- **THEN** zapis jest odrzucony, a komunikat nazywa tę strefę
- **AND** żaden harmonogram nie powstaje

#### Scenario: Budzenie wyłączone ustawieniem

- **WHEN** budzenie się modułu jest wyłączone ustawieniem aplikacji
- **THEN** żaden harmonogram nie wyzwala
- **AND** ręczne uruchomienie przebiegu działa dalej
