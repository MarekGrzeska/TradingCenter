## ADDED Requirements

### Requirement: Profil kosztów instrumentu ustawia operator

Pakiet MUST przechowywać co najwyżej jeden profil kosztów na instrument, o tym samym kształcie i z tym samym sprawdzeniem
co model kosztów uruchomienia. Profil ustawia i zmienia operator przez REST. Uruchomienie korzystające z profilu MUST
zapisywać wartości kosztów, a nie odwołanie do profilu. Zmiana profilu MUST NOT zmieniać żadnego wcześniej zapisanego
uruchomienia.

#### Scenario: Zmiana profilu po uruchomieniu

- **WHEN** operator zmienia spread w profilu instrumentu, który ma już zakończone uruchomienie
- **THEN** koszty zapisane w tamtym uruchomieniu MUST pozostać takie, jakie były

#### Scenario: Profil z niepełnym profilem spreadu

- **WHEN** operator zapisuje profil, którego godzinowy profil spreadu ma 23 wartości
- **THEN** zapis MUST zostać odrzucony z tym samym problemem, jaki dostałby model kosztów uruchomienia

### Requirement: Uruchomienie pamięta, kto o nie poprosił

Każde uruchomienie MUST zapisywać, czy zlecił je operator (REST), czy agent (narzędzie rozmowy). Uruchomienia zapisane
przed tą zmianą MUST być przypisane operatorowi. Licznik prób MUST liczyć uruchomienia obu zlecających tak samo.

#### Scenario: Uruchomienie z rozmowy

- **WHEN** agent zleca uruchomienie, które się kończy
- **THEN** uruchomienie MUST mieć zlecającego `agent`, a licznik prób strategii MUST wzrosnąć o jeden
