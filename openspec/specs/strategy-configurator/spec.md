# strategy-configurator Specification

## Purpose
Strategia, którą operator składa na ekranie, a nie w obrazie: reguła jest danymi w zamkniętym
słowniku węzłów, zapisaną rewizją, którą obserwacja przypina — i przechodzi tę samą ocenę,
te same odmowy i ten sam ślad co strategia będąca kodem.
## Requirements

### Requirement: Reguła jest danymi w zamkniętym słowniku węzłów

Reguła strategii MAY być zapisana jako dane. Zapisana regułą MUST być drzewem węzłów
o zamkniętym, zadeklarowanym słowniku: liczbowe liście (stała, parametr strategii, odczyt
faktu, pole świecy), działania arytmetyczne, wywołania z zamkniętej listy funkcji,
porównania, spójniki logiczne, przecięcie i przesunięcie o świecę. Słownik MUST NOT zawierać
pętli, definiowania zmiennych, definiowania funkcji ani żadnego węzła sięgającego poza
podane fakty i parametry. Reguła MUST być odrzucona, jeśli przekracza zadeklarowane sufity
liczby faktów, liczby węzłów lub głębokości drzewa.

Zamknięty słownik jest tym, co pozwala nie robić review każdej reguły z osobna: język,
w którym nie da się wyrazić efektu ubocznego, nie wymaga sprawdzania, czy go nie wywołano.
Sufity są drugą połową tej samej myśli — reguła, która czyta czterdzieści wskaźników, jest
obciążeniem archiwum, o którym nikt nie zdecydował.

#### Scenario: Reguła nazywa węzeł spoza słownika

- **WHEN** definicja niesie węzeł o rodzaju, którego słownik nie zawiera
- **THEN** zapis zostaje odrzucony z powodem nazywającym ten rodzaj

#### Scenario: Reguła przekracza sufit

- **WHEN** definicja deklaruje więcej faktów albo głębsze drzewo niż dopuszczony sufit
- **THEN** zapis zostaje odrzucony z powodem nazywającym sufit i wartość, która go przekroczyła

### Requirement: Brak odczytu nie jest sygnałem, a odmowa jest domknięta

Wyrażenie reguły, którego którykolwiek składnik opiera się na odczycie niepoliczonym przez
archiwum, MUST dać wynik nieustalony, a nie liczbę ani fałsz. Warunek nieustalony MUST
prowadzić do odmowy, nigdy do wejścia. Spójniki logiczne MUST rozstrzygać przypadki, które
da się rozstrzygnąć bez brakującego składnika: koniunkcja z jawnym fałszem MUST być fałszem,
alternatywa z jawną prawdą MUST być prawdą. Definicja MUST deklarować własny powód odmowy
dla nieustalonego odczytu.

Nieustabilizowana średnia wygląda dokładnie tak samo jak przecięcie, którego nie było — to
jest ta pomyłka, którą każdy ręcznie pisany wpis musi wyłapać sam i którą interpreter ma
wyłapać raz. Kierunek jest domknięty na odmowę, bo to jedyny bezpieczny kierunek dla systemu
decydującego o pieniądzach.

#### Scenario: Wskaźnik nie zdążył się ustabilizować

- **WHEN** reguła porównuje odczyt, którego archiwum nie policzyło na tej świecy
- **THEN** ocena kończy się odmową z powodem zadeklarowanym dla nieustalonego odczytu

#### Scenario: Koniunkcja z jawnym fałszem

- **WHEN** jeden ze składników koniunkcji jest jawnie fałszywy, a inny nieustalony
- **THEN** wynikiem koniunkcji jest fałsz, a nie wynik nieustalony

### Requirement: Definicja jest odrzucana w chwili zapisu

Definicja reguły MUST być sprawdzona przy zapisie, przeciwko katalogowi wskaźników
archiwum, i odrzucona, jeśli: nazywa wskaźnik, którego archiwum nie ogłasza; nazywa linię,
której wpis tego wskaźnika nie ogłasza; nazywa parametr wskaźnika, którego ten nie ma;
podaje wartość poza zakresem ogłoszonym przez archiwum; deklaruje własny parametr o zakresie
szerszym niż zakres parametru wskaźnika, na który ten parametr wskazuje; odwołuje się do
klucza faktu albo parametru, których sama nie deklaruje; nazywa rozdzielczość spoza słownika
archiwum; albo nie ma setupu z kompletem poziomów. Każda odmowa MUST nazywać to, co ją
wywołało. Gdy katalog archiwum jest nieosiągalny, zapis MUST zostać odrzucony, a nie
przyjęty bez sprawdzenia.

