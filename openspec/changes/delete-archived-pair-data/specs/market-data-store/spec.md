## ADDED Requirements

### Requirement: Skasowanie danych pary zdejmuje też jej pokrycie

Zakres pokrycia jest zapisem tego, że dane dla danego przedziału zostały zweryfikowane. Po usunięciu
świec taki zapis mówi nieprawdę i, co gorsza, jest wiążący dla planowania: przedział uchodzący za
pokryty nie zostanie pobrany ponownie. Archiwum MUST usuwać świece pary i jej zakresy pokrycia
razem, w jednej niepodzielnej operacji — MUST NOT być stanu pośredniego, w którym pokrycie przeżyło
świece, ani takiego, w którym świece przeżyły pokrycie.

Skasowanie MUST dotyczyć wyłącznie wskazanej pary (symbol i rozdzielczość) — dane innych
archiwizowanych rozdzielczości tego samego symbolu MUST zostać nietknięte, bo każda z nich jest
osobną decyzją operatora.

Wyjątkiem są świece wyliczone z serii kasowanej: są jej projekcją, a nie osobno zebranymi danymi.
Skasowanie serii, z której zostały wyliczone, MUST usunąć je razem z nią — inaczej archiwum
odpowiadałoby na pytanie o rozdzielczość pochodną danymi, których źródło operator kazał usunąć.

#### Scenario: Skasowanie danych pary

- **WHEN** dane pary zostają skasowane
- **THEN** ani jedna świeca tej pary nie pozostaje w archiwum
- **AND** ani jeden zakres pokrycia tej pary nie pozostaje w archiwum

#### Scenario: Kasowanie przerwane w połowie

- **WHEN** kasowanie danych pary nie może dojść do końca
- **THEN** archiwum zostaje w stanie sprzed kasowania
- **AND** MUST NOT zostać para bez świec, ale z zachowanym pokryciem

#### Scenario: Zapytanie o okres po skasowaniu

- **WHEN** konsument pyta o okres, który przed skasowaniem był pokryty
- **THEN** archiwum stwierdza, że tego okresu nie zebrało
- **AND** MUST NOT stwierdzać, że rynek był wtedy zamknięty

#### Scenario: Inna rozdzielczość tego samego symbolu

- **WHEN** zostaje skasowana jedna rozdzielczość symbolu archiwizowanego w kilku
- **THEN** świece i pokrycie pozostałych archiwizowanych rozdzielczości tego symbolu zostają
  nietknięte

#### Scenario: Skasowanie serii, z której wyliczane są inne

- **WHEN** zostaje skasowana seria, z której archiwum wylicza rozdzielczości pochodne tego symbolu
- **THEN** wyliczone z niej świece również przestają istnieć
- **AND** zapytanie o rozdzielczość pochodną tego symbolu MUST NOT odpowiadać danymi wyliczonymi
  przed skasowaniem
