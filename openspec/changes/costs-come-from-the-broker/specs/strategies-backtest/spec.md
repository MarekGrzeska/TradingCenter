## RENAMED Requirements

- FROM: `### Requirement: Profil kosztów instrumentu ustawia operator`
- TO: `### Requirement: Profil kosztów instrumentu pochodzi od brokera`

## MODIFIED Requirements

### Requirement: Model kosztów jest obowiązkowy

Każde uruchomienie MUST być liczone z modelem kosztów, w którym są: spread (jedna wartość albo profil 24 godzin UTC),
poślizg na stronę, stawki finansowania overnight dla longa i shorta (ułamek wartości pozycji za noc) i godzina
rozliczenia doby. Model MUST pochodzić z jednego z trzech źródeł, a uruchomienie MUST zapisywać, z którego:
1. modelu podanego w żądaniu;
2. profilu kosztów instrumentu, gdy żądanie modelu nie podaje;
3. jawnego wyboru „bez kosztów” (`without_costs`), który daje model z samych zer.

Żądanie z modelem kosztów i jednocześnie z „bez kosztów” MUST zostać odrzucone. Zera podane w modelu MUST być przyjęte
jako zwykły model kosztów. Finansowanie MUST być naliczane za każde przekroczenie godziny rozliczenia przy otwartej
pozycji, także w dni bez handlu.

#### Scenario: Brak modelu kosztów

- **WHEN** żądanie uruchomienia nie zawiera modelu kosztów ani wyboru „bez kosztów”
- **THEN** uruchomienie MUST być liczone z profilu kosztów instrumentu, a jego źródłem MUST być profil

#### Scenario: Uruchomienie bez kosztów

- **WHEN** żądanie wybiera „bez kosztów”
- **THEN** uruchomienie MUST być liczone z zerowym modelem i MUST zapisywać, że było bez kosztów

#### Scenario: Koszty i „bez kosztów” naraz

- **WHEN** żądanie podaje model kosztów i wybiera „bez kosztów”
- **THEN** uruchomienie MUST zostać odrzucone przed zakolejkowaniem

#### Scenario: Pozycja przez weekend

- **WHEN** long jest otwarty od piątku 20:00 do poniedziałku 10:00 UTC przy rozliczeniu o 22:00 UTC
- **THEN** finansowanie MUST zostać naliczone za trzy noce

### Requirement: Profil kosztów instrumentu pochodzi od brokera

Pakiet MUST przechowywać co najwyżej jeden profil kosztów na instrument, o tym samym kształcie i z tym samym sprawdzeniem
co model kosztów uruchomienia. Gdy uruchomienie potrzebuje profilu, a instrument go nie ma, pakiet MUST pobrać go sam od
brokera przez archiwum w tym procesie, bez kroku operatora i niezależnie od tego, kto prosi o uruchomienie. Wartości są
wtedy takie:
- spread to różnica bieżących ask i bid;
- poślizg to zero;
- stawki finansowania pochodzą z warunków instrumentu, przeliczone na ułamek wartości pozycji za noc, ze znakiem
  „dodatnie = opłata”;
- godzina rozliczenia to godzina UTC chwili naliczenia podanej przez brokera.

Profil MUST zapisywać swoje źródło (broker albo operator), chwilę ustalenia i surowe wartości brokera, z których
powstał. Operator MAY profil zmienić albo kazać pobrać go od brokera od nowa. Profil MUST NOT odświeżać się sam przy
kolejnych uruchomieniach. Gdy broker nie podaje którejś wartości albo nie odpowiada, pakiet MUST odmówić uruchomienia,
nazwać brakującą wartość i niczego nie zapisać. MUST NOT podstawiać wartości domyślnej.

Uruchomienie korzystające z profilu MUST zapisywać wartości kosztów, a nie odwołanie do profilu. Zmiana profilu MUST
NOT zmieniać żadnego wcześniej zapisanego uruchomienia.

#### Scenario: Pierwsze uruchomienie instrumentu bez profilu

- **WHEN** uruchomienie bez modelu kosztów dotyczy instrumentu, który nie ma profilu
- **THEN** pakiet MUST pobrać profil od brokera, zapisać go ze źródłem „broker” i policzyć z nim uruchomienie

#### Scenario: Broker nie podaje finansowania

- **WHEN** warunki instrumentu nie niosą stawki finansowania
- **THEN** uruchomienie MUST zostać odrzucone z nazwą brakującej wartości, a profil MUST NOT powstać

#### Scenario: Zmiana profilu po uruchomieniu

- **WHEN** operator zmienia spread w profilu instrumentu, który ma już zakończone uruchomienie
- **THEN** koszty zapisane w tamtym uruchomieniu MUST pozostać takie, jakie były

#### Scenario: Profil z niepełnym profilem spreadu

- **WHEN** operator zapisuje profil, którego godzinowy profil spreadu ma 23 wartości
- **THEN** zapis MUST zostać odrzucony z tym samym problemem, jaki dostałby model kosztów uruchomienia
