# terminal-polymarket Specification

## Purpose
Zakładka terminala, w której operator ogląda rynki predykcyjne sam, zamiast pytać o nie model:
co jest obserwowane i po ile, jak to się ruszyło w oknie, jak wygląda cała seria wraz z granicą
tego, co udało się zebrać, i gdzie stoi jedyne w terminalu kasowanie zebranej historii.
## Requirements
### Requirement: Rynki predykcyjne są zakładką terminala

Podgląd rynków predykcyjnych MUST być dostępny jako zakładka terminala, adresowalna własną
ścieżką i wpisana do rejestru zakładek. Zakładka MUST pokazywać coś od pierwszego wejścia —
także wtedy, gdy nic nie jest jeszcze obserwowane, kiedy MUST powiedzieć, że lista jest pusta,
i MUST wskazać, czym się ją zapełnia.

#### Scenario: Wejście na zakładkę

- **WHEN** operator otwiera zakładkę rynków predykcyjnych
- **THEN** widzi listę obserwowanych wydarzeń pod adresem tej zakładki

#### Scenario: Nic nie jest obserwowane

- **WHEN** operator otwiera zakładkę, a moduł nie obserwuje żadnego wydarzenia
- **THEN** zakładka MUST nazwać pustą listę jako pustą, a nie jako brak odpowiedzi
- **AND** MUST wskazać objęcie obserwacją jako czynność, która ją zapełnia

### Requirement: Lista pokazuje wydarzenie, nie pojedynczą monetę

Widok MUST przedstawiać obserwowane wydarzenie wraz z jego rynkami i wynikami każdego rynku.
Rynek o dwóch wynikach MUST być pokazany jako szczególny przypadek rynku wielowynikowego, a nie
odwrotnie: widok MUST NOT sprowadzać rynku do jednej ceny „za", ani pomijać rynków ani wyników,
których nie da się tak sprowadzić.

Każdy wynik MUST nieść swoje prawdopodobieństwo w skali 0..1 wraz z nazwaniem tej skali. Widok
MUST NOT przedstawiać go jako procentu bez powiedzenia tego wprost, bo odczytanie 0,62 jako 62
myli się o dwa rzędy wielkości i nie daje po drodze żadnego błędu.

**Rynek rozstrzygnięty MAY być domyślnie zwinięty**, a widok MUST wtedy podać ich liczbę i MUST
dać sposób ich pokazania. Zwinięcie MUST NOT być usunięciem: historia rynku, który się
rozstrzygnął, jest tym, czego dostawca już nie odda, więc jest najcenniejszym, a nie
najmniej ważnym, co archiwum trzyma.

Dla rynku rozstrzygniętego widok MUST NOT pokazywać wartości zmiany w oknach. Po rozstrzygnięciu
cena stoi, więc każde okno wyszłoby zerem albo brakiem pokrycia — pierwsze twierdzi, że rynek się
nie ruszył, drugie że archiwum ma dziurę, a prawdą jest, że nie ma czego mierzyć. Widok MUST
zamiast tego podać, czym rynek się rozstrzygnął.

#### Scenario: Wydarzenie o wielu rynkach

- **WHEN** obserwowane wydarzenie ma więcej niż jeden nierozstrzygnięty rynek
- **THEN** widok pokazuje każdy z nich wraz z jego wynikami

#### Scenario: Rynek o wielu wynikach

- **WHEN** rynek ma więcej niż dwa wyniki
- **THEN** widok pokazuje każdy wynik z jego własnym prawdopodobieństwem
- **AND** MUST NOT pokazywać wyłącznie najwyższego z nich

#### Scenario: Wydarzenie z rynkami rozstrzygniętymi

- **WHEN** część rynków wydarzenia jest rozstrzygnięta
- **THEN** widok domyślnie pokazuje tylko nierozstrzygnięte
- **AND** podaje liczbę rozstrzygniętych oraz sposób ich pokazania

