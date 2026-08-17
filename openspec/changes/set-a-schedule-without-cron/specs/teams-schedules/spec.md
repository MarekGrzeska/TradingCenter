## ADDED Requirements

### Requirement: Harmonogram da się opisać rytmem, a moduł zna oba zapisy

Moduł MUST przyjmować opis harmonogramu podany jako rytm — odstęp w minutach, godzina doby,
dni tygodnia albo dzień miesiąca — i MUST sam zamienić go na wyrażenie czasowe, które
wykonuje. Moduł MUST publikować ten rytm przy harmonogramie, obok wyrażenia czasowego.
Harmonogram, którego wyrażenia nie da się wyrazić żadnym z rytmów, MUST zostać opublikowany
z rytmem pustym i MUST nadal dać się odczytać oraz wyzwalać.

Zamiana rytmu na wyrażenie czasowe istnieje raz — w module. Odbiorca kontraktu, który
musiałby ją powtórzyć u siebie, żeby pokazać operatorowi jego własny harmonogram, prędzej
czy później pokaże co innego, niż moduł wykona.

#### Scenario: Harmonogram zapisany rytmem

- **WHEN** operator zapisuje harmonogram jako „codziennie o 9:00"
- **THEN** moduł zapisuje harmonogram wyzwalający się o 9:00 czasu polskiego
- **AND** odczyt tego harmonogramu zwraca ten sam rytm

#### Scenario: Wyrażenie spoza rytmów kreatora

- **WHEN** harmonogram niesie wyrażenie czasowe, którego nie da się opisać żadnym z rytmów
- **THEN** odczyt zwraca ten harmonogram z pustym rytmem i z jego wyrażeniem
- **AND** harmonogram wyzwala się dalej

### Requirement: Moduł liczy najbliższe wyzwolenia także dla opisu, którego nie zapisano

Moduł MUST odpowiadać na pytanie „kiedy wyzwoli się harmonogram opisany tak a tak" dla opisu,
który nie został jeszcze zapisany. Odpowiedź MUST mieć tę samą postać co dla harmonogramu
zapisanego. Opis, którego moduł nie umie wykonać, MUST zostać odrzucony z powodem, a nie
policzony.

Operator układający harmonogram ma zobaczyć jego skutek przed zapisem. Bez tego jedyną drogą
do podglądu jest zapisanie harmonogramu, obejrzenie i poprawienie go — czyli trzy zapisy na
jedną decyzję.

#### Scenario: Podgląd przed zapisem

- **WHEN** operator pyta o najbliższe wyzwolenia dla opisu, którego jeszcze nie zapisał
- **THEN** moduł zwraca te momenty, nie zapisując żadnego harmonogramu

#### Scenario: Opis, którego nie da się wykonać

- **WHEN** operator pyta o najbliższe wyzwolenia dla opisu niepoprawnego
- **THEN** moduł odmawia z powodem nazywającym, co jest w tym opisie nie tak

## MODIFIED Requirements

### Requirement: Moduł ma jeden zegar i sam publikuje najbliższe wyzwolenia

Czas wyzwolenia MUST być liczony w strefie `Europe/Warsaw` i MUST być publikowany w UTC.
Godzina harmonogramu MUST NOT przesuwać się przy zmianie czasu: harmonogram opisany na 9:00
wyzwala się o 9:00 czasu polskiego zarówno w czasie letnim, jak i zimowym. Moduł MUST
publikować moment najbliższego wyzwolenia harmonogramu, a jego wyliczenie MUST NOT być
zadaniem odbiorcy kontraktu. Budzenie się modułu MUST dać się wyłączyć ustawieniem aplikacji,
bez wdrażania nowego obrazu; wyłączenie MUST NOT zabrać możliwości uruchomienia przebiegu
ręcznie.

Operator pracuje w jednej strefie — swojej. Harmonogram liczony w UTC znaczył, że operator
sam wpisywał 7:00, żeby zespół ruszył o dziewiątej, i poprawiał to dwa razy w roku. Cena jest
w drugą stronę: granica dobowa kosztu nadal liczy się od północy UTC, więc odstęp między
resetem budżetu a porannym wyzwoleniem zmienia się o godzinę przy zmianie czasu. To jest
odstęp, którego nikt nie ogląda; przesuwająca się godzina wyzwolenia była widoczna codziennie.

#### Scenario: Operator pyta o najbliższe wyzwolenia

- **WHEN** operator otwiera harmonogram
- **THEN** dostaje z modułu moment najbliższego wyzwolenia i kolejnych

#### Scenario: Zmiana czasu

- **WHEN** harmonogram codzienny na 9:00 przechodzi przez zmianę czasu letniego na zimowy
- **THEN** wyzwala się dalej o 9:00 czasu polskiego
- **AND** publikowany moment wyzwolenia w UTC przesuwa się o godzinę

#### Scenario: Budzenie wyłączone ustawieniem

- **WHEN** budzenie się modułu jest wyłączone ustawieniem aplikacji
- **THEN** żaden harmonogram nie wyzwala
- **AND** ręczne uruchomienie przebiegu działa dalej
