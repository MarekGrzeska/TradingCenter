## MODIFIED Requirements

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
w jednej kolumnie, od kiedy instrument jest archiwizowany oraz stan zbierania. Interwał, dla którego
zbieranie nie nadąża albo ustało, MUST być wyróżniony wewnątrz tej kolumny, żeby cicha awaria
jednego interwału nie ginęła w wierszu wyglądającym poprawnie.

#### Scenario: Przegląd listy

- **WHEN** operator patrzy na listę archiwizowanych instrumentów
- **THEN** każdy instrument zajmuje jeden wiersz
- **AND** wiersz podaje wszystkie jego interwały skrótowo w jednej kolumnie, moment rozpoczęcia
  archiwizowania oraz stan zbierania

#### Scenario: Instrument w wielu interwałach

- **WHEN** ten sam instrument jest archiwizowany w czterech interwałach
- **THEN** zajmuje jeden wiersz, a nie cztery
- **AND** wszystkie cztery interwały są w nim wypisane

#### Scenario: Zbieranie ustało

- **WHEN** archiwum zgłasza, że dla jednego z interwałów instrumentu zbieranie nie nadąża albo ustało
- **THEN** panel wyróżnia ten interwał wewnątrz wiersza
- **AND** wiersz MUST NOT wyglądać tak samo jak wiersz, w którym wszystko działa

#### Scenario: Świeżość danych

- **WHEN** operator chce wiedzieć, jak świeże są dane
- **THEN** dla każdego interwału dostępny jest czas najnowszej zebranej świecy

### Requirement: Panel pokazuje zasięg archiwum

Operator MUST widzieć, jaki przedział czasu archiwum pokrywa dla instrumentu, osobno dla każdego
jego interwału, żeby wiedzieć, na czym może oprzeć wykres albo backtest.

#### Scenario: Podgląd pokrycia pary

- **WHEN** operator wybiera instrument z listy
- **THEN** widzi dla każdego jego archiwizowanego interwału najstarszy i najnowszy pokryty znacznik
  czasu
- **AND** informację, czy najstarsza granica wynika z końca historii u providera

#### Scenario: Pokrycie z lukami

- **WHEN** pokrycie interwału składa się z więcej niż jednego przedziału
- **THEN** panel stwierdza, że między nimi są luki, zamiast pokazywać jeden ciągły zakres

### Requirement: Zdjęcie pary jest jawną decyzją

Panel MUST pozwalać przestać archiwizować pojedynczy interwał instrumentu oraz instrument w całości.
Obie decyzje MUST wymagać potwierdzenia, a przy nim panel MUST wymienić, co przestanie być zbierane,
i stwierdzić, że zebrane świece pozostają w archiwum.

#### Scenario: Operator zdejmuje parę

- **WHEN** operator wybiera zaprzestanie archiwizowania jednego interwału instrumentu
- **THEN** panel prosi o potwierdzenie i stwierdza, że dane pozostaną zachowane
- **AND** po potwierdzeniu ten interwał znika z wiersza, a pozostałe zostają

#### Scenario: Operator zdejmuje cały instrument

- **WHEN** operator wybiera zaprzestanie archiwizowania instrumentu w całości
- **THEN** panel wymienia wszystkie interwały, które przestaną być zbierane, i prosi o potwierdzenie
- **AND** po potwierdzeniu instrument znika z listy, a zebrane świece pozostają w archiwum

## ADDED Requirements

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

## REMOVED Requirements

### Requirement: Operator dokłada parę wybierając instrument i rozdzielczość

**Reason**: Dodawanie po jednej parze naraz, bez zakresu i bez wyceny, jest zastąpione kreatorem i
dialogiem akceptacji — dokładanie instrumentu w czterech interwałach przestaje być czterema
decyzjami podejmowanymi w ciemno.

**Migration**: Zachowanie opisują nowe wymagania „Instrumenty dokłada się kreatorem" oraz
„Zatwierdzenie kreatora otwiera dialog akceptacji" w tej samej zdolności.
