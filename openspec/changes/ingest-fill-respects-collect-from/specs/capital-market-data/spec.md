## MODIFIED Requirements

### Requirement: Historia jest stronicowana poza limit providera

Provider zwraca najwyżej 1000 świec na żądanie i odrzuca okno czasowe szersze niż żądana liczba.
Moduł MUST stronicować wstecz, żeby zaspokoić większe żądanie, a każde kolejne okno MUST być
kotwiczone na najstarszej już pobranej świecy, a nie na zegarze — rynek, który był zamknięty,
zwraca mniej świec, niż wynika z kalendarza.

Konsument MUST móc ograniczyć odczyt nie tylko liczbą świec, ale i momentem, poniżej którego nie
chce zejść. Liczba tego nie wyraża i wyrazić nie może: liczba liczy świece, a instrument zamknięty
przez pół tygodnia oddaje żądaną liczbę świec z okresu znacznie dłuższego niż tyle samo okresów
kalendarza — „nic starszego niż 1 stycznia" nie jest zdaniem, które da się powiedzieć licznikiem.
Gdy konsument poda taki moment, moduł MUST przyciąć do niego okna żądań, żeby nie wydawać żądania
na świece z góry przeznaczone do odrzucenia, MUST zatrzymać stronicowanie po jego osiągnięciu
i MUST NOT zwrócić ani jednej świecy starszej niż on.

Stwierdzenie „historia się skończyła" mówi o providerze, nie o konsumencie. MUST paść wyłącznie
wtedy, gdy provider nie ma nic starszego, i MUST NOT paść dlatego, że odczyt zatrzymał się na
granicy, którą konsument sam podał — o tym, co provider trzyma poniżej tej granicy, taki odczyt
nie dowiedział się niczego. Rozróżnienie jest kosztowne w jedną stronę: konsument zapisuje to
stwierdzenie jako trwałą granicę instrumentu i pomija na jego podstawie pracę, do której nigdy
potem nie wróci.

#### Scenario: Prośba o więcej świec, niż mieści jedno żądanie

- **WHEN** konsument prosi o więcej świec, niż provider podaje w jednym żądaniu
- **THEN** moduł wysyła tyle żądań, ile trzeba, i zwraca jedną serię, uporządkowaną od najstarszej
  i wolną od powtórzonych znaczników czasu

#### Scenario: Historia instrumentu się kończy

- **WHEN** stronicowanie dochodzi do miejsca, w którym provider nie ma starszych danych
- **THEN** moduł zatrzymuje się i zwraca to, co zebrał, co nie jest błędem
- **AND** odpowiedź stwierdza, że seria jest krótsza od żądanej, bo historia się skończyła

#### Scenario: Okno nie przynosi nic nowego

- **WHEN** kolejne okno nie daje świecy starszej niż najstarsza już posiadana
- **THEN** stronicowanie kończy się, zamiast powtarzać to samo okno

#### Scenario: Odczyt ograniczony momentem, nie liczbą

- **WHEN** konsument prosi o świece do chwili bieżącej, podając moment, poniżej którego nie chce
  zejść, i liczbę świec większą, niż ten okres faktycznie mieści
- **THEN** moduł stronicuje wstecz tylko do tego momentu, a nie do wyczerpania żądanej liczby
- **AND** odpowiedź MUST NOT zawierać świecy starszej niż podany moment, także wtedy, gdy provider
  dołożył ją wewnątrz strony sięgającej poniżej granicy

#### Scenario: Okno przycięte do granicy konsumenta nic nie przynosi

- **WHEN** ostatnie okno odczytu zostało przycięte do granicy podanej przez konsumenta i provider
  odpowiada na nie brakiem danych albo wyłącznie świecami, które moduł już ma
- **THEN** odczyt kończy się jako osiągnięcie granicy konsumenta
- **AND** odpowiedź MUST NOT stwierdzać, że historia instrumentu się skończyła

#### Scenario: Historia providera kończy się powyżej granicy konsumenta

- **WHEN** provider nie ma nic starszego, a stronicowanie zatrzymało się na oknie, którego starsza
  krawędź wynikała z kalendarza, nie z granicy konsumenta
- **THEN** odpowiedź stwierdza, że historia instrumentu się skończyła — granica konsumenta MUST NOT
  ukryć końca historii, tak samo jak MUST NOT go zmyślić