#### Scenario: Rozstrzygnięty rynek pokazany świadomie

- **WHEN** operator każe pokazać rozstrzygnięte rynki
- **THEN** widok podaje dla każdego, czym się rozstrzygnął
- **AND** MUST NOT pokazać przy nim zmiany w żadnym oknie

#### Scenario: Wszystkie rynki wydarzenia rozstrzygnięte

- **WHEN** każdy rynek obserwowanego wydarzenia jest rozstrzygnięty
- **THEN** widok mówi to wprost
- **AND** MUST NOT wyglądać na wydarzenie bez rynków

### Requirement: Ceny całej listy biorą się z jednego żądania

Odświeżenie prawdopodobieństw dla całej listy obserwowanych MUST być jednym żądaniem do modułu,
nigdy żądaniem na wynik ani na rynek. Wymaganie to nie jest optymalizacją: wyniki pobrane
osobno pochodzą z różnych chwil, a lista, w której dwa wyniki tego samego rynku zostały wycenione
w innych momentach, pokazuje sumę prawdopodobieństw, jakiej nigdy nie było.

Każda pokazana cena MUST nieść moment, którego dotyczy. Widok MUST odróżniać cenę świeżą od
takiej, która się zestarzała, i MUST NOT pokazywać starej ceny tak samo jak bieżącej.

#### Scenario: Odświeżenie listy

- **WHEN** widok odświeża prawdopodobieństwa obserwowanych wyników
- **THEN** pobiera je jednym żądaniem obejmującym całą listę

#### Scenario: Cena, która się zestarzała

- **WHEN** ostatnia znana cena wyniku pochodzi sprzed dłuższego czasu niż takt próbkowania
- **THEN** widok MUST pokazać, kiedy została wzięta
- **AND** MUST NOT przedstawiać jej jako ceny bieżącej

### Requirement: Zmiana w oknie jest liczona przez moduł i ma nazwany brak

Widok MUST pokazywać zmianę prawdopodobieństwa w oknach, których dostarcza kontrakt modułu, i MUST
brać ją z modułu, a nie liczyć samodzielnie z dwóch odczytów: punkt odniesienia jest wyznaczany
z tolerancją na nierówny takt i widok nie ma z czego go odtworzyć.

Okno, dla którego moduł nie ma pokrycia, MUST być pokazane jako **brak z przyczyną**. Widok
MUST NOT przedstawiać takiego okna jako zmiany zerowej ani zostawiać w tym miejscu pustego pola:
jedno kłamie o rynku, który stał, drugie wygląda jak awaria widoku.

Widok MUST udostępniać moment punktu bazowego, względem którego zmiana została policzona.

#### Scenario: Okno z pokryciem

- **WHEN** moduł ma pokrycie dla żądanego okna
- **THEN** widok pokazuje zmianę oraz moment punktu bazowego, względem którego ją policzono

#### Scenario: Okno bez pokrycia

- **WHEN** moduł nie ma pokrycia dla żądanego okna
- **THEN** widok MUST nazwać brak i jego przyczynę
- **AND** MUST NOT pokazać w tym miejscu zera

### Requirement: Objęcie obserwacją odbywa się z zakładki

Operator MUST móc objąć wydarzenie obserwacją z tej zakładki, wskazując je adresem na
polymarket.com albo identyfikatorem — obie drogi MUST prowadzić do tej samej obserwacji.
Wydarzenie już obserwowane MUST być rozpoznane jako takie: widok MUST powiedzieć, że obserwacja
istnieje, i MUST NOT utworzyć drugiej ani naruszyć zebranej historii.

Odmowa modułu — w szczególności odmowa z powodu sufitu liczby obserwacji — MUST być pokazana
operatorowi wraz z jej przyczyną. Widok MUST NOT przedstawiać odmowy jako niedostępności modułu.

#### Scenario: Objęcie obserwacją adresem

