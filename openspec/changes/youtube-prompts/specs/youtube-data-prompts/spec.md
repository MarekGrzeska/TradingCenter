## Purpose

Prompty analizy filmów jako dane operatora: z wersjami, z jednym promptem, którego nie da się usunąć, przypisane do
kanału, tematu i filmu, oraz kolejny odczyt filmu wybranym promptem.

## ADDED Requirements

### Requirement: Prompt jest daną operatora i ma wersje

Moduł MUST przechowywać prompty analizy jako dane: nazwę, unikalną wśród nieusuniętych promptów, i treść, niepustą i
nie dłuższą niż limit ogłoszony przez kontrakt. Kontrakt MUST pozwalać odczytać listę promptów, utworzyć prompt,
zmienić jego nazwę albo treść i usunąć go. Zmiana treści MUST tworzyć nową wersję promptu i MUST NOT zmieniać
treści wersji, którą powstał już jakikolwiek odczyt. Każdy odczyt MUST nieść prompt i wersję, którą powstał.

#### Scenario: Edycja promptu z odczytami

- **WHEN** operator zmienia treść promptu, którym odczytano już filmy
- **THEN** prompt MUST mieć nową wersję, a dotychczasowe odczyty MUST nadal wskazywać wersję, którą powstały

#### Scenario: Nazwa już zajęta

- **WHEN** operator tworzy prompt o nazwie, którą nosi inny nieusunięty prompt
- **THEN** kontrakt MUST odmówić z powodem i MUST NOT zapisać niczego

### Requirement: Zawsze istnieje co najmniej jeden prompt

Moduł MUST zasiać jeden prompt przy migracji, z treścią czytającą film rynkowo. Zasianego promptu MUST NOT dać się
usunąć; MUST dać się zmienić jego nazwę i treść jak każdego innego. Wszystko, co przed zmianą niosło profil analizy
`market` — kanały, tematy, filmy i odczyty — MUST wskazywać zasiany prompt.

#### Scenario: Próba usunięcia zasianego promptu

- **WHEN** klient usuwa zasiany prompt
- **THEN** kontrakt MUST odmówić z powodem, a prompt MUST zostać

#### Scenario: Edycja zasianego promptu

- **WHEN** operator zmienia treść zasianego promptu
- **THEN** zmiana MUST zostać przyjęta jako nowa wersja

### Requirement: Usunięcie promptu nie gubi odczytów

Prompt przypisany do kanału albo tematu MUST NOT dać się usunąć; odmowa MUST nazwać te kanały i tematy. Usunięty
prompt MUST zniknąć z listy promptów i z wyborów, a odczyty, które nim powstały, MUST zostać i MUST nadal nieść jego
nazwę i wersję.

#### Scenario: Prompt przypisany do kanału

- **WHEN** operator usuwa prompt przypisany do kanału
- **THEN** kontrakt MUST odmówić, nazywając kanał

#### Scenario: Prompt z odczytami usunięty

- **WHEN** operator usuwa nieprzypisany prompt, którym odczytano film
- **THEN** film MUST nadal pokazywać ten odczyt z nazwą promptu

### Requirement: Kanał i temat czytają nowe filmy swoim promptem

Każdy kanał i temat MUST mieć przypisany dokładnie jeden prompt; dopisanie bez wskazania promptu MUST przypisać
zasiany. Film MUST dostać prompt źródła w chwili, gdy zostaje zauważony, a film wskazany do analizy — prompt wskazany
razem z nim albo zasiany. Ten prompt MUST być promptem filmu: pętla MUST czytać film właśnie nim. Zmiana promptu
kanału albo tematu MUST dotyczyć filmów zauważonych od tej chwili i MUST NOT zmieniać promptu filmów już zauważonych.

#### Scenario: Zmiana promptu kanału

- **WHEN** operator zmienia prompt kanału, którego filmy są już odczytane
- **THEN** nowe filmy kanału MUST być czytane nowym promptem, a odczyty starszych MUST zostać bez zmian

#### Scenario: Prompt usunięty z wyboru

- **WHEN** klient przypisuje kanałowi prompt usunięty albo nieistniejący
- **THEN** kontrakt MUST odmówić z powodem

### Requirement: Film może mieć kilka odczytów

Operator MUST móc zamówić odczyt przetranskrybowanego filmu wybranym promptem; odczyt MUST stanąć obok
odczytów innymi promptami, a odczyt tym samym promptem MUST zostać zastąpiony nowym, powstałym bieżącą wersją.
Zamówienie MUST NOT wołać dostawcy transkrypcji, MUST liczyć się w dziennym limicie tokenów i MUST zostać odrzucone
z powodem, gdy film nie ma transkrypcji albo limit dnia jest wyczerpany.

#### Scenario: Drugi prompt na odczytanym filmie

- **WHEN** operator zamawia odczyt filmu z odczytem promptem kanału innym promptem
- **THEN** film MUST mieć oba odczyty, a dostawca transkrypcji MUST NOT zostać zawołany

#### Scenario: Film bez transkrypcji

- **WHEN** operator zamawia odczyt filmu, który nie ma transkrypcji
- **THEN** kontrakt MUST odmówić z powodem

### Requirement: Prompt zmienia polecenie, nie granice

Treść promptu MUST decydować wyłącznie o tym, czego model szuka w filmie i jak układa tekst odczytu. Oznaczenie
transkrypcji jako danej obcej, brak narzędzi i historii oraz kształt odpowiedzi MUST obowiązywać przy każdym
prompcie, niezależnie od jego treści.

#### Scenario: Prompt prosi o inny kształt

- **WHEN** treść promptu każe modelowi odpowiedzieć listą instrumentów zamiast tekstu
- **THEN** zapisany odczyt MUST mieć kształt odczytu albo MUST NOT zostać zapisany
