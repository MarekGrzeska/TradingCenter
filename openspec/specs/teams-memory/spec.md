# teams-memory Specification

## Purpose
Czym jest pamięć zespołu: co zespół może zostawić następnemu przebiegowi, do czego ten zapis
należy, dlaczego stoi obok rewizji zamiast w niej, czego nie zmienia, jakie ma granice i kto go
usuwa.
## Requirements
### Requirement: Pamięć należy do zespołu i przeżywa przebieg

Moduł MUST przechowywać wpisy pamięci związane z **zespołem**. Wpis MUST być czytelny w kolejnych
przebiegach tego zespołu, niezależnie od tego, na której rewizji się odbywają i jak skończył się
przebieg, w którym powstał. Wpis MUST NOT być częścią rewizji ani MUST NOT wymagać zapisania nowej
rewizji, żeby powstać.

Rewizja mówi, czym zespół jest, i po zapisaniu się nie zmienia — pamięć mówi, czego zespół się
nauczył, i rośnie przy każdym przebiegu. Wpis wewnątrz rewizji zmuszałby każdą notatkę do
utworzenia nowej definicji, a wtedy dwa przebiegi „tej samej" rewizji nigdy nie byłyby tą samą
rewizją i porównanie wyników przestałoby cokolwiek znaczyć.

Wpis MUST nieść klucz agenta, który go zapisał, i wskazanie przebiegu, w którym powstał. Jedno i
drugie jest czytelnością eksperymentu, a nie uprawnieniem: żadne z nich MUST NOT decydować o tym,
kto wpis przeczyta.

#### Scenario: Kolejny przebieg czyta to, co zostawił poprzedni

- **WHEN** agent w jednym przebiegu zapisuje wpis, a w kolejnym przebiegu tego samego zespołu agent
  sięga po pamięć
- **THEN** dostaje ten wpis

#### Scenario: Wpis zostaje po przebiegu, który się nie udał

- **WHEN** przebieg zapisuje wpis, a potem kończy się błędem, przerwaniem albo przekroczeniem limitu
- **THEN** wpis pozostaje czytelny dla kolejnych przebiegów

#### Scenario: Nowa rewizja nie zabiera pamięci

- **WHEN** operator zapisuje kolejną rewizję zespołu, który ma już wpisy pamięci
- **THEN** wpisy pozostają czytelne dla przebiegów tej nowej rewizji

#### Scenario: Pamięć nie sięga poza zespół

- **WHEN** agent w przebiegu jednego zespołu sięga po pamięć
- **THEN** dostaje wyłącznie wpisy tego zespołu
- **AND** wpisy innych zespołów tego samego operatora MUST NOT zostać mu podane

### Requirement: Wpis raz zapisany się nie zmienia

Zapisany wpis pamięci MUST NOT być nadpisywany ani poprawiany. Agent, który chce sprostować to, co
zostało zapisane, MUST zrobić to kolejnym wpisem.

