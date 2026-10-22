## ADDED Requirements

### Requirement: Odstęp pętli i domyślne granice tematu są ustawieniami operatora

Moduł MUST trzymać trzy wartości w bazie i MUST pozwalać operatorowi je odczytać i zmienić przez REST: odstęp między
przebiegami pętli, domyślny odstęp wyszukiwania tematu i domyślną liczbę filmów z jednego wyszukiwania tematu. Dopóki
żadna wartość nie została zapisana, moduł MUST stosować ustawienia procesu, a odpowiedź MUST podawać obowiązującą
wartość. Wartość poza granicami MUST zostać odrzucona z powodem i MUST NOT zmienić niczego. Agent MUST NOT zmieniać
tych ustawień.

#### Scenario: Nic nie zapisano

- **WHEN** operator czyta ustawienia, zanim cokolwiek zapisał
- **THEN** odpowiedź MUST zawierać wartości z ustawień procesu

#### Scenario: Zmiana jednej wartości

- **WHEN** operator zmienia tylko odstęp pętli
- **THEN** pozostałe dwie wartości MUST pozostać takie, jakie obowiązywały

#### Scenario: Wartość poza granicami

- **WHEN** operator zapisuje odstęp pętli krótszy niż 5 minut
- **THEN** moduł MUST odmówić z powodem, a obowiązujące wartości MUST pozostać bez zmian

### Requirement: Pętla stosuje zmieniony odstęp bez restartu

Pętla MUST czytać odstęp po każdym przebiegu, a zmiana zapisana w trakcie oczekiwania MUST skrócić lub wydłużyć to
oczekiwanie: następny przebieg MUST zacząć się nowy odstęp po końcu poprzedniego przebiegu. Zmiana MUST NOT uruchamiać
przebiegu sama w sobie. Tętno pętli MUST nieść obowiązujący odstęp jako oczekiwany.

#### Scenario: Skrócenie podczas oczekiwania

- **WHEN** odstęp zmienia się z 30 na 10 minut, a od końca ostatniego przebiegu minęło 15 minut
- **THEN** następny przebieg MUST ruszyć od razu

#### Scenario: Wydłużenie podczas oczekiwania

- **WHEN** odstęp zmienia się z 30 na 60 minut, a od końca ostatniego przebiegu minęło 20 minut
- **THEN** następny przebieg MUST ruszyć po 40 minutach od zmiany

### Requirement: Domyślne granice dotyczą tematów dopisywanych bez własnych

Odstęp i liczba filmów zapisane w ustawieniach MUST być stosowane do tematu dopisywanego bez własnych granic — przez
operatora i przez agenta — i MUST NOT zmieniać tematów już na liście.

#### Scenario: Temat dopisany po zmianie

- **WHEN** operator zmienia domyślny odstęp na 120 minut i dopisuje temat samą frazą
- **THEN** temat MUST dostać odstęp 120 minut, a odpowiedź MUST wskazać, że pochodzi z ustawień

#### Scenario: Temat już na liście

- **WHEN** operator zmienia domyślny odstęp, a na liście jest temat z odstępem 360 minut
- **THEN** temat MUST zachować 360 minut
