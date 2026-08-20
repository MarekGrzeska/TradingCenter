## ADDED Requirements

### Requirement: Operator zatrzymuje odpowiedź z panelu

Panel MUST dawać sposób zatrzymania odpowiedzi, dopóki ona trwa, i MUST go pokazywać w tym
samym miejscu, w którym w czasie tury i tak nie da się wysłać następnego pytania. Operator,
który po dwóch zdaniach widzi, że agent odpowiada nie na to pytanie, MUST mieć hamulec
bliżej niż zamknięcie panelu.

Zatrzymanie MUST być żądaniem skierowanym do modułu, a nie samym porzuceniem strumienia
przez terminal: porzucone łącze zostawia turę biegnącą dalej, a operator, który kliknął
zatrzymanie, MUST dostać turę zakończoną.

Po zatrzymaniu panel MUST wrócić do stanu, w którym można pisać dalej, a to, co dotarło,
MUST zostać na ekranie. Zatrzymanie MUST NOT wymagać przeładowania terminala ani otwarcia
rozmowy na nowo.

Zatrzymanie, którego moduł nie przyjął, MUST być powiedziane wprost, a panel MUST NOT
pokazać tury jako zatrzymanej, dopóki moduł tego nie potwierdzi — odpowiedź, która płynie
dalej pod napisem „zatrzymano", jest gorsza niż brak przycisku.

#### Scenario: Operator zatrzymuje trwającą odpowiedź

- **WHEN** odpowiedź agenta płynie, a operator wybiera zatrzymanie
- **THEN** panel żąda zatrzymania od modułu
- **AND** po zakończeniu tury pokazuje to, co dotarło, jako odpowiedź zatrzymaną
- **AND** pozwala napisać następną wiadomość

#### Scenario: Nie ma czego zatrzymywać

- **WHEN** żadna tura nie trwa
- **THEN** panel MUST NOT pokazywać sposobu zatrzymania

#### Scenario: Moduł nie przyjął zatrzymania

- **WHEN** żądanie zatrzymania kończy się błędem
- **THEN** panel mówi to wprost
- **AND** MUST NOT oznaczyć odpowiedzi jako zatrzymanej

#### Scenario: Powrót do zatrzymanej rozmowy

- **WHEN** operator otwiera sesję, w której tura została zatrzymana
- **THEN** panel pokazuje tę wypowiedź jako zatrzymaną, tak samo jak pokazywał ją w chwili
  zatrzymania

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
Odpowiedź niepełna MUST być oznaczona jako niepełna, a nie pokazana jako całość. Odpowiedź
zatrzymana przez operatora MUST być odróżnialna od obu: nie jest błędem i nie jest urwana
sama z siebie — skończyła się, bo ktoś tak powiedział.

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

#### Scenario: Odpowiedź zatrzymana nie jest błędem

- **WHEN** tura kończy się zatrzymaniem na żądanie operatora
- **THEN** panel oznacza tę wypowiedź jako zatrzymaną
- **AND** MUST NOT pokazać jej jako błędu ani jako odpowiedzi zakończonej normalnie

#### Scenario: Moduł agenta jest nieosiągalny

- **WHEN** moduł agenta nie odpowiada
- **THEN** panel mówi to wprost
- **AND** MUST NOT pokazywać wypowiedzi agenta, która nie powstała
