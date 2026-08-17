## Purpose

Jak moduł jest osiągalny i przez kogo: jeden transport sieciowy, jeden nazwany wołający, i
jedno wejście, które odpowiada bez poświadczenia — po to, żeby wdrożenie miało czego dotknąć.

## ADDED Requirements

### Requirement: Jeden transport, wybrany bez pytania wołającego

Moduł MUST udostępniać narzędzia wyłącznie transportem sieciowym. MUST NOT udostępniać
wariantu uruchamianego jako proces potomny klienta.

Ten moduł nie jest narzędziem, które operator podłącza do swojego klienta na biurku — jego
wołającym jest inna usługa, a każdy wariant transportu jest drugą drogą, którą trzeba osobno
uwierzytelnić i osobno przetestować. `trading-mcp` podjął tę samą decyzję z tego samego powodu.

#### Scenario: Moduł startuje

- **WHEN** moduł jest uruchamiany
- **THEN** wystawia narzędzia transportem sieciowym na skonfigurowanym porcie
- **AND** nie ma trybu, w którym wystawia je inaczej

### Requirement: Wołający jest jeden i jest nazwany

Dostęp do narzędzi MUST być ograniczony do wskazanych tożsamości wołających. Tożsamość
niewymieniona MUST zostać odrzucona, nawet jeśli pochodzi z tego samego katalogu tożsamości.

Ten zestaw zakłada zespoły i uruchamia przebiegi w imieniu operatora. Lista wołających jest
miejscem, w którym widać, kto to potrafi — i musi być wyliczeniem, a nie skutkiem ubocznym
posiadania jakiegokolwiek tokenu.

#### Scenario: Wołający spoza listy

- **WHEN** narzędzie jest wołane przez tożsamość spoza listy dopuszczonych
- **THEN** wywołanie MUST zostać odrzucone
- **AND** MUST NOT dojść do modułu `teams`

#### Scenario: Wołający z listy

- **WHEN** narzędzie jest wołane przez `agent`
- **THEN** wywołanie jest obsłużone

### Requirement: Jedno wejście odpowiada bez poświadczenia

Moduł MUST udostępniać jedno wejście odpowiadające bez poświadczenia, przeznaczone wyłącznie
do sprawdzenia, że proces żyje. MUST NOT ono ujawniać niczego o katalogu zespołów, o
operatorach ani o stanie modułu `teams`.

Wdrożenie, które umie zapytać wyłącznie warstwę sterującą platformy, dowiaduje się, że
serwowany jest właściwy obraz — nie że proces w środku wstał. Ta różnica raz już przykryła
kontener w pętli restartów zgłoszeniem „Running".

#### Scenario: Sprawdzenie po wdrożeniu

- **WHEN** wdrożenie pyta o to wejście
- **THEN** odpowiedź potwierdza, że proces odpowiada
- **AND** nie niesie żadnej informacji o zespołach ani ich właścicielach

#### Scenario: Każde inne wejście

- **WHEN** żądanie bez poświadczenia trafia na jakiekolwiek inne wejście
- **THEN** MUST zostać odrzucone
