## Purpose

Od odpalenia reguły do wiadomości na telefonie: co pakiet zapisuje, kiedy ponawia, kiedy odpuszcza i co
chroni operatora przed zalaniem wiadomościami.

## ADDED Requirements

### Requirement: Odpalenie jest zapisane, zanim pójdzie wiadomość

Każde odpalenie MUST zostać zapisane z regułą, źródłem (zdarzeniem albo wartością warunku), treścią
po wypełnieniu szablonu i stanem, zanim pakiet poprosi bramę o wysyłkę. Wynik wysyłki MUST być
dopisany do tego zapisu: doręczone, odmowa z powodem bramy albo bramy nie da się zapytać.

#### Scenario: Brama odmawia

- **WHEN** brama odmawia wysyłki, bo adresat zablokował bota
- **THEN** odpalenie MUST mieć stan odmowy ze słowami bramy

### Requirement: Jedno źródło daje co najwyżej jedno powiadomienie na regułę

Para (reguła, zdarzenie) i para (reguła, zbocze warunku) MUST dać co najwyżej jedno odpalenie, także
przy ponownej publikacji, restarcie procesu w trakcie wysyłki i wielu instancjach procesu.

#### Scenario: Restart w trakcie wysyłki

- **WHEN** proces zostaje zatrzymany po zapisaniu odpalenia, a przed odpowiedzią bramy, i startuje ponownie
- **THEN** pakiet MUST NOT utworzyć drugiego odpalenia dla tej pary

### Requirement: Nieudana wysyłka jest ponawiana w oknie, a potem odpuszczana

Odpalenie, którego bramy nie dało się zapytać albo które dostało odmowę przejściową (limit szybkości),
MUST być ponawiane, nie wcześniej niż po czasie wskazanym przez bramę. Odpalenie starsze niż okno
ponowień z ustawień MUST zostać oznaczone jako odpuszczone i MUST NOT zostać wysłane. Odmowa trwała —
adresat nie istnieje, zablokował bota, jeszcze nie odbiera — MUST NOT być ponawiana.

Wiadomość o filmie z rana doręczona wieczorem, w stosie z dwudziestoma innymi, jest gorsza niż jej brak.

#### Scenario: Brama wraca po godzinie

- **WHEN** bramy nie da się zapytać przez godzinę, a okno ponowień to sześć godzin
- **THEN** odpalenia z tej godziny MUST zostać doręczone po jej powrocie

#### Scenario: Brama wraca po dwóch dniach

- **WHEN** bramy nie da się zapytać dłużej niż okno ponowień
- **THEN** odpalenia starsze niż okno MUST zostać odpuszczone i MUST NOT zostać wysłane

### Requirement: Reguła ma sufit wysyłek na godzinę

Reguła MUST NOT doręczyć więcej wiadomości w ciągu godziny niż sufit z ustawień pakietu. Odpalenia ponad
sufit MUST być zapisane jako zdławione i MUST NOT być wysyłane później. Pierwsze zdławienie w danej
godzinie MUST dać jedną wiadomość do adresata reguły mówiącą, że reguła została zdławiona i ile odpaleń pominięto do tej chwili.

Reguła „każdy post” ustawiona przez pomyłkę na archiwum, które właśnie nadrabia zaległości, to setki
wiadomości. Jedna wiadomość o zdławieniu mówi więcej niż one wszystkie.

#### Scenario: Zalew zdarzeń

- **WHEN** reguła pasuje do stu zdarzeń w ciągu minuty, a sufit to dziesięć na godzinę
- **THEN** MUST zostać doręczone dziesięć wiadomości i jedna wiadomość o zdławieniu

### Requirement: Brak bramy jest stanem wspieranym

Gdy brama Telegrama nie jest zamontowana w procesie, pakiet MUST przyjmować zdarzenia, sprawdzać
warunki i zapisywać odpalenia jako niedoręczalne z powodem „brak bramy”. Pakiet MUST NOT odmawiać
startu i MUST powiedzieć w trasie stanu, że nie doręcza.

#### Scenario: Proces bez bramy

- **WHEN** reguła odpala w procesie bez bramy Telegrama
- **THEN** odpalenie MUST zostać zapisane z powodem „brak bramy”, a trasa stanu MUST mówić, że pakiet nie doręcza
