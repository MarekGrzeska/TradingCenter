## MODIFIED Requirements

### Requirement: Wykres podaje wartości spod kursora

Wykres MUST pokazywać otwarcie, maksimum, minimum, zamknięcie i czas świecy wskazywanej kursorem.

Wolumen MUST NOT być pokazywany. Provider podaje dla kontraktów CFD wolumen własnego instrumentu,
a nie rynku bazowego, więc jest to liczba, której nie da się uczciwie przeczytać: pokazana obok
ceny wygląda na wolumen rynkowy i tym nie jest.

#### Scenario: Kursor nad świecą

- **WHEN** operator najeżdża na świecę
- **THEN** wykres pokazuje jej otwarcie, maksimum, minimum, zamknięcie i czas

#### Scenario: Świeca z wolumenem od źródła

- **WHEN** świeca pochodzi ze źródła, które wolumen niesie
- **THEN** wykres i tak go nie pokazuje

## REMOVED Requirements

### Requirement: Świeca w budowie jest oznaczona na ekranie

**Reason**: To, że ostatnia świeca jeszcze się nie zamknęła, widać na wykresie — świeca zmienia się
na oczach patrzącego. Osobna etykieta mówiła to, co i tak widać, i zajmowała miejsce w nagłówku obok
rzeczy, których nie widać: stanu strumienia i dociągania starszej historii.

**Migration**: Informacja o świecy w budowie zostaje w danych i w kontrakcie
(`terminal-market-data`, „Świeca w budowie jest oznaczona jako niepewna"; `market-data-api`,
„Świeca w budowie jest oznaczona") — znika wyłącznie jej rysowanie w nagłówku wykresu.
