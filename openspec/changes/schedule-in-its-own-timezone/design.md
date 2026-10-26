## Context

Strefa jest dziś stałą `SCHEDULE_TIMEZONE` w `teams/scheduler/timing.py`, a jej trzech użytkowników — zapis
harmonogramu (pierwsze `next_fire_at`), podgląd najbliższych wyzwoleń i zegar (`_next_fire_and_skipped`) — dostaje
samo wyrażenie cron. Wiersz `schedules` nie ma kolumny strefy.

## Goals / Non-Goals

**Non-Goals:** strefa zespołu albo rewizji; strefa granicy dobowej kosztu; zmiana strefy, w której terminal
pokazuje godziny (zostaje polska, `terminal-shell`).

## Decisions

**Strefa należy do harmonogramu, nie do zespołu.** Zespół może mieć dwa harmonogramy w różnych rytmach (wejście
i wyjście), a strefa jest częścią opisu „kiedy”, tak jak wyrażenie cron. Strefa zespołu wymagałaby nowej
rewizji, żeby przestawić godzinę, i wiązałaby z definicją coś, co do definicji nie należy.

**Dowolna nazwa IANA, sprawdzana przy zapisie, a nie lista dozwolonych.** Walidacja to `ZoneInfo(name)` — ta sama
baza, w której zegar potem liczy, więc nie ma dwóch prawd. Lista w kontrakcie (`Literal[...]`) zmuszałaby do
zmiany kontraktu dla każdego nowego rynku. Krótką listę dostaje dopiero kreator w terminalu, jako wygodę, nie
regułę; harmonogram z inną strefą (zapisany przez rozmowę) kreator pokazuje i zachowuje.

**Kolumna `timezone text NOT NULL DEFAULT 'Europe/Warsaw'`.** Domyślna wartość w bazie robi z migracji operację
bez przepisywania danych: każdy istniejący wiersz czyta się dokładnie tak jak dotąd. `fires_after` dostaje strefę
argumentem; stała zostaje jako wartość domyślna, a nie jako jedyna odpowiedź.

**Godziny w luce lub zakładce zmiany czasu — zachowanie `croniter`, bez własnej reguły.** 2:30 w noc wiosennej
zmiany nie istnieje i jest pomijane (już dziś przetestowane dla Warszawy); dotyczy to każdej strefy tak samo.
Sesje rynków nie leżą w tych godzinach.

## Risks / Trade-offs

- [Lista harmonogramów miesza strefy, a terminal pokazuje godziny po polsku] → wiersz w strefie innej niż polska
  pokazuje jej nazwę obok rytmu („pn–pt 9:35 · America/New_York”), a najbliższe wyzwolenie dalej po polsku — więc
  operator widzi i regułę, i to, kiedy to u niego.
- [Baza stref w obrazie starsza niż zmiana prawa o czasie w jakimś kraju] → `tzdata` jest zależnością Pythona
  aktualizowaną z obrazem; dla NY i Warszawy reguły są stabilne.

## Migration Plan

Migracja teams 0011 dodaje kolumnę z wartością domyślną; uruchamia ją lifespan jak każdą inną. Wycofanie obrazu
zostawia kolumnę, której stary kod nie czyta — harmonogramy nowojorskie wróciłyby wtedy do czytania po polsku,
co jest zachowaniem sprzed zmiany.
