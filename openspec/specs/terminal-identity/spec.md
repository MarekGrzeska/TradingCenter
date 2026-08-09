# terminal-identity Specification

## Purpose
Opisuje, skąd terminal bierze tożsamość operatora, co dokłada do wywołań i połączeń do archiwum,
jak zachowuje się, gdy tożsamość wygaśnie lub jej nie ma, i czego o niej nie pokazuje ani nie
zapisuje.
## Requirements
### Requirement: Operator loguje się kontem organizacji

Terminal MUST pozwolić operatorowi zalogować się kontem organizacji i MUST z tego logowania
uzyskać poświadczenie przeznaczone dla archiwum, a nie dla siebie. Poświadczenie MUST być
odnawiane bez udziału operatora, dopóki jego sesja na to pozwala; dopiero gdy ciche odnowienie się
nie powiedzie, terminal MUST poprosić o ponowne zalogowanie.

Stan zalogowania MUST być widoczny w powłoce, obok stanu źródeł danych — operator, który nie
widzi świec, MUST móc odróżnić „archiwum nie odpowiada" od „nie jestem zalogowany", bo są to
dwie różne sytuacje z dwiema różnymi odpowiedziami.

#### Scenario: Pierwsze wejście do terminala

- **WHEN** operator otwiera terminal i nie ma jeszcze tożsamości
- **THEN** terminal prowadzi go przez logowanie kontem organizacji
- **AND** po powrocie z logowania pokazuje widok, na który operator wchodził, a nie stronę startową

#### Scenario: Poświadczenie wygasa w trakcie pracy

- **WHEN** poświadczenie traci ważność, a sesja operatora jest nadal ważna
- **THEN** terminal odnawia je po cichu
- **AND** operator nie widzi ani logowania, ani przerwy w danych

#### Scenario: Sesja wygasła

- **WHEN** ciche odnowienie poświadczenia się nie powiedzie
- **THEN** terminal stwierdza, że operator nie jest zalogowany, i proponuje zalogowanie
- **AND** MUST NOT pokazywać tego jako niedostępności archiwum

### Requirement: Każde wywołanie archiwum niesie poświadczenie

Terminal MUST dokładać poświadczenie do każdego żądania HTTP kierowanego do archiwum — świec,
pokrycia, zleceń, usunięć oraz katalogu instrumentów, który archiwum proxuje. Dokładanie MUST być
własnością wspólnej warstwy wywołań, nie decyzją pojedynczego wywołania: trasa dopisana później
MUST nieść poświadczenie bez pamiętania o tym przez autora.

#### Scenario: Nowa trasa w kodzie terminala

- **WHEN** do kodu dochodzi wywołanie kolejnej trasy archiwum
- **THEN** niesie poświadczenie bez osobnego kroku po stronie wywołującego

#### Scenario: Katalog instrumentów

- **WHEN** wyszukiwarka pyta o instrumenty, a archiwum przekazuje pytanie dalej do gatewaya
- **THEN** żądanie do archiwum niesie poświadczenie tak samo jak żądanie o świece

### Requirement: Odmowa z powodu tożsamości jest odróżniona od awarii źródła

Odpowiedź archiwum stwierdzająca brak lub nieważność poświadczenia MUST być przez terminal
potraktowana jako utrata tożsamości, a nie jako niedostępność źródła. Terminal MUST wtedy podjąć
jedną próbę cichego odnowienia poświadczenia i powtórzyć wywołanie; MUST NOT wpadać w pętlę,
w której odmowa wywołuje odnowienie, a odnowienie kolejną odmowę.

#### Scenario: Odmowa, którą naprawia odnowienie

- **WHEN** archiwum odmawia z powodu poświadczenia, a ciche odnowienie się udaje
- **THEN** terminal powtarza wywołanie ze świeżym poświadczeniem
- **AND** operator nie widzi błędu

#### Scenario: Odmowa, której odnowienie nie naprawia

- **WHEN** archiwum odmawia z powodu poświadczenia, a odnowienie też kończy się odmową
- **THEN** terminal przestaje ponawiać i stwierdza, że operator nie jest zalogowany
- **AND** wskaźnik źródeł MUST NOT pokazywać archiwum jako nieosiągalnego

### Requirement: Połączenie strumieniowe zestawiane jest poświadczeniem jednorazowym

Przeglądarkowe połączenie strumieniowe nie niesie nagłówków, więc poświadczenie operatora nie ma
jak do niego trafić. Terminal MUST pobrać z archiwum poświadczenie jednorazowe przeznaczone
wyłącznie do zestawienia jednego połączenia i użyć go przy otwieraniu strumienia. Terminal
MUST pobierać je osobno dla każdej próby zestawienia, w tym dla każdej próby po zerwaniu, bo
poświadczenie zużyte jest bezwartościowe.

Terminal MUST NOT umieszczać w adresie połączenia poświadczenia operatora — do adresu trafia
wyłącznie poświadczenie jednorazowe.

#### Scenario: Otwarcie strumienia

- **WHEN** widok subskrybuje parę, a terminal ma ważną tożsamość
- **THEN** terminal najpierw pobiera poświadczenie jednorazowe, a potem otwiera nim połączenie

#### Scenario: Ponowne połączenie po zerwaniu

- **WHEN** połączenie zostaje zerwane i terminal je ponawia
- **THEN** każda próba używa świeżo pobranego poświadczenia jednorazowego
- **AND** MUST NOT używać ponownie tego, którym zestawiono poprzednie połączenie

#### Scenario: Adres połączenia trafia do logu

- **WHEN** adres zestawianego połączenia zostaje zapisany po stronie serwera
- **THEN** nie niesie poświadczenia operatora

### Requirement: Poświadczenie nie jest pokazywane ani utrwalane poza swoim miejscem

Terminal MUST NOT pokazywać poświadczenia — operatora ani jednorazowego — w komunikatach o błędach,
w widoku diagnostycznym ani w konsoli przeglądarki. Komunikat o niepowodzeniu MUST nazywać przyczynę
bez cytowania poświadczenia ani jego fragmentu.

#### Scenario: Nieudane wywołanie trafia do komunikatu

- **WHEN** wywołanie archiwum kończy się błędem, a terminal buduje komunikat dla operatora
- **THEN** komunikat nazywa przyczynę
- **AND** nie niesie poświadczenia ani jego fragmentu

### Requirement: Brak konfiguracji tożsamości oznacza pracę bez niej

Terminal uruchamiany bez skonfigurowanej tożsamości MUST działać i MUST NOT dokładać żadnego
poświadczenia do wywołań. Jest to tryb pracy lokalnej, gdzie archiwum stoi na tej samej maszynie
i nikt przed nim nie stoi. Terminal MUST NOT wymagać logowania po to, żeby dało się go w ogóle
uruchomić.

#### Scenario: Uruchomienie lokalne

- **WHEN** terminal startuje bez skonfigurowanej tożsamości
- **THEN** wywołania do archiwum idą bez poświadczenia
- **AND** terminal nie prowadzi operatora przez logowanie

#### Scenario: Strumień w trybie lokalnym

- **WHEN** widok subskrybuje parę, a tożsamość nie jest skonfigurowana
- **THEN** terminal pobiera poświadczenie jednorazowe i zestawia nim połączenie, tak samo jak
  z tożsamością
- **AND** samo żądanie o to poświadczenie idzie bez poświadczenia operatora

