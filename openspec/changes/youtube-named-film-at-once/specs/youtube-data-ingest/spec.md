## MODIFIED Requirements

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
