## Purpose

Która decyzja platformy strategii jest warta powiadomienia operatora, i dlaczego pętla licząca ją co
przebieg nie zamienia tego w powtarzalny alarm.

## ADDED Requirements

### Requirement: Powiadamia wejście, nie każdy przebieg

Moduł MUST wysłać powiadomienie o decyzji wskazującej zagranie i MUST NOT wysyłać go o decyzji
odmawiającej zagrania.

Odmowa jest zwykłym wynikiem oceny i zdarza się w większości przebiegów; powiadamianie o niej
zamieniłoby kanał w szum, przez który nie przebije się to jedno, o co chodzi.

#### Scenario: Decyzja o zagraniu

- **WHEN** przebieg pętli kończy się decyzją wskazującą zagranie
- **THEN** moduł MUST wysłać o niej powiadomienie

#### Scenario: Decyzja odmowna

- **WHEN** przebieg pętli kończy się odmową zagrania
- **THEN** moduł MUST NOT wysyłać powiadomienia

### Requirement: Ta sama decyzja nie powiadamia dwa razy

Moduł MUST powiadamiać wyłącznie wtedy, gdy decyzja dla danej obserwacji jest zmianą względem
poprzedniej zapisanej dla niej decyzji. Decyzja powtórzona w kolejnym przebiegu MUST NOT wywoływać
drugiego powiadomienia.

Pętla ocenia obserwację przy każdej zamkniętej świecy, więc jedno wejście, które jest ważne przez
dziesięć świec, jest dziesięcioma identycznymi decyzjami.

#### Scenario: Wejście utrzymuje się przez kolejne przebiegi

- **WHEN** kolejny przebieg dochodzi do tej samej decyzji co poprzedni dla tej samej obserwacji
- **THEN** moduł MUST NOT wysłać drugiego powiadomienia

### Requirement: Znacznik jest stawiany po udanej wysyłce

Moduł MUST oznaczyć decyzję jako zapowiedzianą dopiero po odpowiedzi bramy oznaczającej powodzenie.
Nieudana wysyłka MUST NOT stawiać znacznika.

Tak samo jak w `social-data-alerts`, i z tego samego powodu: brama nie pamięta wysłanych wiadomości,
więc brak znacznika jest jedynym mechanizmem ponowienia, jaki tu jest.

#### Scenario: Brama odmawia

- **WHEN** brama odmawia wysłania powiadomienia o decyzji
- **THEN** decyzja MUST zostać zapisana normalnie i MUST NOT dostać znacznika

### Requirement: Brak bramy nie zatrzymuje oceniania

Moduł MUST oceniać obserwacje i zapisywać decyzje normalnie, gdy adres bramy nie jest ustawiony.
Powiadamianie MUST być wtedy pominięte bez wpływu na decyzję i bez błędu.

Platforma strategii decyduje, a wykonaniem zajmuje się kto inny — więc niemożność powiedzenia o
decyzji MUST NOT być powodem, żeby jej nie podjąć.

#### Scenario: Brama nieskonfigurowana

- **WHEN** adres bramy nie jest ustawiony, a przebieg kończy się decyzją o zagraniu
- **THEN** decyzja MUST zostać zapisana, a przebieg MUST zakończyć się powodzeniem
