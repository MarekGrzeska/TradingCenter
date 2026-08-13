## MODIFIED Requirements

### Requirement: Widać, że odpowiedź powstaje

Panel MUST pokazywać odpowiedź w miarę, jak przychodzi, a przed pierwszym jej fragmentem
MUST pokazywać, że wypowiedź została przyjęta i czekanie trwa. Operator MUST NOT stać przed
niezmienionym ekranem, na którym równie dobrze mogło nic się nie wysłać.

Panel MUST pokazywać wywołania narzędzi, którymi agent doszedł do odpowiedzi — w trakcie
tury, w chwili gdy przychodzą, i po powrocie do sesji, z transkryptu. Wywołanie MUST stać w
transkrypcie tam, gdzie padło, a nie w osobnym oknie diagnostycznym: to część drogi do
odpowiedzi, a nie zapis techniczny obok niej.

Wpis wywołania MUST nieść nazwę narzędzia i to, jak się skończyło, w postaci zwiniętej, i
MUST dać się rozwinąć do argumentów oraz treści wyniku albo powodu odmowy. Zwinięta postać
jest domyślna: tura z ośmioma wywołaniami rozwiniętymi zasłoniłaby rozmowę, o którą
operatorowi chodzi.

Wywołanie odmówione MUST być widoczne jako odmowa, odróżnialne od wywołania udanego i od
wywołania, którego serwer narzędzi nie przyjął. Odmowa narzędzia MUST NOT być pokazana jako
błąd całej odpowiedzi.

Zerwanie strumienia MUST być widoczne jako błąd, odróżnialny od odpowiedzi zakończonej.
Odpowiedź niepełna MUST być oznaczona jako niepełna, a nie pokazana jako całość.

#### Scenario: Odpowiedź w trakcie

- **WHEN** operator wysyła wiadomość
- **THEN** panel pokazuje, że odpowiedź powstaje, zanim przyjdzie jej pierwszy fragment
- **AND** dopisuje kolejne fragmenty w miarę, jak przychodzą

#### Scenario: Narzędzie w trakcie tury

- **WHEN** agent wywołuje narzędzie w trakcie powstawania odpowiedzi
- **THEN** panel pokazuje wpis tego wywołania, zanim przyjdzie domknięcie odpowiedzi
- **AND** wpis niesie nazwę narzędzia i to, jak się skończyło

#### Scenario: Operator rozwija wywołanie

- **WHEN** operator rozwija wpis wywołania
- **THEN** widzi argumenty, którymi narzędzie wywołano, i treść wyniku albo powód odmowy

#### Scenario: Narzędzie odmawia

- **WHEN** narzędzie odmawia odpowiedzi
- **THEN** panel pokazuje wpis oznaczony jako odmowa, z jej powodem po rozwinięciu
- **AND** odpowiedź agenta MUST NOT zostać oznaczona jako niepełna wyłącznie z tego powodu

#### Scenario: Powrót do zakończonej rozmowy

- **WHEN** operator otwiera sesję, w której agent sięgał po narzędzia
- **THEN** panel pokazuje te same wywołania, które pokazywał w trakcie tury

#### Scenario: Strumień pęka

- **WHEN** strumień zostaje zerwany przed zakończeniem odpowiedzi
- **THEN** panel oznacza odpowiedź jako niepełną i podaje, że wystąpił błąd
- **AND** to, co dotarło, zostaje na ekranie

#### Scenario: Moduł agenta jest nieosiągalny

- **WHEN** moduł agenta nie odpowiada
- **THEN** panel mówi to wprost
- **AND** MUST NOT pokazywać wypowiedzi agenta, która nie powstała