- **WHEN** operator podaje adres wydarzenia na polymarket.com
- **THEN** wydarzenie zostaje objęte obserwacją i pojawia się na liście

#### Scenario: Wydarzenie już obserwowane

- **WHEN** operator podaje wydarzenie, które jest już obserwowane
- **THEN** widok MUST to powiedzieć
- **AND** MUST NOT powstać druga obserwacja

#### Scenario: Sufit obserwacji

- **WHEN** moduł odmawia objęcia obserwacją z powodu sufitu
- **THEN** widok pokazuje odmowę wraz z przyczyną i tym, co zrobić najpierw
- **AND** MUST NOT przedstawić jej jako awarii modułu

### Requirement: Grupy obserwacji są operatora

Operator MUST móc tworzyć grupy obserwacji, przypisywać do nich wydarzenia i je kasować. Grupy
MUST być wyłącznie sposobem porządkowania listy: skasowanie grupy MUST NOT zakończyć żadnej
obserwacji ani usunąć żadnej zebranej próbki.

Widok MUST umożliwiać ograniczenie listy do jednej grupy.

#### Scenario: Skasowanie grupy

- **WHEN** operator kasuje grupę obserwacji
- **THEN** wydarzenia z tej grupy pozostają obserwowane
- **AND** ich zebrana historia pozostaje nienaruszona

#### Scenario: Ograniczenie listy do grupy

- **WHEN** operator wybiera grupę
- **THEN** lista pokazuje wyłącznie wydarzenia do niej przypisane

### Requirement: Seria prawdopodobieństwa jest oglądalna wraz z granicą pokrycia

Widok MUST pokazywać przebieg prawdopodobieństwa wybranego wyniku w czasie, z zakresem czasu
wybieranym przez operatora. Oś wartości MUST być skalą 0..1 i MUST być tak opisana.

Granica najstarszego osiągalnego momentu MUST być **narysowana**, a nie domyślna z tego, że
przebieg się urywa. Wymaganie jest tu tym, czym „brak pokrycia" jest przy oknach: seria kończąca
się bez powodu wygląda jak seria, dla której nic się nie działo, a naprawdę jest serią, dla której
niczego nie da się już dowiedzieć — dostawca nie sięga dalej wstecz.

Dziura wewnątrz zakresu MUST być widoczna jako dziura. Widok MUST NOT łączyć dwóch punktów
rozdzielonych brakiem pokrycia odcinkiem, który sugeruje przebieg pomiędzy nimi.

#### Scenario: Przebieg wybranego wyniku

- **WHEN** operator wybiera wynik i zakres czasu
- **THEN** widok pokazuje przebieg prawdopodobieństwa tego wyniku w tym zakresie

#### Scenario: Zakres sięgający przed granicę pokrycia

- **WHEN** wybrany zakres sięga przed najstarszy osiągalny moment
- **THEN** widok MUST narysować tę granicę
- **AND** MUST NOT przedstawić braku danych przed nią jako końca przebiegu

#### Scenario: Dziura w środku zakresu

- **WHEN** w zebranej serii jest przerwa
- **THEN** widok MUST pokazać ją jako przerwę
- **AND** MUST NOT poprowadzić przez nią odcinka łączącego jej krańce

### Requirement: Kasowanie zebranej historii jest tutaj i wymaga potwierdzenia

Terminal MUST udostępniać operatorowi usunięcie obserwacji wraz z całą zebraną historią, i MUST
być jedynym miejscem, w którym da się to zrobić. Czynność MUST wymagać potwierdzenia nazywającego,
czego dotyczy i że jest nieodwracalna.

Nieodwracalność jest tu inna niż przy archiwum świec i MUST być powiedziana wprost: dostawca nie
oddaje historii rynku, który się rozstrzygnął, a dla pozostałych sięga tylko tak daleko, jak sięga.
Usunięte dane w większości przypadków nie dadzą się zebrać ponownie żadnym kosztem.

