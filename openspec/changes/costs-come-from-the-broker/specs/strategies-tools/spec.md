## MODIFIED Requirements

### Requirement: Agent nie podaje kosztów

`run_backtest` MUST NOT przyjmować liczb kosztów jako argumentu. Koszty MUST pochodzić z profilu instrumentu, który
pakiet w razie potrzeby sam pobiera od brokera (`strategies-backtest`). Narzędzie MUST przyjmować wybór „bez kosztów”,
a jego opis MUST mówić, że ten wybór służy tylko wtedy, gdy operator wprost o niego prosi, i że wynik pomija koszty.
Agent MUST NOT mieć narzędzia, które ustawia albo zmienia wartości profilu kosztów.

#### Scenario: Instrument bez profilu kosztów

- **WHEN** agent prosi o backtest strategii na instrumencie, który nie ma profilu kosztów
- **THEN** narzędzie MUST zakolejkować uruchomienie z profilem pobranym od brokera
- **AND** odpowiedź MUST mówić, że koszty pochodzą od brokera, i podawać ich wartości

#### Scenario: Backtest bez kosztów na prośbę operatora

- **WHEN** operator prosi agenta o backtest bez kosztów
- **THEN** narzędzie MUST zakolejkować uruchomienie z wyborem „bez kosztów”, oznaczone tak w raporcie
