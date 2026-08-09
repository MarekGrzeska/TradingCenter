# market-data-jobs Specification

## Purpose
Opisuje zlecenie dociągania historii: jak decyzja operatora „zbieraj te instrumenty od tej daty"
zamienia się w pracę podzieloną na kawałki, skąd bierze się mierzony postęp, co zostaje po kawałku,
który zawiódł, i dlaczego ta historia przeżywa restart modułu.
## Requirements
### Requirement: Zlecenie jest jednostką decyzji, kawałek jednostką pracy

Operator podejmuje jedną decyzję — zbierz te instrumenty, w tych interwałach, od tej daty — i moduł
MUST zapisać ją jako jedno zlecenie. Zlecenie MUST zostać rozłożone na kawałki, gdzie kawałek to
jedna para (symbol, rozdzielczość) i jedno okno czasu, a okno MUST być takie, by mieściło się w
limicie świec na jedno żądanie do gatewaya. Kawałek jest najmniejszą rzeczą, która się udaje albo
nie udaje; zlecenie samo z siebie nie sięga do providera.

#### Scenario: Zlecenie na wiele par

- **WHEN** operator zleca zebranie dwóch instrumentów w trzech interwałach od zadanej daty
- **THEN** moduł zapisuje jedno zlecenie
- **AND** rozkłada je na kawałki pokrywające każdą z sześciu par od tej daty do chwili bieżącej

#### Scenario: Zakres głębszy niż jedno żądanie

- **WHEN** zakres pary wymaga więcej świec, niż wolno zamówić w jednym żądaniu do gatewaya
- **THEN** moduł dzieli go na kolejne kawałki, każdy w granicach tego limitu
- **AND** kawałki pokrywają cały zakres bez luki między nimi

#### Scenario: Para już pokryta

- **WHEN** archiwum ma już świece dla całego zakresu pary ze zlecenia
- **THEN** moduł MUST NOT tworzyć dla niej kawałków pytających providera o to, co już posiada
- **AND** zlecenie stwierdza, że dla tej pary nie było czego dociągać

### Requirement: Data OD jest przycinana do tego, co provider ma

Operator MUST móc podać dowolnie wczesną datę początku, łącznie z datą sprzed istnienia rynku.
Data wcześniejsza niż historia dostępna u providera MUST zostać przycięta do najstarszego
osiągalnego momentu i MUST NOT być odrzucona jako błąd — wpisanie odległej daty znaczy „wszystko,
co się da".

#### Scenario: Data sprzed historii providera

- **WHEN** operator podaje datę początku wcześniejszą niż najstarsza świeca, którą provider potrafi
  podać dla tej pary
- **THEN** moduł przycina zakres do tego najstarszego osiągalnego momentu
- **AND** zlecenie odnotowuje, że zakres został przycięty, wraz z datą faktycznie użytą

#### Scenario: Data w przyszłości

- **WHEN** operator podaje datę początku późniejszą niż chwila bieżąca
- **THEN** moduł odmawia utworzenia zlecenia i nazywa powód

### Requirement: Zlecenie da się wycenić przed jego uruchomieniem

Zlecenie kosztuje dziesiątki minut i setki żądań do providera, więc MUST dać się o nie zapytać, nic
nie uruchamiając. Wycena MUST podawać dla każdej pary przycięty zakres, szacowaną liczbę świec i
szacowany rozmiar w archiwum, oraz sumę dla całego zlecenia. Wycena MUST być liczona tą samą drogą
co późniejszy podział na kawałki, żeby to, co operator zatwierdza, było tym, co zostanie wykonane.

#### Scenario: Wycena przed decyzją

- **WHEN** konsument prosi o wycenę zlecenia dla wskazanych par i daty początku
- **THEN** dostaje dla każdej pary przycięty zakres, szacowaną liczbę świec i szacowany rozmiar
- **AND** sumę tych wartości dla całego zlecenia
- **AND** żadne zlecenie nie zostaje utworzone ani żadna para nie zaczyna być śledzona

#### Scenario: Szacunek jest opisany jako szacunek

- **WHEN** konsument odczytuje wycenę
- **THEN** liczby są opisane jako szacunkowe
- **AND** wycena stwierdza, że rynek zamknięty w części zakresu obniży faktyczną liczbę świec

### Requirement: Postęp zlecenia jest mierzony, nie zgadywany

