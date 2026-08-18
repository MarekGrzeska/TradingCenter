## MODIFIED Requirements

### Requirement: Opis narzędzia jest częścią kontraktu

Opis narzędzia jest jedyną rzeczą, którą model o nim wie, więc MUST być traktowany jak
kontrakt, a nie jak komentarz. Każde publikowane narzędzie MUST nieść opis, typowane
parametry, wpisany sufit swojej odpowiedzi oraz jawnie nazwane jednostki, strefę czasową
i stronę ceny, z której liczone są świece.

#### Scenario: Narzędzie bez kompletnego opisu

- **WHEN** do zestawu trafia narzędzie bez opisu, bez wpisanego sufitu albo bez nazwanych
  jednostek
- **THEN** MUST to wywrócić test powierzchni narzędzi, zanim moduł zostanie wdrożony

#### Scenario: Czas jest jednoznaczny

- **WHEN** narzędzie przyjmuje albo zwraca moment w czasie
- **THEN** jego opis MUST nazywać strefę, a odpowiedź MUST podawać moment w UTC

## ADDED Requirements

### Requirement: Powierzchnia narzędzi ma zapisany sufit

Cały zestaw — opisy, schematy wejścia i schematy wyjścia razem — jest czytany przez model w
**każdej** turze rozmowy, więc jego rozmiar jest kosztem, nie szczegółem implementacji.
Moduł MUST trzymać zserializowaną postać tego, co ogłasza, poniżej sufitu zapisanego w jego
własnym teście, i MUST wywrócić ten test, gdy sufit zostanie przekroczony.

Moduł MUST NOT publikować w schemacie rzeczy, które nie niosą modelowi informacji ponad to,
co sam schemat już mówi. Sufit bez tej zasady byłby budżetem wydawanym na rusztowanie
zamiast na treść.

Sufit jest liczbą do zmierzenia i do obniżenia, a nie granicą naturalną: podniesienie go
MUST być świadomą zmianą tego testu, nie skutkiem ubocznym dodania narzędzia.

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
