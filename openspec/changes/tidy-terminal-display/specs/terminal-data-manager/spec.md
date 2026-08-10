## MODIFIED Requirements

### Requirement: Panel pokazuje, czy zbieranie działa

Sama obecność instrumentu na liście nie dowodzi, że dane przychodzą. Panel MUST pokazywać jeden
wiersz na instrument, a w nim wszystkie archiwizowane interwały tego instrumentu wypisane skrótowo
w jednej kolumnie oraz stan zbierania. Interwał, dla którego zbieranie nie nadąża albo ustało,
MUST być wyróżniony wewnątrz tej kolumny, żeby cicha awaria jednego interwału nie ginęła w wierszu
wyglądającym poprawnie.

Wiersz MUST NOT nieść jednej daty początku danych dla całego instrumentu. Ta data należy do
interwału, a nie do instrumentu — interwały tego samego instrumentu sięgają różnie daleko wstecz —
i jest podana przy interwale, po rozwinięciu wiersza.

#### Scenario: Przegląd listy

- **WHEN** operator patrzy na listę archiwizowanych instrumentów
- **THEN** każdy instrument zajmuje jeden wiersz
- **AND** wiersz podaje wszystkie jego interwały skrótowo w jednej kolumnie oraz stan zbierania

#### Scenario: Instrument w wielu interwałach

- **WHEN** ten sam instrument jest archiwizowany w czterech interwałach
- **THEN** zajmuje jeden wiersz, a nie cztery
- **AND** wszystkie cztery interwały są w nim wypisane

#### Scenario: Zbieranie ustało

- **WHEN** archiwum zgłasza, że dla jednego z interwałów instrumentu zbieranie nie nadąża albo ustało
- **THEN** panel wyróżnia ten interwał wewnątrz wiersza
- **AND** wiersz MUST NOT wyglądać tak samo jak wiersz, w którym wszystko działa

### Requirement: Panel pokazuje zasięg archiwum

Operator MUST być ostrzeżony, gdy pokrycie interwału składa się z więcej niż jednego przedziału —
świece między nimi nie zostały zebrane, mimo że reszta wygląda na ciągłą historię. Rozwinięcie
MUST NOT pokazywać nic o pokryciu, gdy interwał jest pokryty jednym ciągłym przedziałem: moment
początku danych już jest podany przy interwale (patrz „Rozwinięcie instrumentu podaje objętość
zebranych danych" niżej), a wypisanie „ciągłe od X do Y" nie mówi operatorowi niczego więcej niż
milczenie.

#### Scenario: Pokrycie ciągłe

- **WHEN** pokrycie interwału to jeden ciągły przedział
- **THEN** rozwinięcie nie pokazuje żadnej wzmianki o pokryciu

#### Scenario: Pokrycie z lukami

- **WHEN** pokrycie interwału składa się z więcej niż jednego przedziału
- **THEN** panel stwierdza, że między nimi są luki, zamiast milczeć albo pokazywać jeden ciągły
  zakres

## ADDED Requirements

### Requirement: Rozwinięcie instrumentu podaje objętość zebranych danych

Rozwinięcie wiersza MUST odpowiadać na pytanie, ile danych archiwum trzyma dla tego instrumentu:
dla każdego archiwizowanego interwału MUST podać liczbę zebranych świec, szacowaną objętość, jaką
zajmują, oraz moment, od którego dane tego interwału sięgają. Interwał, który nie zebrał jeszcze
nic, MUST być nazwany jako taki, a nie zostawiony z pustym miejscem ani z zerem udającym pomiar.

Rozwinięcie MUST NOT powtarzać tego, co mówi zakładka Data History — przebiegu dociągania, stanu
pojedynczego zlecenia ani historii skasowań. Panel odpowiada na pytanie „ile tego jest", a nie
„skąd się to wzięło".

Objętość MUST być pokazana jako szacunek podany przez archiwum, a panel MUST NOT wyliczać jej
własnym mnożnikiem — dwie różne liczby dla tych samych danych, jedna w kreatorze i jedna tutaj,
byłyby gorsze niż jedna niedokładna.

#### Scenario: Rozwinięcie instrumentu

- **WHEN** operator rozwija wiersz instrumentu
- **THEN** dla każdego archiwizowanego interwału widzi liczbę zebranych świec, szacowaną objętość
  danych i moment, od którego dane sięgają

#### Scenario: Interwał bez zebranych danych

- **WHEN** dla któregoś interwału instrumentu nie zebrano jeszcze żadnej świecy
- **THEN** rozwinięcie stwierdza to wprost dla tego interwału

#### Scenario: Interwały sięgają różnie daleko

- **WHEN** dane dla interwałów instrumentu zaczynają się w różnych momentach
- **THEN** każdy interwał niesie własny moment początku, przy sobie

#### Scenario: Objętości nie da się odczytać

- **WHEN** archiwum nie odpowiada na pytanie o śledzone pary
- **THEN** panel mówi, że objętość jest nieznana, i MUST NOT pokazywać zera jako odpowiedzi
