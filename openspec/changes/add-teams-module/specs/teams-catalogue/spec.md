## Purpose

Czym jest zespół zapisany w katalogu: z czego składa się jego definicja, jak powstaje kolejna
rewizja, czego moduł przy zapisie nie przyjmie i co katalog udostępnia temu, kto go czyta.

## ADDED Requirements

### Requirement: Definicja zespołu wystarcza, żeby zbudować z niej pracę

Definicja zespołu MUST być daną, którą moduł czyta, a nie kodem, który trzeba dopisać.
Definicja MUST nieść komplet tego, co potrzebne do wykonania: dla każdego agenta jego rolę,
prompt, wytyczne, wskazanie modelu i wskazanie narzędzi, którymi ma dysponować, a dla każdej
zależności między agentami jej kierunek.

Dołożenie zespołu MUST NOT wymagać zmiany w module ani jego wdrożenia. Zespół, którego
uruchomienie wymaga wcześniejszego dopisania kodu, nie jest zespołem zdefiniowanym przez
operatora — jest zespołem zaprogramowanym przez kogoś innego, a wtedy porównywanie wariantów
kosztuje tyle co wdrożenie i nikt go nie robi.

#### Scenario: Operator składa zespół, jakiego moduł nie widział

- **WHEN** operator zapisuje definicję z rolami i zależnościami, których nie ma żaden
  zapisany wcześniej zespół
- **THEN** moduł przyjmuje ją i potrafi ją uruchomić
- **AND** nie wymaga do tego zmiany w swoim kodzie ani restartu

#### Scenario: Agent bez wskazanego narzędzia

- **WHEN** definicja nie przypisuje agentowi żadnego narzędzia
- **THEN** jest to poprawna definicja, a agent pracuje bez narzędzi

### Requirement: Rewizja raz zapisana się nie zmienia

Zapis zmienionej definicji MUST tworzyć kolejną rewizję zespołu, a MUST NOT nadpisywać
poprzedniej. Każda rewizja MUST być czytelna po zapisaniu następnej.

Rewizja jest jedyną rzeczą, która nadaje śladowi przebiegu znaczenie po czasie. Definicja
zmieniana pod spodem sprawia, że przebieg sprzed tygodnia mówi o zespole, którego już nie ma,
a wtedy porównanie dwóch wariantów porównuje dwie nieznane rzeczy.

#### Scenario: Operator poprawia prompt roli

- **WHEN** operator zmienia prompt jednego agenta i zapisuje zespół
- **THEN** powstaje kolejna rewizja
- **AND** poprzednia rewizja pozostaje czytelna w niezmienionej postaci

#### Scenario: Odczyt rewizji, po której były następne

- **WHEN** wołający prosi o rewizję, po której zapisano nowsze
- **THEN** dostaje ją taką, jaka była w chwili zapisu

### Requirement: Definicja, której nie da się wykonać, jest odrzucana przy zapisie

Moduł MUST odrzucić zapis definicji, która niesie cykl zależności, agenta nieosiągalnego
z żadnego punktu startowego, wskazanie modelu spoza katalogu modeli albo wskazanie narzędzia,
którego serwer narzędzi nie ogłasza. Odmowa MUST nazywać agenta albo zależność, przez którą
zapadła.

Sprawdzenie MUST zapadać przy zapisie, nie przy uruchomieniu. Definicja, którą da się zapisać,
a nie da uruchomić, jest pułapką zastawioną na operatora w najgorszym momencie — wtedy, gdy
myśli, że eksperyment już biegnie.

#### Scenario: Zależności tworzą cykl

- **WHEN** operator zapisuje definicję, w której zależności prowadzą z powrotem do agenta,
  od którego wyszły
- **THEN** moduł odmawia zapisu
- **AND** komunikat nazywa zależność zamykającą cykl

#### Scenario: Agent, do którego nic nie prowadzi i który do niczego nie prowadzi

- **WHEN** definicja niesie agenta bez żadnej zależności w obie strony, a inni agenci są
  ze sobą połączeni
- **THEN** moduł odmawia zapisu, wskazując tego agenta

#### Scenario: Wskazanie modelu, którego katalog nie zawiera

- **WHEN** definicja wskazuje agentowi model spoza katalogu modeli modułu
- **THEN** moduł odmawia zapisu, wskazując agenta i model

### Requirement: Katalog wystarcza, żeby wybrać zespół bez otwierania go

Moduł MUST publikować katalog zespołów, a wpis katalogu MUST nieść nazwę, opis, wskazanie
najnowszej rewizji i moment ostatniej zmiany. Wołający MUST móc zbudować z samego katalogu
listę, na której operator wskaże zespół, nie wczytując definicji żadnego z nich.

#### Scenario: Terminal buduje listę katalogu

- **WHEN** terminal odczytuje katalog zespołów
- **THEN** każdy wpis niesie nazwę, opis, najnowszą rewizję i moment ostatniej zmiany
- **AND** lista powstaje bez pobierania definicji zespołów

### Requirement: Zespół wycofany z katalogu nie zabiera ze sobą przebiegów

Wycofanie zespołu MUST usunąć go z katalogu wybieranego do uruchomienia, a MUST NOT usunąć
śladu przebiegów, które się na nim odbyły, ani rewizji, których te przebiegi dotyczą.

Wynik eksperymentu jest tym, po co ten moduł istnieje, i MUST NOT znikać dlatego, że operator
posprzątał listę.

#### Scenario: Wycofanie zespołu, na którym coś już biegło

- **WHEN** operator wycofuje zespół mający zapisane przebiegi
- **THEN** zespół znika z katalogu do uruchomienia
- **AND** ślad jego przebiegów i wskazywane przez nie rewizje pozostają czytelne