Sprawdzenie przy zakładaniu obserwacji MUST zostać zachowane niezależnie od tego: katalog
archiwum może się zmienić między zapisem definicji a jej uruchomieniem, więc wcześniejsze
sprawdzenie jest wygodą dla operatora, a nie zastąpieniem tamtego.

Czego sprawdzić się statycznie nie da — na przykład tego, że wyliczona obrona nie zrówna się
z wyliczonym wejściem — MUST pozostać odmową przy ocenie świecy, z powodem.

#### Scenario: Definicja nazywa nieogłoszony wskaźnik

- **WHEN** operator zapisuje definicję z faktem o wskaźniku, którego archiwum nie ogłasza
- **THEN** zapis zostaje odrzucony z powodem nazywającym ten wskaźnik

#### Scenario: Parametr strategii szerszy niż parametr wskaźnika

- **WHEN** definicja deklaruje parametr o zakresie wykraczającym poza zakres parametru
  wskaźnika, na który ten parametr wskazuje
- **THEN** zapis zostaje odrzucony z powodem nazywającym oba zakresy

#### Scenario: Archiwum nie odpowiada w chwili zapisu

- **WHEN** operator zapisuje definicję, a katalog wskaźników jest nieosiągalny
- **THEN** zapis zostaje odrzucony z powodem mówiącym, czego nie dało się sprawdzić
- **AND** żadna definicja nie zostaje zapisana bez sprawdzenia

### Requirement: Rewizja jest niezmienna, a obserwacja ją przypina

Zapis zmienionej definicji MUST tworzyć nową rewizję; rewizja raz zapisana MUST NOT być
zmieniona ani usunięta, dopóki wskazuje ją choćby jedna decyzja. Obserwacja MUST wskazywać
konkretną rewizję, a zapisanie nowszej MUST NOT zmieniać reguły, którą liczy działająca
obserwacja. Przejście obserwacji na nowszą rewizję MUST być osobnym, jawnym działaniem.
Zestaw parametrów MUST należeć do rewizji, a nie do strategii; obserwacja i backtest MUST
odmówić zestawu należącego do innej rewizji, nazywając obie.

Reguła zmieniona pod stopami działającej obserwacji daje decyzje sprzed i po zmianie, które
z zewnątrz wyglądają na porównywalne, a nie są. Zestaw parametrów przypisany do strategii
zamiast do rewizji jest tym samym błędem o warstwę niżej: wartość dopuszczalna wczoraj może
dziś nie mieć nawet swojej deklaracji.

#### Scenario: Zapis zmienionej definicji

- **WHEN** operator zapisuje zmienioną definicję
- **THEN** powstaje nowa rewizja, a poprzednia pozostaje odczytywalna w swoim brzmieniu
- **AND** obserwacje wskazujące poprzednią rewizję liczą dalej po staremu

#### Scenario: Zestaw parametrów spod innej rewizji

- **WHEN** obserwacja ma zostać założona z zestawem parametrów należącym do innej rewizji
- **THEN** zostaje odrzucona z powodem nazywającym obie rewizje

### Requirement: Strategia odniesienia pozostaje kodem i jest miarą interpretera

Strategia odniesienia MUST pozostać wpisem kodowym w obrazie i MUST być obliczalna bez
odczytu z bazy. Moduł MUST nieść jej odpowiednik wyrażony jako reguła-dane — obok wpisu
kodowego, a nie jako druga pozycja katalogu, którą operator musiałby od niego odróżniać —
a testy modułu MUST porównywać oba na tych samych faktach: akcja, powód, rodzaj odmowy, poziomy
i punktacja MUST być identyczne, a cechy wpisu kodowego MUST być podzbiorem cech
odpowiednika o tych samych wartościach.

Podłoga, którą da się przestawić klikaniem, przestaje być podłogą — a wyrażenie znanej,
przejrzanej reguły w słowniku węzłów jest jedynym uczciwym sprawdzianem, czy ten słownik
jest dość wyrazisty i czy interpreter liczy to, co się wydaje. Jedna dopuszczona różnica —
cechy liczone także przy odmowie — jest kierunkiem „więcej informacji", nie rozjazdem logiki,
i test nazywa ją wprost.

#### Scenario: Bliźniak strategii odniesienia

- **WHEN** ta sama seria faktów zostaje oceniona wpisem kodowym strategii odniesienia i jej
  odpowiednikiem wyrażonym jako reguła
- **THEN** obie oceny dają tę samą akcję, ten sam powód, te same poziomy i tę samą punktację

#### Scenario: Wpis kodowy bez bazy

- **WHEN** backtest liczy strategię odniesienia
- **THEN** przebieg dochodzi do skutku bez odczytu definicji z bazy