Zlecenie MUST podawać swój postęp jako stosunek kawałków ukończonych do wszystkich, a nie jako
oszacowanie z upływu czasu. Zlecenie MUST NOT raportować postępu wyższego niż faktycznie ukończona
praca, nawet gdy pojedynczy kawałek trwa długo.

#### Scenario: Odczyt postępu w trakcie

- **WHEN** konsument odczytuje zlecenie, którego część kawałków się zakończyła
- **THEN** dostaje liczbę kawałków ukończonych, liczbę wszystkich oraz wynikający z nich udział
- **AND** liczbę świec zapisanych do tej pory

#### Scenario: Długi kawałek

- **WHEN** kawałek trwa, a żaden inny się w tym czasie nie kończy
- **THEN** postęp zlecenia nie rośnie
- **AND** zlecenie stwierdza, który kawałek jest w toku

### Requirement: Nieudany kawałek nie przerywa zlecenia

Kawałek, który zawiódł, MUST zostać odnotowany z nazwaną przyczyną, a pozostałe kawałki zlecenia
MUST być wykonane dalej. Zlecenie z choć jednym nieudanym kawałkiem MUST kończyć się stanem
częściowym — odróżnialnym zarówno od sukcesu, jak i od porażki całości — i MUST podawać, jaka część
zakresu została pokryta. Świece zapisane przez kawałki udane MUST pozostać w archiwum; moduł
MUST NOT wycofywać ich z powodu porażki innego kawałka.

#### Scenario: Kawałek w środku zakresu zawodzi

- **WHEN** jeden z kawałków zlecenia kończy się błędem, a inne czekają w kolejce
- **THEN** moduł odnotowuje przyczynę przy tym kawałku
- **AND** wykonuje pozostałe kawałki
- **AND** świece zapisane przez kawałki udane pozostają w archiwum

#### Scenario: Zlecenie kończy się częściowo

- **WHEN** zlecenie dobiega końca, mając kawałki udane i nieudane
- **THEN** jego stan stwierdza pokrycie częściowe, a nie sukces ani porażkę
- **AND** podaje, ile kawałków zawiodło i z jakich powodów

#### Scenario: Pokrycie z luką

- **WHEN** nieudany kawałek leżał między dwoma udanymi
- **THEN** pokrycie pary pokazuje osobne przedziały z luką między nimi, zamiast jednego ciągłego

### Requirement: Ponowienie obejmuje wyłącznie to, co zawiodło

Operator MUST móc ponowić zlecenie zakończone częściowo lub porażką. Ponowienie MUST wykonać
wyłącznie kawałki nieudane i MUST NOT pytać providera ponownie o zakresy już pokryte. Ponowienie
MUST być widoczne jako kolejna próba tego samego zlecenia, a nie jako nowe zlecenie, żeby historia
nie rozpadała się na wpisy bez związku.

#### Scenario: Ponowienie po porażce części

- **WHEN** operator ponawia zlecenie, w którym dwa kawałki z dziesięciu zawiodły
- **THEN** moduł wykonuje te dwa kawałki
- **AND** nie wysyła żądań o zakresy pokryte przez pozostałe osiem

#### Scenario: Ponowienie się udaje

- **WHEN** ponowione kawałki kończą się powodzeniem
- **THEN** zlecenie przechodzi w stan zakończonego powodzeniem
- **AND** historia zachowuje ślad wcześniejszej porażki

#### Scenario: Ponowienie zlecenia bez porażek

- **WHEN** operator ponawia zlecenie, w którym nic nie zawiodło
- **THEN** moduł nie wysyła żadnego żądania do providera i stwierdza, że nie ma czego ponawiać

### Requirement: Historia zleceń przeżywa restart

Zlecenia i ich kawałki MUST być trwałe. Po restarcie modułu operator MUST widzieć zlecenia sprzed
restartu wraz z ich wynikiem, a zlecenie przerwane restartem MUST NOT wyglądać na wiecznie trwające.

#### Scenario: Odczyt po restarcie

- **WHEN** moduł zostaje zatrzymany i uruchomiony ponownie
- **THEN** zlecenia sprzed zatrzymania są nadal odczytywalne wraz z liczbą świec i pokrytym zakresem

#### Scenario: Zlecenie przerwane zatrzymaniem

