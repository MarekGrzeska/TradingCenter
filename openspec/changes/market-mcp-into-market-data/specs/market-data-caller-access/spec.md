## Purpose
Kto sięga po którą powierzchnię archiwum: trasa narzędziowa dla modeli, REST dla terminala,
i dlaczego samo przepuszczenie przez bramę platformy nie wystarcza, odkąd obie stoją
w jednej aplikacji.

## ADDED Requirements

### Requirement: Powierzchnia narzędziowa jest osiągalna po sieci, jedną drogą

Archiwum MUST udostępniać zestaw narzędzi klientowi MCP po sieci, pod jednym adresem
w swojej własnej aplikacji. Zestaw MUST być opisany raz; adres rozstrzyga o tym, jak
żądanie dociera, i o niczym więcej.

Dodanie narzędzia MUST być widoczne pod tym adresem bez osobnej rejestracji gdziekolwiek
indziej.

#### Scenario: Klient pyta o listę narzędzi

- **WHEN** klient MCP nawiązuje sesję pod adresem powierzchni narzędziowej
- **THEN** dostaje zestaw narzędzi z ich opisami i schematami

#### Scenario: Narzędzie dołożone do zestawu

- **WHEN** do archiwum trafia nowe narzędzie
- **THEN** jest widoczne pod tym samym adresem bez osobnej rejestracji

### Requirement: Żądanie z sieci niesie tożsamość wołającego

Archiwum MUST wymagać, żeby żądanie po sieci niosło tożsamość wołającego, i MUST odmówić
obsługi żądaniu, które jej nie niesie. Wymóg ten MUST dać się wyłączyć wyłącznie dla pracy
lokalnej, a jego wyłączenie MUST być świadomym ustawieniem, nie wartością domyślną
w środowisku zdalnym.

Archiwum MUST zapisywać w dzienniku fakt odmowy i tożsamość, dla której wywołanie przeszło —
nigdy zaś treści żądania ani wartości poświadczenia.

#### Scenario: Wołanie bez tożsamości przy włączonym wymogu

- **WHEN** żądanie po sieci nie niesie tożsamości wołającego, a archiwum jej wymaga
- **THEN** archiwum MUST odmówić obsługi
- **AND** MUST NOT wykonać żadnego narzędzia

#### Scenario: Praca lokalna

- **WHEN** archiwum jest uruchomione lokalnie z wyłączonym wymogiem tożsamości
- **THEN** narzędzia działają, a dziennik odnotowuje wywołanie bez tożsamości jako takie

### Requirement: Tożsamość rozstrzyga, po którą powierzchnię wolno sięgnąć

Sama obecność tożsamości MUST NOT wystarczać do sięgnięcia po dowolną trasę. Archiwum MUST
trzymać zapis tego, która tożsamość ma prawo do której powierzchni, i MUST odmówić
żądaniu spoza tego zapisu — nawet gdy żądanie niesie tożsamość, którą platforma
uwierzytelniła.

Wymaganie to istnieje, bo brama platformy autoryzuje **aplikację**, nie trasę: wpuszczenie
wołającego, który potrzebuje wyłącznie narzędzi, otwiera mu bez tego zapisu również trasy
zmieniające stan archiwum — rozpoczęcie zbierania pary i skasowanie jej danych.

Zapis MUST rozróżniać co najmniej: wołających sięgających po powierzchnię narzędziową
i wołających sięgających po kontrakt REST. Wołający uprawniony do jednej z nich MUST NOT
być tym samym uprawniony do drugiej.

Każda para „tożsamość — powierzchnia, do której nie ma prawa" MUST mieć test odmowy.
Zapis bez testu trybu awarii jest listą, o której nikt nie wie, czy działa.

#### Scenario: Wołający narzędzi sięga po zapis

- **WHEN** wołający uprawniony wyłącznie do powierzchni narzędziowej wysyła żądanie
  rozpoczynające zbieranie pary albo kasujące jej dane
- **THEN** archiwum MUST odmówić
- **AND** MUST NOT wykonać żądania

#### Scenario: Wołający REST sięga po narzędzia

- **WHEN** wołający uprawniony wyłącznie do kontraktu REST wysyła żądanie pod adres
  powierzchni narzędziowej
- **THEN** archiwum MUST odmówić

#### Scenario: Wołający uprawniony

- **WHEN** wołający wysyła żądanie do powierzchni, do której zapis daje mu prawo
- **THEN** żądanie przechodzi

#### Scenario: Tożsamość nieznana zapisowi

- **WHEN** żądanie niesie tożsamość, której zapis nie wymienia
- **THEN** archiwum MUST odmówić, zamiast potraktować ją jak uprawnioną

### Requirement: Zdrowie modułu da się sprawdzić bez sesji MCP i bez tożsamości

Archiwum MUST odpowiadać na sondę zdrowia po drodze niewymagającej nawiązania sesji MCP,
wywołania narzędzia ani niesienia tożsamości wołającego. Platforma, na której moduł stoi,
restartuje kontener na podstawie tej odpowiedzi, nie zna protokołu MCP i nie ma tożsamości
do przedstawienia.

Droga wyjęta spod wymogu tożsamości MUST być wskazana wprost i MUST NOT obejmować żadnej
trasy niosącej dane ani zmieniającej stan.

#### Scenario: Sonda bez sesji

- **WHEN** platforma odpytuje sondę zdrowia
- **THEN** archiwum MUST odpowiedzieć bez nawiązywania sesji MCP i bez tożsamości

#### Scenario: Trasa z danymi nie jest wyjęta spod wymogu

- **WHEN** do zapisu tras wyjętych spod wymogu tożsamości trafia trasa niosąca dane
- **THEN** MUST to wywrócić testy modułu
