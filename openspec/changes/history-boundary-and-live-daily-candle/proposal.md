## Why

Dwa błędy potwierdzone na produkcji, oba sprowadzają się do tego samego: moduł zapisuje
jako trwały fakt coś, czego nie zmierzył.

Para US100 zebrana od 1 stycznia 2026 nie daje się pogłębić. Prośba o historię od
1 stycznia 2024 (zlecenie #4) skończyła się zerem świec na wszystkich siedmiu
rozdzielczościach, ze statusem „ukończone" — bo w pokryciu siedzi granica historii
providera ustawiona na 2026-01-01, której nic nigdy nie zdejmuje. Odzyskanie pary wymaga
dziś skasowania jej razem ze wszystkimi świecami.

Na `DAY` i `WEEK` wykres nie pokazuje bieżącej, niezamkniętej świecy — czasem przez dobę,
czasem przez tydzień — a po jedynym zdarzeniu zamknięcia w okresie zaczyna pokazywać
świecę **błędną**: właśnie zamkniętą, rozciąganą cenami z następnego okresu.

Trzecia rzecz wyszła przy badaniu drugiej i jest jej drugą połową. Odczyt historii nigdy
nie mówi, które świece są zamknięte — DTO gatewaya nie ma o tym pola, a `market-data`
stempluje każdą świecę z REST jako zamkniętą. Reguła „archiwum nie utrwala świecy
w budowie" jest więc spełniona trywialnie: świeca z historii nigdy nie jest tak oznaczona.
Bieżący, niedomknięty okres trafia do archiwum jako fakt. Gorzej, że sam się tam
zabetonowuje — uzupełnianie liczy zaległość od najnowszej posiadanej świecy, więc świeca
bieżąca zatrzymuje kolejne żądania i zostaje z częściowymi wartościami aż do
przeterminowania o dwa okresy. Dla `DAY` to dwie doby. To jest ta świeca, którą operator
widzi narysowaną i nieruchomą.

## What Changes

- Stwierdzenie „historia instrumentu się skończyła" wymaga potwierdzenia. Pusta odpowiedź
  providera na okno, z którego nie zebrano jeszcze ani jednej świecy, przestaje być
  dowodem końca historii — provider zwraca `error.prices.not-found` również z innych
  powodów, a konsument zapisuje to stwierdzenie jako trwałą granicę.
- Granica trafia tam, gdzie dane faktycznie się skończyły — na najstarszą odebraną świecę
  — a nie na żądaną krawędź okna. Dziś kawałek proszący o okno sięgające 2024 roku
  i dostający dane tylko do 2026 zapisuje granicę na 2024… albo na krawędzi, której nikt
  nie sprawdził.
- **Jawna prośba o dane starsze niż zapisana granica unieważnia tę granicę.** Zakres jest
  planowany w całości, a zlecenie odkrywa krawędź na nowo. Bez nowego endpointu i bez
  nowej rzeczy do zrozumienia dla operatora: pogłębienie po prostu działa. To także
  ścieżka odzyskania US100 na produkcji — ponowna prośba od 2024 wystarczy.
- Zlecenie odnotowuje datę, od której faktycznie zaplanowało, obok tej, o którą
  poproszono. Wymaganie już tego żąda; implementacja wyrzuca tę wartość.
- Świeca w budowie na `DAY` i `WEEK` jest zasiewana z odczytu od providera, bo tylko on
  zna granicę sesji. Kwotowanie z okresu późniejszego niż zasiana świeca MUST NOT
  rozciągać świecy zamkniętej — granica jest odczytywana na nowo.
- Odczyt historii mówi, która świeca jest jeszcze w budowie. Dla rozdzielczości o stałej
  długości okresu wynika to z arytmetyki; dla `DAY` i `WEEK` — ze stanu rynku, który
  gateway już zna, bo bez zgadywania granicy sesji nie da się tego powiedzieć inaczej.
  Archiwum przestaje utrwalać bieżący okres, a reguła, która tego zabrania, wreszcie ma
  na czym zadziałać.

Te dwie ostatnie rzeczy są jedną: świeca w budowie ma płynąć do konsumenta strumieniem,
a zamknięta archiwum. Dziś archiwum trzyma jedną i drugą, a strumień nie daje żadnej —
i dlatego odjęcie świecy bieżącej z archiwum wolno zrobić dopiero razem z naprawą
strumienia, nie wcześniej.

Bez zmian pozostaje to, co dziś działa: granica nadal powstaje i nadal pozwala pominąć
w hurcie starsze kawałki tego samego zlecenia, bo tam jej wartość jest realna. Zmienia się
wyłącznie to, jak jest ustalana i jak długo obowiązuje.

## Capabilities

### New Capabilities

Brak — wszystkie cztery zdolności już istnieją.

### Modified Capabilities

- `capital-market-data`: koniec historii MUST być stwierdzony wyłącznie na podstawie okna,
  z którego moduł zdążył już coś zebrać; pusta odpowiedź na okno bez ani jednej świecy nie
  jest dowodem. Dodatkowo: odczyt historii MUST powiedzieć, która świeca należy do okresu
  jeszcze trwającego — dziś nie mówi tego wcale.
- `capital-streaming`: skąd bierze się pierwsza znana świeca dla rozdzielczości bez stałej
  granicy okresu, i co się dzieje, gdy okres się przetoczy, zanim provider zamknie
  poprzedni.
- `market-data-store`: granica pokrycia zapisywana w miejscu, gdzie dane faktycznie się
  skończyły; granica przestaje obowiązywać, gdy ktoś jawnie prosi o dane starsze od niej.
  Osobno: zakaz utrwalania świecy w budowie obejmuje także świecę z odczytu historii, nie
  tylko tę ze strumienia.
- `market-data-jobs`: przycinanie daty OD dotyczy wyłącznie granicy potwierdzonej
  i nieunieważnionej; wycena i wykonanie MUST liczyć tak samo, mimo że tylko jedno z nich
  zapisuje.

## Impact

**modules/capital-gateway** — `capital_gateway/history.py` (warunek ustawiania
`history_ended`; wyznaczanie świecy w budowie), `capital_gateway/dtos.py` i
`mapping.py` (**kontrakt między modułami**: `Candle` zyskuje pole mówiące, czy okres się
domknął), `capital_gateway/stream/forming.py` i `stream/hub.py` (zasiew i przetoczenie
okresu dla `DAY`/`WEEK`; pokój zyskuje dostęp do odczytu historii, którego dziś nie ma).

**modules/market-data** — `market_data/coverage.py` (zdejmowanie flagi, zapis granicy),
`market_data/jobs/plan.py` (reguła przycinania), `market_data/jobs/runner.py` (punkt
zapisu granicy), `market_data/routers/pairs.py` (zachowanie `effective_from`),
`market_data/gateway/history.py` (czytanie pola zamiast wpisywania stałej).
`market_data/contract.py` **bez zmian** — `CandleOut` nadal nie niesie tego pola, bo
odczyt zakresu nadal zwraca wyłącznie świece zamknięte; różnica jest taka, że wreszcie to
prawda. Bez `pnpm contract:generate` i bez ścieżki mapowania w terminalu.

**modules/terminal** — bez zmian w kodzie wykresu. `useBarFeed.ts` i `Chart.tsx` obsługują
świecę w budowie poprawnie; brakowało wyłącznie wiadomości od gatewaya.

**Produkcja** — po wdrożeniu US100 odzyskuje się ponowną prośbą od 2024, bez kasowania
pary i bez ręcznego zapisu do bazy. Koszt ponownego odkrycia granicy to jeden do dwóch
żądań na parę, bo kawałki idą od najnowszego i pierwszy trafiony na krawędź domyka resztę.
