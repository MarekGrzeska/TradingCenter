## Purpose

Jak archiwum YouTube trafia na produkcję: w jakiej kolejności dostaje bazę, klucze i ustawienia oraz co
gwarantuje, że żaden krok nie zostawia workbencha bez możliwości startu.

## ADDED Requirements

### Requirement: Ustawienia montujące pakiet stoją za jedną zmienną

Infrastruktura MUST dawać workbenchowi ustawienia pakietu YouTube — adres bazy, dostawców i odwołania
do kluczy — wyłącznie wtedy, gdy zmienna włączenia jest prawdziwa, a jej wartość domyślna MUST być
fałszywa. Przy fałszywej zmiennej proces MUST działać bez pakietu.

Ustawienie wskazujące na pusty sekret App Service zostawia jako dosłowny tekst, a pakiet, któremu
dano bazę, MUST ją mieć w posiadaniu, inaczej proces odmawia startu w całości.

#### Scenario: Zmienna fałszywa

- **WHEN** infrastruktura jest zastosowana ze zmienną włączenia fałszywą
- **THEN** workbench MUST NOT dostać żadnego ustawienia `YOUTUBE_*`, a baza i nazwy sekretów MUST istnieć

#### Scenario: Zmienna prawdziwa

- **WHEN** zmienna włączenia zostaje ustawiona na prawdziwą
- **THEN** workbench MUST dostać adres bazy, źródło `data_api`, łańcuch `direct,gemini` i odwołania do dwóch kluczy w Key Vault

### Requirement: Skrypt operatora nie ujawnia wartości i zamyka zaporę

Skrypt przygotowujący produkcję MUST domyślnie tylko opisywać kroki. Przy wykonaniu MUST przekazywać
klucze do Key Vault plikiem tymczasowym usuwanym od razu, MUST NOT umieszczać ich w argumentach
poleceń ani na ekranie, a token bazy MUST przekazywać środowiskiem. Tymczasową regułę zapory MUST
usunąć także wtedy, gdy nadanie własności bazy się nie powiodło.

#### Scenario: Próba na sucho

- **WHEN** skrypt jest uruchomiony bez zgody na wykonanie
- **THEN** MUST NOT wykonać żadnego polecenia ani wypisać żadnej wartości klucza

#### Scenario: Nadanie własności kończy się błędem

- **WHEN** polecenie bazy zwraca błąd
- **THEN** reguła zapory MUST zostać usunięta, a żaden sekret MUST NOT zostać zapisany

### Requirement: Pule połączeń mieszczą się w budżecie z włączonym pakietem

Suma pul wszystkich pakietów workbencha, łącznie z pakietem YouTube, MUST nie przekraczać budżetu
połączeń serwera, zarówno w wartościach domyślnych, jak i w ustawieniach produkcji.

#### Scenario: Pakiet YouTube policzony

- **WHEN** test budżetu sumuje pule domyślne i produkcyjne
- **THEN** MUST uwzględnić pakiet YouTube, a suma MUST wynosić nie więcej niż budżet
