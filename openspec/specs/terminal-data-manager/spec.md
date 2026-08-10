## Purpose

Miejsce w terminalu, z którego operator decyduje, co archiwum zbiera — dokłada i zdejmuje pary
symbolu z rozdzielczością — oraz widzi, czy to zbieranie faktycznie działa i jak daleko sięga.
## Requirements
### Requirement: Panel jest zakładką terminala

Zarządzanie archiwizowanymi instrumentami MUST być dostępne jako zakładka terminala o nazwie
`Instruments`, adresowalna własną ścieżką i wpisana do rejestru zakładek na tych samych zasadach co
pozostałe. MUST to być jedyna zakładka mówiąca o instrumentach — terminal MUST NOT mieć osobnej
zakładki przeglądającej katalog providera obok tej listy.

#### Scenario: Operator otwiera panel

- **WHEN** operator wchodzi na ścieżkę panelu
- **THEN** widzi listę instrumentów aktualnie archiwizowanych

#### Scenario: Odświeżenie strony

- **WHEN** operator odświeża stronę na ścieżce panelu
- **THEN** wraca do panelu, a nie do widoku domyślnego

#### Scenario: Zakładki mówiące o instrumentach

- **WHEN** operator przegląda pasek nawigacji
- **THEN** widzi jedną zakładkę `Instruments`
- **AND** nie ma osobnej zakładki z katalogiem providera ani osobnej zakładki archiwum

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

### Requirement: Zdjęcie pary jest jawną decyzją

Panel MUST pozwalać skasować pojedynczy interwał instrumentu oraz instrument w całości. Skasowanie
zatrzymuje zbieranie **i** usuwa zebrane dane — panel MUST nazywać tę operację kasowaniem, a nie
zatrzymaniem, bo nazwa jest jedyną rzeczą, którą operator czyta przed kliknięciem.

Obie decyzje MUST wymagać potwierdzenia. Potwierdzenie MUST wymienić, co przestanie być zbierane,
MUST stwierdzić, że zebrane dane zostaną usunięte, i MUST stwierdzić, że jest to nieodwracalne.
Panel MUST NOT zapewniać, że zebrane świece pozostają w archiwum. Panel SHOULD podać przy
potwierdzeniu, od kiedy dane dla tej pary są zebrane, żeby operator widział, ile ich traci.

#### Scenario: Operator zdejmuje parę

- **WHEN** operator wybiera skasowanie jednego interwału instrumentu
- **THEN** panel prosi o potwierdzenie, stwierdzając, że dane tego interwału zostaną usunięte
  nieodwracalnie
- **AND** po potwierdzeniu ten interwał znika z wiersza, a pozostałe zostają

#### Scenario: Operator zdejmuje cały instrument

- **WHEN** operator wybiera skasowanie instrumentu w całości
- **THEN** panel wymienia wszystkie interwały, których dane zostaną usunięte, i prosi o potwierdzenie
- **AND** po potwierdzeniu instrument znika z listy

#### Scenario: Operator wycofuje się z potwierdzenia

- **WHEN** operator odrzuca potwierdzenie
- **THEN** nic nie zostaje skasowane
- **AND** instrument nadal jest archiwizowany

#### Scenario: Kasowanie zawodzi

- **WHEN** archiwum nie wykonuje skasowania
- **THEN** panel mówi, że skasowanie się nie udało, i zostawia możliwość spróbowania raz jeszcze
- **AND** MUST NOT usuwać wiersza z listy, jakby operacja się powiodła

### Requirement: Panel mówi, gdy archiwum nie odpowiada

Panel MUST odróżnić „nie ma żadnych archiwizowanych par" od „nie udało się o nie zapytać".

#### Scenario: Archiwum nieosiągalne

- **WHEN** panel nie może pobrać listy par
- **THEN** pokazuje, że archiwum jest nieosiągalne, zamiast pustej listy

### Requirement: Instrumenty dokłada się kreatorem

Panel MUST prowadzić dodawanie krokami, a nie jednym formularzem: klasa aktywów, następnie instrument
w tej klasie, następnie wybór wielu interwałów naraz, następnie data, od której historia ma zostać
dociągnięta. Klasa i instrument MUST być wybierane z podpowiedzi, a nie wpisywane z pamięci. Interwał
MUST dać się wybrać wielokrotnie w jednym przejściu przez kreator, żeby dołożenie instrumentu w
czterech interwałach było jedną decyzją.

