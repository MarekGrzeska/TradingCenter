## MODIFIED Requirements

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
