# telegram-gateway-delivery Specification

## Purpose
Czym jest wysłanie wiadomości przez tę bramę: co wywołujący dostaje w odpowiedzi, które ograniczenia
Telegrama są częścią kontraktu, a nie szczegółem implementacji, i czego moduł świadomie nie pamięta.
## Requirements
### Requirement: Wysłanie jest jednym aktem i nie zostawia śladu

Moduł MUST wysłać wiadomość w trakcie obsługi żądania i MUST zwrócić wywołującemu wynik, jaki dał
Telegram. Moduł MUST NOT kolejkować wiadomości, MUST NOT ponawiać jej samodzielnie i MUST NOT
przechowywać treści po zakończeniu żądania.

To jest wybór, nie uproszczenie, i ma nazwaną cenę: skoro brama nie pamięta, to deduplikacja i
ponowienie należą do wywołującego — `social-data-alerts` mówi, jak je robi.

#### Scenario: Wiadomość dochodzi

- **WHEN** wywołujący prosi o wysłanie treści do znanego adresata
- **THEN** moduł MUST odpowiedzieć powodzeniem niosącym identyfikator wiadomości nadany przez Telegram

#### Scenario: Nie ma czego odczytać

- **WHEN** ktokolwiek pyta bramę, co zostało wysłane
- **THEN** moduł MUST NOT publikować żadnej trasy ani narzędzia, które by na to odpowiedziało

### Requirement: Odmowa Telegrama dociera w całości

Odpowiedź na nieudaną wysyłkę MUST nieść to, co powiedział Telegram, w postaci, z której wywołujący
podejmie decyzję — w szczególności czas oczekiwania przy przekroczeniu limitu i informację, że
adresat zablokował bota. Moduł MUST NOT zastępować tego własnym, ogólnym komunikatem.

Bez tego jedyną informacją wywołującego byłoby „nie udało się", a on ma na tej podstawie zdecydować,
czy stawiać znacznik „już powiedziane".

#### Scenario: Przekroczony limit

- **WHEN** Telegram odrzuca wysyłkę z powodu limitu tempa
- **THEN** odpowiedź MUST nieść podany przez Telegram czas, po którym wolno spróbować ponownie

#### Scenario: Adresat zablokował bota

- **WHEN** Telegram odmawia, bo adresat zablokował bota
- **THEN** odpowiedź MUST odróżniać ten przypadek od awarii i MUST mówić, że adresat wymaga ponownego związania

### Requirement: Wiadomość jest adresowana nazwą

Wywołujący MUST adresować wiadomość nazwą adresata, którą zna z listy, oraz — gdy adresat jest związany przez więcej niż
jednego bota — botem, przez którego ma pójść. Gdy adresat ma dokładnie jedno wiązanie, bot MAY zostać pominięty i
wiadomość MUST pójść przez to wiązanie. Gdy ma kilka, a bota pominięto, moduł MUST odmówić i wymienić boty; MUST NOT
wybierać żadnego z nich. Kontrakt MUST NOT przyjmować celu ani identyfikatora czatu.

Identyfikator czatu jest liczbą, którą każdy wywołujący musiałby skądś mieć i trzymać u siebie. Bot jest częścią decyzji
wywołującego (reguły pakietu alertów), więc jego wymiana ma unieważnić dokładnie to, co go wskazuje, a nie wszystko
naraz ani nic.

#### Scenario: Nieznany adresat

- **WHEN** wywołujący adresuje wiadomość nazwą, której moduł nie zna
- **THEN** moduł MUST odmówić, wskazując nazwę, i MUST NOT wysłać niczego

#### Scenario: Wiadomość z celem

- **WHEN** wywołujący podaje cel zamiast nazwy adresata
- **THEN** moduł MUST odmówić i MUST NOT wysłać niczego

#### Scenario: Wiadomość przez wskazanego bota

- **WHEN** adresat ma dwa wiązania i wywołujący wskazuje jednego z botów
- **THEN** wiadomość MUST pójść tylko przez to wiązanie

#### Scenario: Dwuznaczny adresat

- **WHEN** adresat ma dwa wiązania, a wywołujący nie wskazuje bota
- **THEN** moduł MUST odmówić, wymienić oba boty i MUST NOT wysłać niczego

#### Scenario: Bot, którego adresat nie ma

- **WHEN** wywołujący wskazuje bota, przez którego adresat nie jest związany
- **THEN** moduł MUST odmówić, wskazując bota i adresata, i MUST NOT wysłać niczego

### Requirement: Za długa treść jest odmową, nie ucięciem

Moduł MUST odmówić wysłania treści dłuższej niż przyjmuje Telegram i MUST NOT skracać jej po cichu.

Ucięty alert jest alertem o innej treści — a to jest dokładnie ta klasa pomyłki, której nie widać
w odpowiedzi oznaczającej powodzenie.

#### Scenario: Treść przekracza sufit

- **WHEN** wywołujący prosi o wysłanie treści dłuższej niż dopuszcza Telegram
- **THEN** moduł MUST odmówić, nazywając sufit i długość otrzymanej treści

