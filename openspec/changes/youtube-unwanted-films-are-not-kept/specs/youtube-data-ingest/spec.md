## MODIFIED Requirements

### Requirement: Filmy, których nie warto czytać, są pomijane jawnie

Moduł MUST NIE przechowywać filmów krótszych niż próg z ustawień ani dłuższych niż próg z ustawień,
gdy ich długość jest znana: taki film MUST NOT zostać zapisany przy odkryciu, a film, który okaże się
poza progami po zapisaniu, MUST zostać usunięty w przebiegu pętli. Film poza progami wskazany ręcznie
MUST zostać odrzucony z powodem, bez zapisu. Transmisja, która jeszcze trwa, MUST zostać podjęta
ponownie, gdy się zakończy; film o nieznanej długości MUST NOT być usuwany ani odrzucany.

#### Scenario: Transmisja na żywo

- **WHEN** odkryty film jest trwającą transmisją
- **THEN** moduł MUST NOT prosić o transkrypcję, dopóki transmisja trwa

#### Scenario: Film ponad limit długości

- **WHEN** źródło listuje film dłuższy niż próg
- **THEN** film MUST NOT trafić do archiwum ani do dostawcy, także gdy źródło listuje go przy każdym przebiegu

#### Scenario: Film, który okazuje się za krótki po zapisaniu

- **WHEN** premiera została zapisana bez długości, a źródło podaje potem długość poniżej progu
- **THEN** film MUST zostać usunięty w następnym przebiegu

#### Scenario: Short wskazany ręcznie

- **WHEN** operator wskazuje film krótszy niż próg
- **THEN** wskazanie MUST zostać odrzucone z powodem, a archiwum MUST NOT zawierać tego filmu
