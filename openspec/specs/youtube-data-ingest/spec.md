# youtube-data-ingest Specification

## Purpose
TBD - created by archiving change add-youtube-archive. Update Purpose after archive.
## Requirements
### Requirement: Odkrywanie jest czynnością pętli, nie skutkiem odczytu

Moduł MUST odkrywać, transkrybować, odczytywać i powiadamiać własną pętlą, w odstępie z ustawień.
Żadna trasa odczytu ani narzędzie czytające MUST NOT wywoływać dostawcy jako skutku ubocznego.
Jedynymi wyjątkami MUST być jawne akcje: dopisanie obserwacji, wyszukiwanie na żądanie oraz wskazanie
filmu do analizy — każda liczona w budżecie jak praca pętli. Film wskazany do analizy MUST być
transkrybowany, odczytany i, jeśli reguła każe, ogłoszony od razu, w tle, poza kolejką pętli, a odpowiedź
na wskazanie MUST wrócić bez czekania na wynik. Przetwarzanie takiego filmu MUST przestrzegać tych samych
sufitów, cen i ponowień co pętla, MUST NOT czekać na termin ponowienia ani na odstęp pętli i MUST NOT
biec równocześnie z przebiegiem pętli.

#### Scenario: Odczyt nie woła dostawcy

- **WHEN** klient czyta listę filmów
- **THEN** żaden dostawca MUST NOT zostać wywołany, a zużycie jednostek MUST zostać bez zmian

#### Scenario: Film wskazany ręcznie

- **WHEN** operator wskazuje film, który nie był jeszcze w archiwum
- **THEN** odpowiedź MUST wrócić od razu, a film MUST zostać transkrybowany i odczytany bez czekania na kolejny przebieg pętli
- **AND** inne filmy z kolejki MUST NOT zostać przez to przetworzone

#### Scenario: Film wskazany ponownie po braku napisów

- **WHEN** operator wskazuje film, który czeka na ponowienie
- **THEN** film MUST zostać zapytany teraz, nie po terminie ponowienia

#### Scenario: Film już odczytany

- **WHEN** operator wskazuje film, który ma już odczyt albo został porzucony
- **THEN** moduł MUST NOT wywołać żadnego dostawcy transkrypcji ani modelu

### Requirement: Stan filmu jest zapisany i ma koniec

Każdy film MUST mieć w archiwum stan: odkryty, oczekujący na transkrypcję, bez napisów,
przetranskrybowany, odczytany, powiadomiony, cichy albo porzucony. Film bez napisów MUST być
ponawiany w rosnących odstępach z ustawień i po ostatniej próbie MUST przejść w stan porzucony,
z którego pętla MUST NOT go podejmować.

Napisy automatyczne pojawiają się często godziny po publikacji, więc pierwsza porażka nie jest
ostateczna — ale każda próba kosztuje, więc ostatnia musi być.

#### Scenario: Napisy pojawiają się po czasie

- **WHEN** pierwsza próba transkrypcji kończy się brakiem napisów, a druga, po odstępie, sukcesem
- **THEN** film MUST przejść dalej do odczytu, a obie próby MUST być policzone w zużyciu

#### Scenario: Napisów nie ma nigdy

- **WHEN** wszystkie zaplanowane próby kończą się brakiem napisów
- **THEN** film MUST przejść w stan porzucony
- **AND** kolejne przebiegi pętli MUST NOT wywołać dla niego dostawcy

### Requirement: Każdy krok przebiegu ma limit partii

Każdy krok przebiegu — odkrywanie, transkrypcja, odczyt, powiadomienie — MUST przetwarzać nie więcej
niż limit z ustawień. Zaległość ponad limit MUST przejść na kolejny przebieg, a MUST NOT
przedłużać bieżącego.

#### Scenario: Kanał wrzuca naraz dwadzieścia filmów

- **WHEN** odkrycie zwraca więcej filmów niż limit transkrypcji
- **THEN** przebieg MUST przetranskrybować co najwyżej limit, a resztę zostawić na następne

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

### Requirement: Film jest jeden, niezależnie od tego, skąd przyszedł

Tożsamością filmu MUST być jego identyfikator YouTube. Film znaleziony przez kanał i wskazany ręcznie, także z listy
kandydatów, MUST być jednym filmem w archiwum, a jego pochodzenie MUST być odnotowane. Wyszukiwanie tematu MUST NOT
dopisywać filmu do archiwum ani pochodzenia do filmu, który już w nim jest. Pochodzenie `topic:N` filmów zauważonych
przed tą zmianą MUST zostać zachowane.

#### Scenario: Film z obserwowanego kanału trafia też do tematu

- **WHEN** wyszukiwanie tematu zwraca film, który jest już w archiwum z obserwowanego kanału
- **THEN** archiwum MUST mieć jeden film z niezmienionym pochodzeniem, a transkrypcja i odczyt MUST powstać raz
- **AND** film MUST NOT stać się kandydatem

