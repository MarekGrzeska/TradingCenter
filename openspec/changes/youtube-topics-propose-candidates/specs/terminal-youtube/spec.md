## MODIFIED Requirements

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

## ADDED Requirements

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
