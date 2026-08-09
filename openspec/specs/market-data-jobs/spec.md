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

