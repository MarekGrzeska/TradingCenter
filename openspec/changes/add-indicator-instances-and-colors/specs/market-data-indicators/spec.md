## MODIFIED Requirements

### Requirement: Jedno żądanie liczy wiele wskaźników na wspólnej osi czasu

Moduł MUST przyjmować w jednym żądaniu listę wskaźników z parametrami i MUST odpowiadać jedną osią
znaczników czasu wspólną dla wszystkich wyników. Odpowiedź MUST powtarzać parametry każdego
wskaźnika, żeby dwa warianty tego samego wskaźnika dały się rozróżnić.

Wyniki MUST wracać w kolejności zamówionych wskaźników — n-ty wynik odpowiada n-temu zamówieniu,
także wtedy, gdy dwa zamówienia mają ten sam identyfikator i te same parametry, i także wtedy, gdy
któreś z nich wraca z przyczyną zamiast wartości. Identyfikator i parametry same w sobie MUST NOT
być jedynym sposobem powiązania wyniku z zamówieniem, bo nie odróżniają zamówień identycznych.

#### Scenario: Kilka wskaźników naraz

- **WHEN** konsument prosi o kilka różnych wskaźników dla jednego zakresu
- **THEN** dostaje je w jednej odpowiedzi, ułożone na jednej osi czasu

#### Scenario: Ten sam wskaźnik z różnymi parametrami

- **WHEN** konsument prosi dwa razy o ten sam wskaźnik z różnymi parametrami
- **THEN** dostaje dwa osobne wyniki, każdy z powtórzonymi parametrami

#### Scenario: Kolejność wyników

- **WHEN** konsument zamawia kilka wskaźników w wybranej przez siebie kolejności
- **THEN** wyniki wracają w tej samej kolejności, po jednym na każde zamówienie

#### Scenario: Dwa identyczne zamówienia

- **WHEN** konsument zamawia dwa razy ten sam wskaźnik z tymi samymi parametrami
- **THEN** dostaje dwa wyniki, na pierwszej i drugiej pozycji odpowiadających tym zamówieniom
