## Purpose

Daje sondzie z zewnątrz sposób odróżnienia martwego kontenera market-data od zdrowego, po
prostu chwilowo bezczynnego — bez przechodzenia przez uwierzytelnianie, które przed
kontenerem odpowiada identycznie w obu przypadkach.

## ADDED Requirements

### Requirement: Sonda dostępności odpowiada bez uwierzytelnienia

Warstwa uwierzytelniająca stojąca przed modułem (Easy Auth) odpowiada 401 dla każdej trasy
poza jawnie wyłączonymi — a to samo 401 dostaje sonda pytająca martwy kontener, co
uwierzytelniony klient pytający żywy. Moduł MUST wystawiać trasę dowodzącą, że proces żyje
i odpowiada, dostępną bez żadnego poświadczenia — ani ticketu strumienia, ani tożsamości
platformy.

#### Scenario: Żądanie bez poświadczenia

- **WHEN** dowolny klient odpytuje trasę dostępności bez żadnego poświadczenia
- **THEN** moduł odpowiada, potwierdzając, że proces żyje

### Requirement: Odpowiedź dowodzi tylko tego, że proces żyje

Trasa MUST zwracać stałą, minimalną treść niezależną od stanu archiwum, kolekcji par czy
połączenia z bramką — nie od tego, czy baza odpowiada, czy dowolna para jest `STALLED`, czy
gateway jest osiągalny. Moduł MUST NOT umieszczać w odpowiedzi żadnych danych pochodzących
z bazy danych, z bramki ani ze stanu śledzonych par.

To rozróżnienie jest zamierzone: trasa mówi, że proces żyje, nie że jego zależności są
zdrowe. Sprawdzanie zależności zamieniłoby sondę „żywy kontener" w drugą kopię
`collection_state` i uczyniłoby ją fałszywie czerwoną akurat wtedy, gdy jedyne, co jest
zepsute, to coś, co ma już własny alarm.

#### Scenario: Baza danych nieosiągalna

- **WHEN** baza danych jest chwilowo nieosiągalna, a proces market-data działa
- **THEN** trasa dostępności nadal odpowiada, potwierdzając, że proces żyje

#### Scenario: Odpowiedź nie niesie danych archiwum

- **WHEN** dowolny klient odpytuje trasę dostępności
- **THEN** odpowiedź nie zawiera danych o śledzonych parach, świecach ani stanie kolekcji

### Requirement: Sonda dostępności nie zastępuje uwierzytelnionych tras

Moduł MUST NOT udostępniać przez tę trasę niczego, co gdzie indziej wymaga uwierzytelnienia
— ani danych archiwum, ani zarządzania śledzonymi parami, ani wydawania poświadczeń
strumienia. Zakres odpowiedzi zostaje ograniczony do samego faktu, że proces odpowiada.

#### Scenario: Próba wyciągnięcia czegokolwiek ponad status

- **WHEN** klient odpytuje trasę dostępności, oczekując danych o archiwum
- **THEN** odpowiedź nie zawiera niczego poza potwierdzeniem, że proces żyje