- **WHEN** moduł zostaje zatrzymany w trakcie zlecenia
- **THEN** po starcie zlecenie ma stan przerwanego, a nie trwającego
- **AND** MUST dać się je ponowić, obejmując kawałki, które nie zdążyły się wykonać

### Requirement: Zlecenia dzielą budżet ruchu z resztą modułu

Kawałki są żądaniami do gatewaya, a ten przepuszcza ograniczoną liczbę żądań na sekundę dla całego
konta. Moduł MUST wykonywać kawałki pod tym samym ograniczeniem równoległości co dotychczasowe
uzupełnianie i MUST NOT dopuścić, by zlecenie zagłodziło odczyt wywołany przez operatora ani nasłuch
na żywo śledzonych par.

#### Scenario: Kilka zleceń naraz

- **WHEN** istnieje więcej zleceń oczekujących, niż wynosi skonfigurowana równoległość
- **THEN** ich kawałki wykonują się kolejno, zamiast wszystkie naraz

#### Scenario: Odczyt w trakcie zlecenia

- **WHEN** operator czyta świece albo ogląda wykres w trakcie trwającego zlecenia
- **THEN** odczyt jest obsłużony z archiwum i nie czeka na zakończenie zlecenia

### Requirement: Kawałek jest ograniczony swoim oknem, nie tylko liczbą świec

