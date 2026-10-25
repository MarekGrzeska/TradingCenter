## MODIFIED Requirements

### Requirement: Porównanie tylko porównywalnych uruchomień

`compare_runs` MUST przyjmować od dwóch do pięciu zakończonych uruchomień i MUST zestawiać ich metryki tylko wtedy, gdy
mają ten sam zakres, ten sam model kosztów, ten sam wymagany depozyt instrumentu (także jego brak) i tę samą wersję
silnika. Gdy którakolwiek z tych rzeczy się różni, narzędzie MUST odmówić i MUST nazwać, co się różni i w którym
uruchomieniu. Uruchomienie niezakończone MUST dawać odmowę z jego stanem. Zestawienie MUST NOT wskazywać lepszego
uruchomienia ani porównywać metryk z progami.

#### Scenario: Różne koszty

- **WHEN** agent porównuje dwa uruchomienia, które różnią się spreadem
- **THEN** narzędzie MUST odmówić, a odmowa MUST nazywać różnicę w kosztach

#### Scenario: Porównywalne uruchomienia

- **WHEN** agent porównuje dwa zakończone uruchomienia o tym samym zakresie, kosztach i wersji silnika
- **THEN** odpowiedź MUST zestawiać ich metryki obok siebie, bez oceny, które jest lepsze

#### Scenario: Różny depozyt

- **WHEN** agent porównuje dwa uruchomienia strategii z `margin_fraction`, liczone z depozytem 0,05 i 0,10
- **THEN** narzędzie MUST odmówić, a odmowa MUST nazywać oba depozyty
