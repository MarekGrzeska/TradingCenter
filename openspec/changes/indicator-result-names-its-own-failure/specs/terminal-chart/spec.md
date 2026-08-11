## MODIFIED Requirements

### Requirement: Wykres mówi, gdy wskaźników nie da się policzyć

Nieudany odczyt wskaźników MUST NOT ukrywać świec, które przyszły. Wykres MUST pokazywać serię
i osobno mówić, że wskaźników nie udało się policzyć, wraz z możliwością ponowienia.

Odmowa źródła — na przykład przekroczony sufit żądania albo nieznany wskaźnik — MUST być pokazana
jako powód, który da się usunąć, a nie jako awaria.

Gdy źródło odpowiedziało, ale część zamówionych wskaźników wróciła z przyczyną zamiast wartości,
wykres MUST narysować te policzone i MUST nazwać po identyfikatorze te, których nie policzono,
razem z przyczyną każdego. MUST NOT ukrywać z tego powodu wskaźników policzonych.

Wskaźnik, który wrócił z przyczyną, MUST pozostać wybrany — zarówno na wykresie, jak i w tym, co
zapamiętał slot siatki. Wybór należy do operatora i wykres MUST NOT cofać go za niego; gdy
brakująca seria zostanie zebrana, wskaźnik MUST zacząć się rysować bez ponownego wybierania.

#### Scenario: Odczyt wskaźników zawiódł

- **WHEN** świece przyszły, a odczyt wskaźników się nie powiódł
- **THEN** wykres rysuje świece i mówi, że wskaźniki są niedostępne, dając ponowić

#### Scenario: Odmowa z powodu sufitu

- **WHEN** źródło odmawia, bo zamówiono zbyt wiele wskaźników naraz
- **THEN** wykres podaje ten powód, zamiast zgłaszać ogólny błąd

#### Scenario: Część wskaźników policzona, część z przyczyną

- **WHEN** źródło odpowiada, a jeden z wybranych wskaźników niesie przyczynę zamiast wartości
- **THEN** wykres rysuje pozostałe i osobno nazywa ten jeden wraz z jego przyczyną

#### Scenario: Nieudany wskaźnik zostaje wybrany

- **WHEN** wybrany wskaźnik wraca z przyczyną zamiast wartości
- **THEN** zostaje zaznaczony w wyborze i zapamiętany przez slot, zamiast zostać odznaczonym

#### Scenario: Brakująca seria zostaje zebrana

- **WHEN** archiwum zaczyna mieć serię, której brakowało nieudanemu wskaźnikowi, a wykres pyta o wskaźniki ponownie
- **THEN** wskaźnik rysuje się bez ponownego wybierania go przez operatora