Ślad przebiegu sprzed tygodnia ma się czytać razem z pamięcią, jaką zespół wtedy zostawił, a nie z
jej dzisiejszą postacią. Wpis poprawiany pod spodem sprawia, że przebieg, który powołał się na
notatkę, powołuje się na zdanie, którego już nie ma — to ta sama zasada, dla której rewizja jest
niezmienna (`teams-catalogue`, „Rewizja raz zapisana się nie zmienia").

#### Scenario: Agent sprostowuje wcześniejszą notatkę

- **WHEN** agent zapisuje wpis prostujący to, co zapisał wcześniej
- **THEN** powstaje kolejny wpis
- **AND** poprzedni pozostaje czytelny w niezmienionej postaci

### Requirement: Wpis powstaje decyzją agenta i zostaje w śladzie przebiegu

Wpis pamięci MUST powstawać wyłącznie z wywołania narzędzia przez agenta. Moduł MUST NOT zapisywać
do pamięci wypowiedzi agenta, briefingu ani przebiegu z własnej inicjatywy. Zapis i odczyt pamięci
MUST zostać w śladzie przebiegu jako wywołania narzędzi, na tych samych prawach co każde inne.

To jest granica między pamięcią a transkryptem. Automatyczny zapis rósłby przy każdym przebiegu bez
niczyjej decyzji i płaciłby za siebie w każdej turze każdego agenta; wpis wywołany narzędziem jest
decyzją, którą widać potem w śladzie — razem z tym, co zespół przeczytał, zanim ją podjął.

#### Scenario: Przebieg bez wywołania narzędzia pamięci

- **WHEN** przebieg kończy się i żaden agent nie wywołał narzędzia zapisującego pamięć
- **THEN** nie powstaje żaden wpis

#### Scenario: Ślad pokazuje, co zespół przeczytał i co zostawił

- **WHEN** agent w przebiegu odczytuje pamięć, a potem zapisuje wpis
- **THEN** ślad przebiegu niesie oba wywołania wraz z ich wynikiem

### Requirement: Odczyt oddaje najnowsze wpisy, a nie całą pamięć

Odczyt pamięci MUST oddawać wpisy od najnowszego i MUST być ograniczony sufitem liczby wpisów
zapisanym w module. Odpowiedź MUST powiedzieć, gdy pamięć niesie więcej wpisów, niż zostało
oddanych.

Pamięć bez sufitu odczytu rośnie w transkrypt podawany modelowi w całości — a to jest dokładnie
ten kształt, którego zespoły nie trzymają (`teams-runs`, „Agent widzi wypowiedzi poprzedników, a nie
całą historię przebiegu"). Milczące ucięcie jest gorsze niż sufit: model wnioskuje wtedy z pamięci,
o której sądzi, że jest całą.

#### Scenario: Pamięć większa niż sufit odczytu

- **WHEN** agent odczytuje pamięć zespołu mającego więcej wpisów, niż wynosi sufit
- **THEN** dostaje najnowsze wpisy do wysokości sufitu
- **AND** odpowiedź mówi, że pamięć niesie ich więcej

#### Scenario: Zespół bez ani jednego wpisu

- **WHEN** agent odczytuje pamięć zespołu, który nie ma jeszcze wpisów
- **THEN** dostaje pustą pamięć jako poprawną odpowiedź, a nie awarię

### Requirement: Pamięć ma granice zapisane w module, nie w konfiguracji

Moduł MUST odmówić zapisu wpisu dłuższego niż zapisany sufit znaków i MUST odmówić zapisu po
wyczerpaniu sufitu wpisów przypadających na jeden przebieg. Odmowa MUST nazwać granicę i wartość,
która ją przekroczyła. Odmowa zapisu MUST NOT zatrzymać przebiegu — jest wynikiem wywołania
narzędzia, nie awarią przebiegu.

Granice te MUST być stałymi modułu. Sufit pamięci nie jest budżetem operatora — inaczej niż granice
handlowe i dobowa granica kosztu, które operator ustawia w rewizji — bo chroni nie jego pieniądze,
lecz kształt, w jakim moduł podaje cokolwiek modelowi.

#### Scenario: Wpis dłuższy niż wolno

- **WHEN** agent próbuje zapisać wpis przekraczający sufit znaków
- **THEN** wywołanie zostaje odrzucone z podaniem sufitu i zmierzonej długości
- **AND** przebieg pracuje dalej

#### Scenario: Agenci wyczerpali pulę zapisów przebiegu

- **WHEN** w jednym przebiegu zapisano tyle wpisów, ile wynosi sufit, i pada kolejne wywołanie
  zapisujące
- **THEN** zostaje odrzucone z podaniem granicy
- **AND** wpisy zapisane wcześniej w tym przebiegu pozostają

### Requirement: Pamięć jest widoczna dla operatora i usuwana wyłącznie przez niego

Moduł MUST udostępniać operatorowi odczyt wpisów pamięci jego zespołu oraz usunięcie pojedynczego
wpisu. Żadne narzędzie podawane agentowi MUST NOT usuwać ani zmieniać wpisu. Pamięć MUST być
filtrowana właścicielem tak samo jak katalog: pamięć cudzego zespołu MUST być nieodróżnialna od
pamięci zespołu, który nie istnieje.

Zespół, który nauczył się rzeczy nieprawdziwej, powtórzy ją w każdym kolejnym przebiegu i będzie za
to płacił. Naprawia to operator, bo jest jedyną stroną, która wie, że wpis jest nieprawdą — agent
mający narzędzie kasujące ma zamiast tego sposób na wymazanie własnego błędu ze śladu.

#### Scenario: Operator usuwa nietrafiony wpis

- **WHEN** operator usuwa wpis pamięci swojego zespołu
- **THEN** wpis znika i nie trafia do kolejnych przebiegów
- **AND** ślady przebiegów, w których był odczytany albo zapisany, pozostają nietknięte

#### Scenario: Pamięć cudzego zespołu

- **WHEN** operator prosi o pamięć zespołu należącego do kogoś innego
- **THEN** odpowiedź jest taka sama jak dla zespołu, który nie istnieje

### Requirement: Wycofanie zespołu z katalogu nie zabiera jego pamięci

Wycofanie zespołu MUST NOT usunąć jego wpisów pamięci. Wpisy MUST pozostać czytelne dla operatora
razem ze śladem przebiegów, których dotyczą.

Ta sama zasada co przy przebiegach (`teams-catalogue`, „Zespół wycofany z katalogu nie zabiera ze
sobą przebiegów"): wynik eksperymentu nie znika dlatego, że operator posprzątał listę.

#### Scenario: Wycofanie zespołu mającego pamięć

- **WHEN** operator wycofuje zespół, który ma zapisane wpisy pamięci
- **THEN** zespół znika z katalogu do uruchomienia
- **AND** jego wpisy pamięci pozostają czytelne