Zakres MUST być nazwany jako całość, a nie jako jedna z dwóch rzeczy do wyboru: zatrzymania
zbierania bez usunięcia nie ma, więc potwierdzenie MUST NOT sugerować, że obserwacja przetrwa
czynność albo że historia przetrwa usunięcie obserwacji.

#### Scenario: Usunięcie zebranej historii

- **WHEN** operator potwierdza usunięcie
- **THEN** wydarzenie znika z listy obserwacji wraz z całą swoją historią

#### Scenario: Potwierdzenie mówi, co się stanie

- **WHEN** operator sięga po usunięcie
- **THEN** widok MUST zażądać potwierdzenia
- **AND** potwierdzenie MUST nazwać zakres usunięcia — wydarzenie i wszystko, co dla niego
  zebrano — oraz jego nieodwracalność

#### Scenario: Odstąpienie od usunięcia

- **WHEN** operator nie potwierdza usunięcia
- **THEN** nic nie zostaje usunięte

### Requirement: Zakładka odróżnia odmowę od niedostępności modułu

Odpowiedź modułu stwierdzająca brak uprawnienia albo brak ważnego poświadczenia MUST być przez
zakładkę potraktowana inaczej niż brak odpowiedzi. Zakładka MUST powiedzieć operatorowi, który
z dwóch przypadków zaszedł.

Wymaganie ma swoją cenę zapisaną w historii tego repozytorium: wskaźnik zlewający problem z sesją
z martwym backendem wysyła operatora diagnozować moduł, który działa. Tu przypadek „nie masz
uprawnienia do kontraktu REST" jest szczególnie prawdopodobny, bo uprawnienie to nadaje się
osobnym krokiem po stronie infrastruktury i może po prostu jeszcze nie dotrzeć.

#### Scenario: Moduł nie odpowiada

- **WHEN** moduł nie odpowiada na żądanie zakładki
- **THEN** zakładka MUST przedstawić to jako niedostępność modułu

#### Scenario: Wołający bez uprawnienia do kontraktu REST

- **WHEN** moduł odmawia żądaniu z powodu tożsamości wołającego
- **THEN** zakładka MUST przedstawić to jako odmowę, a nie jako niedostępność modułu

### Requirement: Zwinięty wiersz identyfikuje obserwację i nie udaje odczytu

Wydarzenie zwinięte MUST nieść to, po czym operator je rozpozna i czym może w nim ruszyć: tytuł,
grupę, stan zbierania i usunięcie. Zwinięty wiersz MUST NOT pokazywać prawdopodobieństwa żadnego
wyniku — ani liczbą, ani paskiem, ani „liderem" rynku.

Skrót do jednej ceny na rynek jest sprowadzeniem rynku do jednej ceny „za", którego widok
rozwinięty ma zakaz; zwinięcie nie jest wyjątkiem od tej reguły, tylko miejscem, w którym łatwo
ją obejść. Odczyt jest po rozwinięciu, gdzie każdy rynek niesie wszystkie swoje wyniki.

**Stan zbierania zostaje**, mimo że nie jest ani tytułem, ani grupą: obecność na liście nie
dowodzi, że ceny przychodzą, i zwinięty wiersz jest jedynym miejscem, w którym operator dowie się
o zatrzymanym zbieraniu, zanim cokolwiek rozwinie.

#### Scenario: Wydarzenie zwinięte

- **WHEN** operator ogląda listę obserwacji bez rozwijania żadnej
- **THEN** każdy wiersz niesie tytuł, grupę, stan zbierania i sposób usunięcia
- **AND** MUST NOT nieść prawdopodobieństwa żadnego wyniku

#### Scenario: Rozwinięcie wydarzenia

- **WHEN** operator rozwija wydarzenie
- **THEN** widok pokazuje jego rynki wraz ze wszystkimi wynikami i ich prawdopodobieństwami
