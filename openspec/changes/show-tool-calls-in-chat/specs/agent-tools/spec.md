## MODIFIED Requirements

### Requirement: Wywołanie narzędzia zostawia ślad

Każde wykonane wywołanie narzędzia MUST zostawić zapis niosący: sesję i wypowiedź agenta,
w ramach której padło, kolejność w turze, nazwę narzędzia, argumenty, to czy się
powiodło, oraz wynik albo powód odmowy i czas trwania.

Zapis MUST powstać także wtedy, gdy wywołanie zakończyło się odmową, i także wtedy, gdy
tura zakończyła się niepełną odpowiedzią. Wywołanie, które kosztowało czas i pieniądze i
nie zostawiło śladu, jest wywołaniem, o którym nie da się już powiedzieć nic.

Ślad MUST być czytelny dla wołającego, a nie wyłącznie zapisany. Odczyt transkryptu MUST
zwracać wywołania przy wypowiedzi agenta, w ramach której padły, w kolejności, w jakiej
padły. Ślad, po który trzeba sięgnąć zapytaniem do bazy, jest śladem, którego operator nie
ma — a odróżnienie „archiwum nie ma danych" od „narzędzie nie odpowiedziało" jest możliwe
wyłącznie z niego.

Kolejność MUST być odtwarzalna z samej odpowiedzi: dwa wywołania tej samej tury MUST dać
się ustawić względem siebie bez sięgania po ich czas zapisu.

#### Scenario: Tura z kilkoma wywołaniami

- **WHEN** model wywołuje w jednej turze trzy narzędzia
- **THEN** powstają trzy zapisy wskazujące tę samą wypowiedź agenta
- **AND** ich kolejność w turze da się odtworzyć

#### Scenario: Wywołanie zakończone odmową

- **WHEN** wywołanie narzędzia kończy się odmową serwera
- **THEN** zapis powstaje i niesie powód odmowy

#### Scenario: Transkrypt niesie wywołania

- **WHEN** wołający odczytuje transkrypt sesji, w której agent sięgał po narzędzia
- **THEN** przy wypowiedzi agenta przychodzą wywołania, które ją poprzedziły
- **AND** każde niesie nazwę, argumenty, to jak się skończyło, wynik albo powód odmowy
  oraz czas trwania

#### Scenario: Wypowiedź bez narzędzi

- **WHEN** wołający odczytuje wypowiedź, przy której nie padło żadne wywołanie
- **THEN** dostaje pustą listę wywołań, a nie brak pola
- **AND** MUST NOT dać się jej pomylić z wypowiedzią, przy której wywołania odpadły po
  drodze
