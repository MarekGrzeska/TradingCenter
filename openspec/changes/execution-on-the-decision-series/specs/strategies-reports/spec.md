## MODIFIED Requirements

### Requirement: Raport mówi, z czego powstał

Raport MUST zapisywać: identyfikator strategii, rewizję i hash jej treści, użyte parametry, model kosztów,
wymagany depozyt instrumentu, gdy wielkość pozycji od niego zależała, zakres, przeczytaną rozgrzewkę, wersję silnika,
serię wykonania, ziarno oraz dla każdej przeczytanej serii odcisk danych (liczbę punktów, pierwszą i ostatnią chwilę,
hash wartości) i fragmenty zakresu, których archiwum nie potwierdziło.

#### Scenario: Dane zmieniły się między uruchomieniami

- **WHEN** dwa uruchomienia tej samej rewizji z tym samym wkładem dają różne wyniki
- **THEN** odciski danych w obu raportach MUST pokazywać, która seria się różni

#### Scenario: Raport strategii z ułamkiem depozytu

- **WHEN** uruchomienie strategii z `margin_fraction` liczyło wielkość z depozytu 0,05
- **THEN** raport MUST zapisywać depozyt 0,05 wśród tego, z czego powstał

#### Scenario: Seria wykonania w odczycie agenta

- **WHEN** agent czyta przez `read_backtest` uruchomienie strategii bez poziomów na `MINUTE_5`
- **THEN** odczyt MUST podawać serię wykonania `MINUTE_5`
