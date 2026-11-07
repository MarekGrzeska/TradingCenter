# terminal-youtube Specification

## Purpose
TBD - created by archiving change add-youtube-archive. Update Purpose after archive.
## Requirements
### Requirement: Zakładka pokazuje filmy z odczytem

Zakładka MUST pokazywać ostatnie filmy, najnowsze najpierw, z kanałem, stanem, oceną wpływu i krótkim
streszczeniem, oraz nazywać okno i liczbę filmów. Szczegół filmu MUST pokazywać odczyty filmu — odczyt promptem
filmu pierwszy — każdy z nazwą promptu i tekstem wyrenderowanym z markdown, zwiniętą transkrypcję i odnośnik do
filmu na YouTube, oraz pozwalać zamówić odczyt filmu innym promptem. Film nieodczytany MUST NOT pokazywać oceny
zastępczej.

#### Scenario: Film bez odczytu

- **WHEN** film nie ma odczytu
- **THEN** karta MUST pokazać jego stan zamiast oceny

#### Scenario: Film z dwoma odczytami

- **WHEN** film ma odczyt promptem kanału i odczyt zamówiony innym promptem
- **THEN** szczegół MUST pokazać oba, każdy z nazwą swojego promptu, odczyt promptem kanału pierwszy

### Requirement: Operator edytuje listę obserwacji

Zakładka MUST pozwalać na:

- dopisanie kanału adresem albo uchwytem;
- dopisanie tematu;
- wybór i zmianę promptu kanału;
- spauzowanie i zdjęcie obserwacji;
- wskazanie pojedynczego filmu do analizy, opcjonalnie z promptem.

Temat MUST NOT oferować wyboru promptu. Zakładka MUST NOT decydować o powiadomieniach z kanału ani tematu, lecz MUST
odsyłać do zakładki Alerty. Odmowa kontraktu (sufit, nieznany kanał) MUST być pokazana z powodem.

#### Scenario: Kanał nie istnieje

- **WHEN** operator dopisuje adres, który nie jest kanałem
- **THEN** ekran MUST pokazać powód odmowy i MUST NOT dodać pozycji do listy

### Requirement: Pasek stanu nazywa to, czego lista nie powie

Zakładka MUST pokazywać zużycie każdego dostawcy wobec sufitu, dostawcę zablokowanego, model
nieskonfigurowany, archiwum nieświeże oraz pracę na symulacji. Pusta lista MUST NOT być jedyną
odpowiedzią na którykolwiek z tych stanów.

#### Scenario: Praca na symulacji

- **WHEN** moduł działa na symulowanych dostawcach
- **THEN** zakładka MUST to pokazywać stale, a nie tylko przy pojedynczym filmie

### Requirement: Nieudane odświeżenie nie czyści ekranu

Zakładka MUST odświeżać się sama, a nieudane odświeżenie MUST NOT kasować tego, co jest na ekranie.

#### Scenario: Odświeżenie nie dochodzi

- **WHEN** odświeżenie kończy się błędem, a lista jest wypełniona
- **THEN** poprzednie filmy MUST zostać na ekranie

### Requirement: Sekcja Prompty zarządza promptami

Zakładka YouTube MUST mieć sekcję Prompty obok Filmów, Kanałów, Tematów i Kandydatów. Sekcja MUST pokazywać prompty z
nazwą, numerem wersji i kanałami, do których każdy jest przypisany. Sekcja MUST pozwalać utworzyć prompt, zmienić
jego nazwę i treść oraz usunąć go. Zasiany prompt MUST NOT oferować usunięcia. Odmowa kontraktu (zajęta nazwa, prompt
przypisany do kanału) MUST być pokazana z powodem.

#### Scenario: Usunięcie przypisanego promptu

- **WHEN** operator usuwa prompt przypisany do kanału
- **THEN** ekran MUST pokazać powód odmowy z nazwą kanału, a prompt MUST zostać na liście

#### Scenario: Zasiany prompt

- **WHEN** operator otwiera zasiany prompt
- **THEN** sekcja MUST pozwolić go edytować i MUST NOT pokazać akcji usunięcia

### Requirement: Sekcja Kandydaci prowadzi od znaleziska do decyzji

Zakładka YouTube MUST mieć sekcję Kandydaci. Każdy kandydat na liście MUST pokazywać:

- tytuł z odnośnikiem do filmu na YouTube, otwieranym w nowej karcie;
- kanał;
- temat, który go znalazł;
- datę publikacji i moment znalezienia;
- długość;
- uzasadnienie modelu albo informację, że kandydat nie był przesiany.

Sekcja MUST pozwalać przełączyć porządek między momentem znalezienia (domyślnie) a datą publikacji, zawęzić listę do
tematu i pokazać odrzuconych przez model. Przy każdym kandydacie MUST być cztery akcje:

- obserwuj kanał, z wyborem promptu;
- analizuj film, z wyborem promptu;
- odrzuć;
- ignoruj kanał.

Sekcja MUST pozwalać cofnąć ignorowanie kanału. Odmowa kontraktu MUST być pokazana z powodem, a kandydat MUST wtedy
zostać na liście.

#### Scenario: Przełączenie porządku

- **WHEN** operator przełącza porządek na datę publikacji
- **THEN** lista MUST zostać ponownie odczytana z kontraktu w tym porządku

#### Scenario: Odrzucenie kandydata

- **WHEN** operator odrzuca kandydata
- **THEN** kandydat MUST zniknąć z listy proponowanych

#### Scenario: Obserwacja ponad sufit

- **WHEN** operator wybiera „obserwuj kanał”, a kontrakt odmawia z powodu sufitu
- **THEN** ekran MUST pokazać powód, a kandydat MUST zostać na liście

