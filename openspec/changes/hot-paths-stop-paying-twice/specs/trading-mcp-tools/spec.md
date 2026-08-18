## ADDED Requirements

### Requirement: Opis narzędzia jest częścią kontraktu

Opis narzędzia jest jedyną rzeczą, którą model o nim wie, zanim je zawoła, więc MUST być
traktowany jak kontrakt, a nie jak komentarz. Każde publikowane narzędzie MUST nieść opis,
typowane parametry i jawnie nazwane jednostki — rozmiar, poziom ceny i walutę, w której
podawane są saldo i wynik.

W module, którego narzędzia ruszają rachunek, przemilczana jednostka nie jest
niedopowiedzeniem: rozmiar wzięty za kontrakty zamiast za jednostki instrumentu jest
zleceniem o innej wielkości, złożonym bez błędu.

#### Scenario: Narzędzie bez nazwanych jednostek

- **WHEN** do zestawu trafia narzędzie zapisujące bez opisu albo bez nazwanej jednostki
  rozmiaru
- **THEN** MUST to wywrócić test powierzchni narzędzi, zanim moduł zostanie wdrożony

### Requirement: Powierzchnia narzędzi ma zapisany sufit

Cały zestaw — opisy, schematy wejścia i schematy wyjścia razem — jest czytany przez model w
**każdej** turze rozmowy, więc jego rozmiar jest kosztem, nie szczegółem implementacji.
Moduł MUST trzymać zserializowaną postać tego, co ogłasza, poniżej sufitu zapisanego w jego
własnym teście, i MUST wywrócić ten test, gdy sufit zostanie przekroczony.

Moduł MUST NOT publikować w schemacie rzeczy, które nie niosą modelowi informacji ponad to,
co sam schemat już mówi.

#### Scenario: Zestaw urósł ponad sufit

- **WHEN** zmiana dokłada narzędzie, pole albo akapit opisu, po którym zserializowany
  zestaw przekracza sufit
- **THEN** test powierzchni narzędzi MUST wywrócić się, nazywając zmierzoną wielkość i sufit
- **AND** moduł MUST NOT zostać wdrożony, dopóki jedno z dwóch nie zostanie zmienione świadomie

#### Scenario: Schemat bez rusztowania

- **WHEN** model czyta ogłoszony schemat narzędzia
- **THEN** schemat MUST NOT nieść nazw pól powtórzonych jako ich własne etykiety ani
  wartości domyślnych dla odpowiedzi, której model nie konstruuje
- **AND** MUST nadal nieść każde pole, jego typ i to, czy jest wymagane
