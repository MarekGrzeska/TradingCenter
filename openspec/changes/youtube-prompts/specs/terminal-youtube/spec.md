## MODIFIED Requirements

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

Zakładka MUST pozwalać dopisać kanał adresem albo uchwytem, dopisać temat, wybrać i zmienić prompt kanału albo
tematu, spauzować i zdjąć obserwację oraz wskazać pojedynczy film do analizy, opcjonalnie z promptem. Zakładka MUST
NOT decydować o powiadomieniach z kanału ani tematu — MUST natomiast odsyłać do zakładki Alerty. Odmowa kontraktu
(sufit, nieznany kanał) MUST być pokazana z powodem.

#### Scenario: Kanał nie istnieje

- **WHEN** operator dopisuje adres, który nie jest kanałem
- **THEN** ekran MUST pokazać powód odmowy i MUST NOT dodać pozycji do listy

## ADDED Requirements

### Requirement: Sekcja Prompty zarządza promptami

Zakładka YouTube MUST mieć sekcję Prompty obok Filmów, Kanałów i Tematów, pokazującą prompty z nazwą, numerem wersji i kanałami oraz
tematami, do których każdy jest przypisany. Sekcja MUST pozwalać utworzyć prompt, zmienić jego nazwę i treść oraz
usunąć go. Zasiany prompt MUST NOT oferować usunięcia. Odmowa kontraktu — zajęta nazwa, prompt przypisany do kanału
— MUST być pokazana z powodem.

#### Scenario: Usunięcie przypisanego promptu

- **WHEN** operator usuwa prompt przypisany do kanału
- **THEN** ekran MUST pokazać powód odmowy z nazwą kanału, a prompt MUST zostać na liście

#### Scenario: Zasiany prompt

- **WHEN** operator otwiera zasiany prompt
- **THEN** sekcja MUST pozwolić go edytować i MUST NOT pokazać akcji usunięcia
