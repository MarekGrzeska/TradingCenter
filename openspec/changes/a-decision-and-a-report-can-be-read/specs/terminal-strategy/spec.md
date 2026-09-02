## ADDED Requirements

### Requirement: Decyzję da się przeczytać do tego, na czym stanęła

Szczegóły decyzji MUST pokazywać powód, a dla decyzji o wejściu także kierunek, poziomy
i stosunek zysku do ryzyka. Dla każdej decyzji MUST być dostępne odczytanie faktów, na
których stanęła, oraz wersji parametrów, którą została policzona.

Decyzja bez tego jest anegdotą. Spór „czemu system wszedł" rozstrzyga się odczytaniem tego,
co system wtedy widział, a nie tego, co widać dzisiaj.

#### Scenario: Operator sprawdza setup

- **WHEN** operator otwiera decyzję o wejściu
- **THEN** widzi kierunek, wejście, obronę, cel i stosunek zysku do ryzyka
- **AND** ma dostęp do odczytów, na których ta decyzja stanęła

### Requirement: Raporty backtestu są czytane, a nie uruchamiane

Zachowane raporty backtestu MUST być czytelne z ekranu wraz z modelem kosztów, wersją
parametrów i zakresem danych, na których powstały. Ekran MUST NOT oferować uruchomienia
przebiegu.

Przebieg po latach świec to minuty pracy i trzymanie żądania przez cały ten czas; jest
komendą właśnie po to, żeby długi przebieg nie był czymś, co da się odpalić przypadkiem.
Raport bez modelu kosztów nie jest wynikiem, więc ekran pokazujący raport bez nich
pokazywałby liczbę, nie odpowiedź.

#### Scenario: Operator czyta raport

- **WHEN** operator otwiera zachowany raport backtestu
- **THEN** widzi metryki wraz z modelem kosztów, wersją parametrów i zakresem danych

#### Scenario: Operator szuka przycisku uruchamiającego przebieg

- **WHEN** operator ogląda listę raportów
- **THEN** nie ma na ekranie akcji uruchamiającej backtest
