## Purpose

Kiedy post z archiwum jest wart obudzenia operatora, co znaczy „już o tym powiedziano", i co robi
moduł, który nie ma dokąd wysłać.

## ADDED Requirements

### Requirement: Powiadamia post, który przekroczył próg oceny wpływu

Moduł MUST wysłać powiadomienie o poście, którego ocena wpływu osiągnęła skonfigurowany próg, i MUST
NOT wysyłać go o żadnym innym. Próg MUST być ustawieniem.

#### Scenario: Post powyżej progu

- **WHEN** zbiórka zapisuje post z oceną wpływu nie niższą niż próg
- **THEN** moduł MUST wysłać o nim powiadomienie

#### Scenario: Post poniżej progu

- **WHEN** zbiórka zapisuje post z oceną niższą niż próg
- **THEN** moduł MUST NOT wysłać o nim niczego

### Requirement: Post bez odczytu modelu nie powiadamia

Post, dla którego nie ma jeszcze oceny wpływu — bo model nie jest skonfigurowany albo odczyt się nie
udał — MUST NOT wywoływać powiadomienia.

Brak oceny nie jest oceną niską ani wysoką; wysłanie „na wszelki wypadek" zamieniłoby próg w jego
przeciwieństwo w dokładnie tym stanie, w którym moduł wie najmniej.

#### Scenario: Model nieskonfigurowany

- **WHEN** moduł zbiera posty bez skonfigurowanego modelu
- **THEN** MUST NOT wysłać żadnego powiadomienia

### Requirement: Znacznik jest stawiany po udanej wysyłce i jest mechanizmem ponowienia

Moduł MUST zapisać przy poście znacznik „już powiedziane" dopiero po odpowiedzi bramy oznaczającej
powodzenie. Post ze znacznikiem MUST NOT być powiadamiany ponownie.

Brama nie pamięta wiadomości, więc to jest jedyne miejsce, w którym deduplikacja może stać. Nieudana
wysyłka nie stawia znacznika, więc następny przebieg zbiórki próbuje jeszcze raz — i to jest cały
mechanizm ponowienia, jaki ten system ma. Cena jest realna: między próbami mija pełny cykl zbiórki,
a wysyłka, która się udała i której znacznika nie udało się zapisać, powtórzy powiadomienie.

#### Scenario: Wysyłka się nie udała

- **WHEN** brama odmawia wysłania powiadomienia o poście
- **THEN** moduł MUST NOT zapisać znacznika, a następny przebieg MUST spróbować ponownie

#### Scenario: Post już zapowiedziany

- **WHEN** przebieg zbiórki napotyka post ze znacznikiem
- **THEN** MUST NOT wysyłać o nim niczego

### Requirement: Brak bramy jest stanem wspieranym

Moduł MUST zbierać i wzbogacać normalnie, gdy adres bramy nie jest ustawiony. MUST NOT odmawiać
startu, MUST NOT przerywać zbiórki i MUST powiedzieć przez własną trasę stanu, że nie powiadamia.

#### Scenario: Brama nieskonfigurowana

- **WHEN** adres bramy nie jest ustawiony, a zbiórka napotyka post powyżej progu
- **THEN** moduł MUST zapisać post normalnie i MUST NOT potraktować braku bramy jako błędu
