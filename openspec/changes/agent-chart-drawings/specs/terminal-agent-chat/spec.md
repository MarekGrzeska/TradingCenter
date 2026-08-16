## MODIFIED Requirements

### Requirement: Panel mówi, że wykres zmienił agent

Terminal MUST czytać nowe polecenia agenta **po zakończonej turze** oraz **po wejściu na
stronę** — pierwsze po to, żeby zmiana była widoczna od razu, drugie po to, żeby polecenie
wydane przed zamknięciem karty nie przepadło.

Zastosowanie polecenia MUST być widoczne dla operatora: panel MUST powiedzieć, że wykres
został zmieniony przez agenta, i czego zmiana dotyczyła. Wykres zmieniający się sam, bez
zdania o tym, czyta się jak usterka.

Panel MUST powiedzieć także o obiektach naniesionych i skasowanych przez agenta
(`agent-chart-drawings`), tą samą drogą i w tej samej chwili co o poleceniu wykresu.
Rysunek, który pojawił się na wykresie bez zdania o tym, jest zmianą, której operator nie
umie przypisać do niczyjej ręki.

Panel MUST wysyłać w żądaniu tury migawkę tego, co rysuje aktywny slot, żeby model mówił
o widocznym wykresie.

Nieudany odczyt poleceń MUST NOT przerywać rozmowy ani czyścić wykresu: panel MUST
pokazywać rozmowę dalej, a polecenie zostanie zastosowane przy następnym udanym odczycie.
To samo MUST dotyczyć nieudanego odczytu naniesionych obiektów.

#### Scenario: Agent zmienia wykres w trakcie rozmowy

- **WHEN** agent kończy turę, w której ustawił wskaźniki
- **THEN** wykres pokazuje je bez odświeżania strony
- **AND** panel mówi, że to agent je ustawił

#### Scenario: Agent nanosi opór w trakcie rozmowy

- **WHEN** agent kończy turę, w której naniósł opór
- **THEN** wykres pokazuje go bez odświeżania strony
- **AND** panel mówi, że to agent go naniósł

#### Scenario: Polecenie wydane przed zamknięciem karty

- **WHEN** operator wraca do terminala po tym, jak agent ustawił wykres w poprzedniej sesji przeglądarki
- **THEN** polecenie zostaje zastosowane raz, przy wejściu na stronę

#### Scenario: Odczyt poleceń zawiódł

- **WHEN** odczyt poleceń agenta się nie powiódł
- **THEN** rozmowa i wykres zostają takie, jakie były