#### Scenario: Przejście przez kreator

- **WHEN** operator wybiera klasę aktywów, potem instrument, potem trzy interwały i datę początku
- **THEN** kreator zbiera to jako jedną decyzję dotyczącą trzech par

#### Scenario: Instrumenty zależą od klasy

- **WHEN** operator wybiera klasę aktywów
- **THEN** podpowiedzi instrumentów obejmują wyłącznie instrumenty tej klasy

#### Scenario: Zmiana klasy po wybraniu instrumentu

- **WHEN** operator zmienia klasę aktywów po wybraniu instrumentu
- **THEN** wybrany instrument zostaje wyczyszczony, zamiast zostać przy nowej klasie

#### Scenario: Podana data jest wcześniejsza niż historia providera

- **WHEN** operator podaje datę początku odleglejszą niż cokolwiek, co provider ma dla tych par
- **THEN** kreator traktuje to jako prośbę o wszystkie dostępne dane
- **AND** MUST NOT odrzucać jej jako błędnej

#### Scenario: Kreator bez kompletu wyborów

- **WHEN** operator nie wybrał instrumentu albo ani jednego interwału
- **THEN** kreatora nie da się zatwierdzić
- **AND** panel mówi, czego brakuje

### Requirement: Zatwierdzenie kreatora otwiera dialog akceptacji

Zatwierdzenie kreatora MUST NOT dodawać niczego od razu. Panel MUST najpierw pokazać dialog, w którym
dla każdej pary instrument–interwał widać zakres faktycznie do pobrania, szacowaną liczbę rekordów i
szacowany rozmiar danych, wraz z sumą dla całości. Dopiero akceptacja tego dialogu MUST rozpocząć
archiwizowanie i dociąganie.

#### Scenario: Dialog przed dodaniem

- **WHEN** operator zatwierdza kreator
- **THEN** panel pokazuje dialog z wierszem dla każdej pary instrument–interwał
- **AND** w każdym wierszu zakres do pobrania, szacowaną liczbę rekordów i szacowany rozmiar
- **AND** sumę rekordów i rozmiaru dla całości

#### Scenario: Zakres przycięty do historii providera

- **WHEN** podana data początku jest wcześniejsza niż historia providera dla którejś pary
- **THEN** dialog pokazuje dla niej zakres przycięty, a nie datę wpisaną przez operatora
- **AND** stwierdza, że zakres został przycięty

#### Scenario: Operator odrzuca dialog

- **WHEN** operator zamyka dialog bez akceptacji
- **THEN** nic nie zaczyna być archiwizowane ani dociągane
- **AND** wybory z kreatora pozostają, żeby dało się je poprawić

#### Scenario: Operator akceptuje

- **WHEN** operator akceptuje dialog
- **THEN** wskazane pary zaczynają być archiwizowane
- **AND** rusza dociąganie historii dla podanego zakresu
- **AND** panel wskazuje, gdzie śledzić postęp tego dociągania

#### Scenario: Wyceny nie da się pobrać

- **WHEN** archiwum nie odpowiada na prośbę o wycenę
- **THEN** dialog mówi, że nie da się oszacować kosztu, i nie proponuje akceptacji na ślepo
- **AND** nic nie zostaje dodane

#### Scenario: Para już archiwizowana

- **WHEN** wśród par z kreatora jest para już archiwizowana
- **THEN** dialog oznacza ją jako już zbieraną
- **AND** akceptacja nie tworzy duplikatu

#### Scenario: Archiwum odmawia dodania

- **WHEN** archiwum odmawia dodania którejś pary, na przykład z powodu osiągniętego limitu
- **THEN** panel pokazuje powód odmowy operatorowi
- **AND** pary, których odmowa nie dotyczy, zostają dodane

### Requirement: Skasowanie odsyła do historii

Skasowanie cofa zasięg danych instrumentu i jest jedynym zdarzeniem, które to robi. Po skasowaniu
panel MUST wskazać zakładkę historii jako miejsce, gdzie ten fakt został odnotowany — tak samo jak
dodanie instrumentu wskazuje ją jako miejsce śledzenia dociągania.

#### Scenario: Po skasowaniu

- **WHEN** skasowanie kończy się powodzeniem
- **THEN** panel stwierdza, ile świec zostało usuniętych
- **AND** wskazuje zakładkę historii jako miejsce, gdzie skasowanie jest odnotowane

