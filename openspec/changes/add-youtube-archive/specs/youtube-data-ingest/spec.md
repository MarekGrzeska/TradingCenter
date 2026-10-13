## Purpose

Pętla archiwum YouTube: jak moduł zauważa nowe filmy, jaką drogę przechodzi każdy film od
odkrycia do alertu i co gwarantuje, że film bez napisów nie kosztuje bez końca.

## ADDED Requirements

### Requirement: Odkrywanie jest czynnością pętli, nie skutkiem odczytu

Moduł MUST odkrywać, transkrybować, odczytywać i powiadamiać własną pętlą, w odstępie z ustawień.
Żadna trasa odczytu ani narzędzie czytające MUST NOT wywoływać dostawcy jako skutku ubocznego.
Jedynymi wyjątkami MUST być jawne akcje: dopisanie obserwacji, wskazanie filmu do analizy oraz
wyszukiwanie na żądanie — każda liczona w budżecie jak praca pętli.

#### Scenario: Odczyt nie woła dostawcy

- **WHEN** klient czyta listę filmów
- **THEN** żaden dostawca MUST NOT zostać wywołany, a zużycie jednostek MUST zostać bez zmian

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

Moduł MUST pomijać filmy krótsze niż próg z ustawień, dłuższe niż próg z ustawień oraz transmisje,
które jeszcze trwają. Pominięcie MUST być zapisane z powodem; transmisja MUST zostać podjęta
ponownie, gdy się zakończy.

#### Scenario: Transmisja na żywo

- **WHEN** odkryty film jest trwającą transmisją
- **THEN** moduł MUST NOT prosić o transkrypcję, dopóki transmisja trwa

#### Scenario: Film ponad limit długości

- **WHEN** film jest dłuższy niż próg
- **THEN** MUST zostać zapisany jako pominięty z powodem i MUST NOT trafić do dostawcy

### Requirement: Film jest jeden, niezależnie od tego, skąd przyszedł

Tożsamością filmu MUST być jego identyfikator YouTube. Film znaleziony przez kanał, przez temat
i wskazany ręcznie MUST być jednym filmem w archiwum, a jego pochodzenie MUST być odnotowane.

#### Scenario: Film z obserwowanego kanału trafia też do tematu

- **WHEN** ten sam film zostaje odkryty przez kanał i przez temat
- **THEN** archiwum MUST mieć jeden film, a transkrypcja i odczyt MUST powstać raz
