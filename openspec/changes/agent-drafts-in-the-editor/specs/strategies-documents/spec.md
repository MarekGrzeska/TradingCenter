## MODIFIED Requirements

### Requirement: Streszczenie powstaje z samego dokumentu

Dla każdego poprawnego dokumentu pakiet MUST tworzyć streszczenie po polsku, wyprowadzone deterministycznie z samego
dokumentu, bez modelu językowego i bez opisu, z którego dokument powstał. Streszczenie MUST obejmować:
- instrument i interwał decyzji;
- każde wejście: stronę, warunek, rodzaj i cenę zlecenia oraz wygaśnięcie;
- wyjścia, rozmiar i limity;
- parametry z zakresami i zmienne nazwane.

Formuły MUST być oddane słowami tam, gdzie konstrukcja albo funkcja ma swoje sformułowanie, a dosłownie tam, gdzie go
nie ma. Zmienna z `let` użyta w formule MUST być oddana tym, czym jest (swoją formułą słowami), a nie samą nazwą. Lista
zmiennych MUST zostać, z nazwami, żeby streszczenie dało się zestawić z dokumentem. Każda funkcja rejestru języka MUST
mieć swoje sformułowanie. Interwały MUST być nazwane tak jak w terminalu (`h4`). Godzina z formuły MUST być nazwana jako
UTC, razem z godziną polską zimą i latem. `hypothesis` i `notes` MUST być oddane dosłownie, jako założenia autora. Ten
sam dokument MUST dawać zawsze to samo streszczenie.

#### Scenario: Filtr na innym interwale

- **WHEN** wejście ma warunek `ema(20) @ HOUR_4 > ema(50) @ HOUR_4`
- **THEN** streszczenie MUST mówić o EMA(20) powyżej EMA(50) na `h4` i MUST NOT zawierać `HOUR_4`

#### Scenario: Godzina w limicie

- **WHEN** `limits.no_entry` brzmi `weekday == FRIDAY and hour >= 18`
- **THEN** streszczenie MUST mówić o piątku od 18:00 UTC, czyli 19:00 zimą i 20:00 latem w Polsce

#### Scenario: Ten sam dokument dwa razy

- **WHEN** ten sam dokument jest streszczany dwa razy
- **THEN** oba streszczenia MUST być identyczne

#### Scenario: Zmienna w warunku wejścia

- **WHEN** `let` definiuje `fast` jako `ema(10)`, a wejście brzmi `crosses_above(fast, ema(30))`
- **THEN** streszczenie wejścia MUST mówić o EMA(10) przecinającej od dołu EMA(30), bez nazwy «fast»