Kawałek ma dwie krawędzie i obie MUST być wiążące. Sama liczba świec, na jaką kawałek został
wyliczony, starszej krawędzi nie pilnuje: liczba liczy świece, a okno liczy kalendarz, i dla
instrumentu zamkniętego przez część tygodnia te dwie rzeczy rozjeżdżają się o połowę — kawałek
policzony na okno od stycznia do sierpnia dostaje tyle świec, ile jest w oknie sięgającym jesieni
poprzedniego roku. Moduł MUST nazwać starszą krawędź kawałka jako moment w żądaniu do gatewaya
(`capital-market-data` spec, „Historia jest stronicowana poza limit providera") i MUST NOT zapisać
ani jednej świecy starszej niż okno tego kawałka, niezależnie od tego, co przyszło w odpowiedzi.

#### Scenario: Odpowiedź sięga poniżej okna kawałka

- **WHEN** gateway odda dla kawałka świece starsze niż początek jego okna
- **THEN** moduł zapisuje wyłącznie te mieszczące się w oknie kawałka
- **AND** pokrycie odnotowane dla kawałka obejmuje jego okno, a nie okres, który świece przypadkiem
  zajęły

#### Scenario: Interwał, w którym rynek stoi przez część tygodnia

- **WHEN** operator zleca zebranie instrumentu notowanego w części doby i części tygodnia, od
  wskazanej daty
- **THEN** archiwum MUST NOT skończyć ze świecami starszymi niż ta data
- **AND** liczba faktycznie zapisanych świec MAY być mniejsza od wyceny, bo wycena liczy okresy
  kalendarza, a rynek ich wszystkich nie wypełnia

### Requirement: Kawałki pomija się w hurcie tylko na granicy providera

Kawałek, który natrafił na koniec historii providera, pozwala pominąć wszystkie kawałki stojące za
nim w kolejce — z konstrukcji starsze, z konstrukcji poza tą granicą — zamiast wydawać po żądaniu
na ponowne odkrycie tej samej krawędzi. To pominięcie jest nieodwracalne w ramach zlecenia: kawałek
pominięty nie zostanie ponowiony, bo nic nie zawiodło.

Dlatego moduł MUST pomijać w hurcie wyłącznie wtedy, gdy koniec historii stwierdził provider. Odczyt
zatrzymany na granicy, którą sam kawałek podał gatewayowi jako swoją starszą krawędź, MUST NOT
uruchomić pominięcia — o danych poniżej tej granicy taki odczyt nie dowiedział się niczego, a stoją
za nią właśnie te kawałki, które miałyby zostać pominięte.

#### Scenario: Kawałek zatrzymany na własnej krawędzi

- **WHEN** kawałek zbierze świece aż do początku swojego okna i tam się zatrzyma
- **THEN** kawałki starsze od niego w tym samym zleceniu zostają do wykonania
- **AND** zlecenie kończy się z pokryciem sięgającym daty, którą podał operator

#### Scenario: Provider kończy się w środku zakresu zlecenia

- **WHEN** kawałek dostanie od gatewaya stwierdzenie, że historia instrumentu się skończyła
- **THEN** moduł odnotowuje tę granicę i pomija kawałki tego zlecenia sięgające poniżej niej
- **AND** zlecenie kończy się jako ukończone, a nie nieudane

### Requirement: Mechanizm wykonujący kawałki przeżywa własną awarię

Awaria w mechanizmie wykonującym kawałki MUST kosztować jedno podejście, a nie cały mechanizm.
Moduł MUST wykonywać kolejne kawałki po niepowodzeniu w dowolnym miejscu swojej pętli roboczej —
także poza samym sięgnięciem do providera, w przejmowaniu pracy do wykonania i w czekaniu na nią.
Przyczyna MUST zostać odnotowana w logu, a kolejne podejście MUST być poprzedzone odczekaniem, żeby
awaria trwała nie zamieniła się w pętlę bez przerwy.

Odróżnienie jest tu całą rzeczą: kawałek, który zawiódł, to jeden zapis w historii zlecenia i
pozycja do ponowienia, natomiast mechanizm, który się zatrzymał, to koniec pobierania czegokolwiek
przez cały moduł — bez żadnego wpisu w żadnym zleceniu, bo nie ma już czego zapisać. Tylko
zatrzymanie modułu MUST kończyć pętlę roboczą.

#### Scenario: Awaria przy przejmowaniu pracy

- **WHEN** próba przejęcia kolejnego kawałka do wykonania kończy się błędem
- **THEN** moduł odnotowuje przyczynę i po odczekaniu próbuje ponownie
- **AND** kawałki oczekujące zostają wykonane, gdy przyczyna ustąpi
- **AND** przywrócenie pobierania MUST NOT wymagać restartu modułu

#### Scenario: Awaria trwała

- **WHEN** przejęcie pracy zawodzi raz za razem
- **THEN** moduł nie próbuje bez przerwy, tylko z przerwą między podejściami

#### Scenario: Mechanizm jednak się zatrzymuje

- **WHEN** pętla robocza kończy się z powodu innego niż zatrzymanie modułu
- **THEN** fakt ten zostaje odnotowany w logu wraz z przyczyną
- **AND** MUST NOT być milczący, bo z zewnątrz wygląda identycznie jak brak pracy do wykonania

### Requirement: Zlecenie podaje moment swojej ostatniej aktywności

Zlecenie MUST podawać moment, w którym ostatnio cokolwiek się w nim wydarzyło — kawałek ruszył albo
się rozstrzygnął. Moment ten MUST być podawany również przy zleceniu zawężonym do jednej pary,
liczony z kawałków tej pary. Zlecenie, w którym żaden kawałek jeszcze nie ruszył, MUST podawać
moment swojego utworzenia, żeby odpowiedź na pytanie „od kiedy nic" istniała zawsze.

Sam postęp na to pytanie nie odpowiada. Kawałek pracujący od czterdziestu minut i kawałek stojący
od czterdziestu minut dają ten sam udział ukończonej pracy i tę samą liczbę świec — różni je
wyłącznie to, kiedy ostatni raz coś się ruszyło.

#### Scenario: Odczyt zlecenia w toku

- **WHEN** konsument odczytuje zlecenie, którego kawałki są w trakcie wykonywania
- **THEN** dostaje moment ostatniej aktywności obok postępu i liczby świec

#### Scenario: Zlecenie stoi

- **WHEN** żaden kawałek nie ruszył ani nie rozstrzygnął się od dłuższej chwili
- **THEN** moment ostatniej aktywności pozostaje ten sam przy kolejnych odczytach
- **AND** MUST NOT przesuwać się z upływem czasu, bo zlecenie jest nadal odczytywane

#### Scenario: Zlecenie dopiero utworzone

- **WHEN** zlecenie zostało utworzone, a żaden jego kawałek jeszcze nie ruszył
- **THEN** moment ostatniej aktywności jest momentem utworzenia zlecenia

#### Scenario: Odczyt zawężony do pary

- **WHEN** konsument odczytuje zlecenie zawężone do jednej pary
- **THEN** dostaje moment ostatniej aktywności wyliczony z kawałków tej pary
- **AND** aktywność innej pary tego samego zlecenia MUST NOT go przesuwać
