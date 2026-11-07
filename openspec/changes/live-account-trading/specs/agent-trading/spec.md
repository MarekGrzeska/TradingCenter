## ADDED Requirements

### Requirement: Rozmowa nie sięga konta realnego

Rozmowa MUST NOT mieć żadnej drogi do serwera narzędzi konta realnego: jej narzędzia rachunku MUST pochodzić wyłącznie z
instancji demo, a ustawienie adresu albo klucza serwera konta realnego MUST być czytane tylko przez pakiet zespołów. Żadna
konfiguracja rozmowy MUST NOT tego zmieniać. Granice handlowe, których ten moduł nie narzuca, pozostają nienarzucone, bo
uzasadnienie — rachunek demonstracyjny wymuszony u gatewaya — nadal jest prawdziwe dla każdej rozmowy.

Rozmowa nie przechodzi przez człowieka przed każdym wywołaniem: model decyduje w turze. Dlatego jest jedynym wołającym,
który na konto realne nie dostaje się w ogóle, zamiast dostać się za przełącznikiem.

#### Scenario: Operator pyta rozmowę o konto realne

- **WHEN** operator prosi agenta w terminalu o pozycje albo zlecenie na koncie realnym
- **THEN** agent nie ma narzędzia, które sięga konta realnego, i mówi, że go nie widzi

#### Scenario: Ustawienie serwera konta realnego w środowisku workbencha

- **WHEN** środowisko workbencha niesie adres i klucz serwera narzędzi konta realnego
- **THEN** narzędzia rachunku rozmowy nadal pochodzą wyłącznie z instancji demo
