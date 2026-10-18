## Why

Dziś adresat jest parą „bot + czat” i należy do jednego bota (`destinations.name` jest unikalna, `bot_id` jedna).
Operator chce jednego odbiorcę (siebie) i kilka botów, z których każdy niesie co innego — jeden posty, drugi filmy,
trzeci raporty zespołów — i żeby to reguła wybierała bota. Dziś da się to tylko przez trzech „adresatów” o trzech
nazwach dla tej samej osoby.

## What Changes

- **Adresat to nazwa odbiorcy, a nie para z botem.** Ta sama nazwa MAY być związana przez kilka botów; każde
  wiązanie (nazwa, bot) ma własny czat, stan i tapnięcie `/start`, bo Telegram nie pozwala botowi napisać pierwszemu.
  Unikalność przechodzi z nazwy na parę (nazwa, bot).
- **Wysłanie i usunięcie wskazują parę.** `POST /messages` przyjmuje adresata i nazwę bota; bot MAY zostać pominięty
  tylko wtedy, gdy adresat ma dokładnie jednego. Usunięcie adresata usuwa wiązanie przez jednego bota, nie wszystkie.
- **Reguła alertów nazywa adresata i bota.** Nowe pole reguły `bot`. Puste znaczy „jedyny bot tego adresata” — tak
  działają wszystkie reguły sprzed zmiany, bez przepisywania. Gdy adresat zyska drugiego bota, reguła z pustym botem
  przestaje być jednoznaczna: jest oznaczona jako wadliwa i nie doręcza, dopóki operator nie wskaże bota.
- **Terminal.** Zakładka Telegram grupuje wiązania według adresata i pozwala dodać tego samego adresata przez
  kolejnego bota. Formularz reguły ma obok „Kogo powiadomić” pole „Którym botem”, z samymi botami, które docierają
  do wybranego adresata.
- **Bez zmiany:** konwersja i dotychczasowe reguły. Migracja bazy `telegram` zmienia tylko unikalność
  (nazwa → para nazwa i bot); baza `alerts` dostaje jedną nullowalną kolumnę.
- **BREAKING (wewnątrz procesu):** kontrakt `POST /telegram/messages` i `DELETE /telegram/destinations/{name}` dostają
  parametr bota; jedynym wołającym wiadomości jest pakiet `alerts`, jedynym wołającym usunięcie — terminal. Kontrakt
  terminala (`contract.telegram`, `contract.alerts`) jest regenerowany.

**Poza zakresem:** kopiowanie czatu między botami (wymagałoby tego samego tapnięcia i tak), grupy adresatów („wyślij
do wszystkich moich botów”), wiele osób w jednym adresacie, zmiana bota reguły z poziomu rozmowy.

## Capabilities

### New Capabilities
Brak: zmiana nie wprowadza nowej zdolności, rozszerza istniejące.

### Modified Capabilities
- `telegram-gateway-destinations`: adresat jest nazwą, którą MAY wiązać kilka botów; stan i blokada są per wiązanie;
  usunięcie rusza jedno wiązanie.
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

`design.md` jest zapisany: zmiana ma realny wybór (jedna tabela z parą kontra osobne tabele odbiorców) i regułę
zgodności wstecznej. `review.md` zostanie napisany po zadaniach: zmiana dotyka drogi doręczenia i usuwania.
