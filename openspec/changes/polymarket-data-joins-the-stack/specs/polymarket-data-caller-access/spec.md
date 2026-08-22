## Purpose

Kto sięga po którą powierzchnię modułu: trasa narzędziowa dla modeli, REST dla terminala, i
dlaczego samo przepuszczenie przez bramę platformy nie wystarcza, skoro obie stoją w jednej
aplikacji.

## ADDED Requirements

### Requirement: Powierzchnia narzędziowa jest osiągalna po sieci, jedną drogą

Moduł MUST udostępniać zestaw narzędzi klientowi MCP po sieci, pod jednym adresem we własnej
aplikacji. Dodanie narzędzia MUST być widoczne pod tym adresem bez osobnej rejestracji gdziekolwiek
indziej.

#### Scenario: Klient pyta o listę narzędzi

- **WHEN** klient MCP nawiązuje sesję pod adresem powierzchni narzędziowej
- **THEN** dostaje zestaw narzędzi z ich opisami i schematami

#### Scenario: Narzędzie dołożone do zestawu

- **WHEN** do modułu trafia nowe narzędzie
- **THEN** jest widoczne pod tym samym adresem bez osobnej rejestracji

### Requirement: Żądanie z sieci niesie tożsamość wołającego

Moduł MUST wymagać, żeby żądanie po sieci niosło tożsamość wołającego, i MUST odmówić obsługi
żądaniu, które jej nie niesie. Wymóg ten MUST dać się wyłączyć wyłącznie dla pracy lokalnej, a jego
wyłączenie MUST być świadomym ustawieniem, nie wartością domyślną w środowisku zdalnym.

Moduł MUST zapisywać w dzienniku fakt odmowy i tożsamość, dla której wywołanie przeszło — nigdy zaś
treści żądania ani wartości poświadczenia.

#### Scenario: Wołanie bez tożsamości przy włączonym wymogu

- **WHEN** żądanie po sieci nie niesie tożsamości wołającego, a moduł jej wymaga
- **THEN** moduł MUST odmówić obsługi
- **AND** MUST NOT wykonać żadnego narzędzia

#### Scenario: Praca lokalna

- **WHEN** moduł jest uruchomiony lokalnie z wyłączonym wymogiem tożsamości
- **THEN** narzędzia działają, a dziennik odnotowuje wywołanie bez tożsamości jako takie

### Requirement: Tożsamość rozstrzyga, po którą powierzchnię wolno sięgnąć

Sama obecność tożsamości MUST NOT wystarczać do sięgnięcia po dowolną trasę. Moduł MUST trzymać
zapis tego, która tożsamość ma prawo do której powierzchni, i MUST odmówić żądaniu spoza tego
zapisu — nawet gdy żądanie niesie tożsamość, którą platforma uwierzytelniła.

Wymaganie to istnieje, bo brama platformy autoryzuje **aplikację**, nie trasę. Cena pomyłki jest tu
inna niż w archiwum świec i trzeba ją nazwać wprost: wołający uprawniony wyłącznie do narzędzi
zmienia listę obserwacji z definicji, więc to nie zapis go odróżnia — odróżnia go kasowanie
historii i cała reszta kontraktu REST, do której zapis MUST NOT go wpuścić.

Zapis MUST rozróżniać co najmniej wołających sięgających po powierzchnię narzędziową i wołających
sięgających po kontrakt REST. Wołający uprawniony do jednej z nich MUST NOT być tym samym
uprawniony do drugiej. Tożsamość, której zapis nie wymienia, MUST być odrzucona, a nie potraktowana
jak uprawniona.

Każda para „tożsamość — powierzchnia, do której nie ma prawa" MUST mieć test odmowy. Zapis bez
testu trybu awarii jest listą, o której nikt nie wie, czy działa.

#### Scenario: Wołający narzędzi sięga po kontrakt

- **WHEN** wołający uprawniony wyłącznie do powierzchni narzędziowej wysyła żądanie kasujące
  zebraną historię
- **THEN** moduł MUST odmówić
- **AND** MUST NOT wykonać żądania

#### Scenario: Wołający REST sięga po narzędzia

- **WHEN** wołający uprawniony wyłącznie do kontraktu REST wysyła żądanie pod adres powierzchni
  narzędziowej
- **THEN** moduł MUST odmówić

#### Scenario: Tożsamość nieznana zapisowi

- **WHEN** żądanie niesie tożsamość, której zapis nie wymienia
- **THEN** moduł MUST odmówić, zamiast potraktować ją jak uprawnioną

#### Scenario: Zapis pusty w świeżym wdrożeniu

- **WHEN** moduł startuje z pustym zapisem uprawnionych wołających
- **THEN** odmawia każdemu żądaniu z sieci
- **AND** MUST NOT wpuszczać wszystkich z powodu pustej listy

### Requirement: Zdrowie modułu da się sprawdzić bez sesji MCP i bez tożsamości

Moduł MUST odpowiadać na sondę zdrowia po drodze niewymagającej nawiązania sesji MCP, wywołania
narzędzia ani niesienia tożsamości wołającego. Platforma, na której moduł stoi, restartuje kontener
na podstawie tej odpowiedzi, nie zna protokołu MCP i nie ma tożsamości do przedstawienia.

Droga wyjęta spod wymogu tożsamości MUST być wskazana wprost i MUST NOT obejmować żadnej trasy
niosącej dane ani zmieniającej stan.

#### Scenario: Sonda bez sesji

- **WHEN** platforma odpytuje sondę zdrowia
- **THEN** moduł MUST odpowiedzieć bez nawiązywania sesji MCP i bez tożsamości

#### Scenario: Trasa z danymi nie jest wyjęta spod wymogu

- **WHEN** do zapisu tras wyjętych spod wymogu tożsamości trafia trasa niosąca dane
- **THEN** MUST to wywrócić testy modułu
