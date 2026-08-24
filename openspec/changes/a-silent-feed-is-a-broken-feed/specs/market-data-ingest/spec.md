## MODIFIED Requirements

### Requirement: Nasłuch na żywo dla każdej śledzonej pary

Moduł MUST utrzymywać subskrypcję strumienia `capital-gateway` dla każdej śledzonej pary i zapisywać
świece w chwili ich zamknięcia. Subskrypcja MUST być wznawiana po zerwaniu, dopóki para pozostaje
śledzona.

Subskrypcja, przez którą nic nie przychodzi, nie jest zerwana — i to jest cały problem: pętla
wznawiania jej nie dotyka, a wraz z nią nie rusza domykanie luki, które na wznowieniu wisi.
Zmierzone 24 sierpnia 2026: nasłuch jednej pary trwał czterdzieści godzin bez ani jednego
zerwania, nie dostając przez ostatnie czternaście z nich żadnej wiadomości. Moduł MUST więc
traktować brak jakiejkolwiek wiadomości na subskrypcji przez czas dłuższy niż własny próg jak jej
koniec, i przejść tą samą drogą co po zerwaniu: domknąć lukę i subskrybować ponownie.

Próg MUST być dłuższy niż najdłuższa cisza, jakiej moduł oczekuje po zdrowym strumieniu, i MUST
być liczony od ostatniej wiadomości dowolnego rodzaju, nie od ostatniej świecy: strumień niesie
także kwotowania i statusy, a to one — nie zamknięte świece — są dowodem, że połączenie żyje.
Świeca zamknięta na rozdzielczości dziennej pada raz na dobę i próg liczony od niej mierzyłby
rozdzielczość, a nie połączenie.

#### Scenario: Świeca się zamyka

- **WHEN** strumień przynosi zamkniętą świecę śledzonej pary
- **THEN** moduł zapisuje ją w archiwum

#### Scenario: Połączenie ze strumieniem pada

- **WHEN** subskrypcja zostaje zerwana, a para nadal jest śledzona
- **THEN** moduł ponawia połączenie z rosnącym odstępem między próbami
- **AND** po wznowieniu domyka lukę powstałą w czasie przerwy

#### Scenario: Subskrypcja milczy

- **WHEN** przez subskrypcję śledzonej pary nie przyszła żadna wiadomość dłużej niż próg ciszy,
  a połączenie nadal jest otwarte
- **THEN** moduł kończy tę subskrypcję i zaczyna ją od nowa
- **AND** przed ponownym nasłuchem domyka lukę powstałą w czasie ciszy
