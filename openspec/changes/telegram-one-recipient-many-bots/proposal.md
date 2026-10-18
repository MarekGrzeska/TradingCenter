## Why

Dziś adresat jest parą „bot + czat” i należy do jednego bota (`destinations.name` jest unikalna, `bot_id` jedna).
Operator chce jednego odbiorcę (siebie) i kilka botów, z których każdy niesie co innego — jeden posty, drugi filmy,
trzeci raporty zespołów — i żeby to reguła wybierała bota. Dziś da się to tylko przez trzech „adresatów” o trzech
nazwach dla tej samej osoby.

## What Changes

- **Adresat jest własną encją.** Nowa tabela `recipients` (nazwa unikalna); dotychczasowy wiersz `destinations` staje
  się **wiązaniem** adresata z botem i zachowuje czat, stan, blokadę i tapnięcie `/start`, bo Telegram nie pozwala
  botowi napisać pierwszemu. Adresat MAY mieć kilka wiązań, po jednym na bota; para (adresat, bot) jest unikalna.
- **Kontrakt bramy: dwa zasoby.** `/recipients` (adresat z listą wiązań), `/recipients/{name}/bots` (dodanie i
  usunięcie jednego wiązania) i `POST /messages` z `{recipient, bot?}`; bot MAY zostać pominięty tylko wtedy, gdy adresat
  ma dokładnie jedno wiązanie. Trasy `/destinations` znikają.
- **Reguła alertów nazywa adresata i bota.** Nowe pole reguły `bot`. Puste znaczy „jedyne wiązanie tego adresata” — tak
  działają wszystkie reguły sprzed zmiany, bez przepisywania. Gdy adresat zyska drugiego bota, reguła z pustym botem
  przestaje być jednoznaczna: jest oznaczona jako wadliwa i nie doręcza, dopóki operator nie wskaże bota.
- **Terminal.** Zakładka Telegram pokazuje adresatów z ich wiązaniami i pozwala dodać kolejnego bota do adresata.
  Formularz reguły ma obok „Kogo powiadomić” pole „Którym botem”, z samymi botami wybranego adresata.
- **Migracje addytywne.** Baza `telegram`: tabela `recipients`, `destinations.recipient_id` z uzupełnieniem po nazwie,
  zdjęcie unikalności `name`; kolumna `name` zostaje do następnej zmiany (kontrakt rozszerz–zawęź), żeby wycofanie
  obrazu nie było ślepą uliczką. Baza `alerts`: jedna nullowalna kolumna `bot`.
- **BREAKING (wewnątrz procesu):** trasy `/destinations` zastąpione; jedynymi wołającymi są terminal i pakiet `alerts`,
  oba w tym repozytorium. Kontrakty terminala (`contract.telegram`, `contract.alerts`) są regenerowane.

**Poza zakresem:** kopiowanie czatu między botami (wymagałoby tego samego tapnięcia i tak), grupy adresatów („wyślij
do wszystkich moich botów”), wiele osób w jednym adresacie, zmiana bota reguły z poziomu rozmowy.

## Capabilities

### New Capabilities
Brak: zmiana nie wprowadza nowej zdolności, rozszerza istniejące.

### Modified Capabilities
- `telegram-gateway-destinations`: adresat jest encją z wiązaniami przez kilka botów; stan i blokada są per wiązanie;
  usunięcie adresata i usunięcie wiązania to dwa ruchy.
- `telegram-gateway-delivery`: wiadomość adresuje się nazwą adresata i botem; bot MAY zostać pominięty tylko przy
  jedynym wiązaniu.
- `alerts-rules`: reguła nazywa też bota; pusty bot to „jedyny”, a dwuznaczność jest wadą reguły, nie zgadywaniem.
- `terminal-telegram`: zakładka grupuje wiązania według adresata i dodaje tego samego adresata przez kolejnego bota.
- `terminal-alerts`: formularz reguły wybiera adresata i bota osobno.

(Wymagania `alerts-rules`, `terminal-alerts` i `terminal-telegram` powstają przy archiwizacji `alerts-package`,
a `terminal-telegram` także `telegram-bots-from-the-terminal`. Ta zmiana MUSI być archiwizowana po nich; do tego czasu
jej delty dla tych trzech zdolności są `ADDED`, nie `MODIFIED`.)

## Impact

- `modules/workbench`: `telegram_gateway` (indeks, `store`, `binding`, `sending`, trasy `/destinations` i `/messages`,
  `contract.py`), `alerts` (`gateway`, `known`, `validation`, `delivery`, `store`, `contract`, `rules`), migracje
  `telegram` i `alerts`.
- `modules/terminal`: zakładki Telegram i Alerty, wygenerowane kontrakty `telegram` i `alerts`.
- `modules/pocket`: bez zmian (nie czyta ani adresatów, ani reguł).
- Wdrożenie: bez kroków operatora. Obie migracje są addytywne i działają pod własnymi blokadami.

`design.md` jest zapisany: zmiana ma realny wybór (osobne tabele wybrane przez operatora, jedna tabela z parą jako
alternatywa) i regułę zgodności wstecznej. `review.md` zostanie napisany po zadaniach: zmiana dotyka drogi doręczenia i usuwania.
