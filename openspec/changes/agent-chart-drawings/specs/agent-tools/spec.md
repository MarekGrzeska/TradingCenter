## MODIFIED Requirements

### Requirement: Zestaw narzędzi pochodzi z serwera, nie z tego modułu

Moduł MUST pobierać zestaw dostępnych narzędzi wraz z ich opisami od serwera narzędzi i
MUST NOT nieść własnej listy narzędzi ani własnych opisów **tych, które serwer ogłasza**.
Narzędzie dołożone po stronie serwera MUST stać się dostępne modelowi bez zmiany w tym
module.

Moduł MUST NOT publikować modelowi narzędzia, którego serwer nie ogłosił — **poza
narzędziami wymienionymi z nazwy w specyfikacjach tego modułu**. Dziś są to trzy
narzędzia: ustawienie zawartości wykresu w terminalu (`agent-chart-control`) oraz
postawienie i odczytanie rysunków na wykresie (`agent-chart-drawings`). Narzędzie własne
modułu MUST być odróżnialne od narzędzia serwera w śladzie wywołania, żeby dało się
powiedzieć, kto je wykonał.

Moduł MUST NOT dokładać narzędzia własnego przez ustawienie ani tryb: granica przebiega
w specyfikacji i jej przesunięcie kosztuje zmianę tego dokumentu.

#### Scenario: Narzędzie dołożone po stronie serwera

- **WHEN** serwer narzędzi zaczyna ogłaszać narzędzie, którego wcześniej nie było
- **THEN** model dostaje je w kolejnej sesji modułu z serwerem, bez zmiany w tym module

#### Scenario: Opis narzędzia zmieniony po stronie serwera

- **WHEN** serwer zmienia opis narzędzia
- **THEN** model widzi opis serwera, a nie kopię trzymaną w tym module

#### Scenario: Narzędzie własne modułu obok narzędzi serwera

- **WHEN** moduł ma połączenie z serwerem narzędzi
- **THEN** model dostaje narzędzia serwera oraz narzędzia ustawiające wykres i rysujące na nim
- **AND** ślad wywołania mówi, które z nich zostało wykonane przez ten moduł

#### Scenario: Brak serwera narzędzi

- **WHEN** moduł nie ma skonfigurowanego serwera narzędzi
- **THEN** model dostaje same narzędzia własne modułu, zamiast żadnego

### Requirement: Agent zapisuje wyłącznie w widoku terminala

Zmianami stanu, jakie moduł MUST umieć wykonać przez narzędzie, są: ustawienie tego, co
terminal rysuje — zestawu wskaźników, symbolu i interwału aktywnego slotu — oraz
postawienie i skasowanie rysunków na wykresie instrumentu (`agent-chart-drawings`).

Moduł MUST NOT wykonywać przez narzędzia żadnej innej zmiany stanu: nie rozpoczyna
zbierania pary, nie kasuje danych, nie składa zlecenia, nie zmienia konfiguracji żadnego
modułu i nie pisze do archiwum. Serwer narzędzi MUST pozostać czytający — zapis nie jedzie
przez niego.

Zapis MUST być odwracalny ręką operatora, bez rozmowy i bez modelu: zawartość slotu tym
samym wybierakiem, którym operator ustawia wykres sam, a rysunek listą, z której operator
go usuwa. Narzędzie, którego skutku operator nie umie cofnąć bez agenta, jest poza tym
wymaganiem.

#### Scenario: Operator prosi o pokazanie wskaźnika

- **WHEN** operator prosi agenta, żeby pokazał EMA 200 na wykresie
- **THEN** agent ma narzędzie, którym to robi, i wykres to pokazuje

#### Scenario: Operator prosi o naniesienie oporu

- **WHEN** operator prosi agenta, żeby naniósł opór na wskazanej cenie
- **THEN** agent ma narzędzie, którym to robi, i wykres to pokazuje

#### Scenario: Operator prosi o wykonanie akcji poza wykresem

- **WHEN** operator prosi agenta, żeby zaczął zbierać parę albo złożył zlecenie
- **THEN** agent nie ma narzędzia, którym mógłby to zrobić
- **AND** odpowiada, że to jest poza jego zakresem, zamiast zgłaszać chwilową awarię

#### Scenario: Operator cofa to, co ustawił agent

- **WHEN** operator usuwa wybierakiem wskaźnik, który ustawił agent
- **THEN** wskaźnik znika i nie wraca sam z siebie

#### Scenario: Operator cofa to, co narysował agent

- **WHEN** operator usuwa z listy rysunek, który postawił agent
- **THEN** rysunek znika i nie wraca sam z siebie
