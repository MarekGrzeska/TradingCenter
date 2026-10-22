## MODIFIED Requirements

### Requirement: Film jest jeden, niezależnie od tego, skąd przyszedł

Tożsamością filmu MUST być jego identyfikator YouTube. Film znaleziony przez kanał i wskazany ręcznie, także z listy
kandydatów, MUST być jednym filmem w archiwum, a jego pochodzenie MUST być odnotowane. Wyszukiwanie tematu MUST NOT
dopisywać filmu do archiwum ani pochodzenia do filmu, który już w nim jest. Pochodzenie `topic:N` filmów zauważonych
przed tą zmianą MUST zostać zachowane.

#### Scenario: Film z obserwowanego kanału trafia też do tematu

- **WHEN** wyszukiwanie tematu zwraca film, który jest już w archiwum z obserwowanego kanału
- **THEN** archiwum MUST mieć jeden film z niezmienionym pochodzeniem, a transkrypcja i odczyt MUST powstać raz
- **AND** film MUST NOT stać się kandydatem
