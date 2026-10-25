## ADDED Requirements

### Requirement: Streszczenie powstaje z samego dokumentu

Dla każdego poprawnego dokumentu pakiet MUST tworzyć streszczenie po polsku, wyprowadzone deterministycznie z samego
dokumentu, bez modelu językowego i bez opisu, z którego dokument powstał. Streszczenie MUST obejmować:
- instrument i interwał decyzji;
- każde wejście: stronę, warunek, rodzaj i cenę zlecenia oraz wygaśnięcie;
- wyjścia, rozmiar i limity;
- parametry z zakresami i zmienne nazwane.

Formuły MUST być oddane słowami tam, gdzie konstrukcja albo funkcja ma swoje sformułowanie, a dosłownie tam, gdzie go
nie ma. Każda funkcja rejestru języka MUST mieć swoje sformułowanie. Interwały MUST być nazwane tak jak w terminalu
(`h4`). Godzina z formuły MUST być nazwana jako UTC, razem z godziną polską zimą i latem. `hypothesis` i `notes` MUST być
oddane dosłownie, jako założenia autora. Ten sam dokument MUST dawać zawsze to samo streszczenie.

#### Scenario: Filtr na innym interwale

- **WHEN** wejście ma warunek `ema(20) @ HOUR_4 > ema(50) @ HOUR_4`
- **THEN** streszczenie MUST mówić o EMA(20) powyżej EMA(50) na `h4` i MUST NOT zawierać `HOUR_4`

#### Scenario: Godzina w limicie

- **WHEN** `limits.no_entry` brzmi `weekday == FRIDAY and hour >= 18`
- **THEN** streszczenie MUST mówić o piątku od 18:00 UTC, czyli 19:00 zimą i 20:00 latem w Polsce

#### Scenario: Ten sam dokument dwa razy

- **WHEN** ten sam dokument jest streszczany dwa razy
- **THEN** oba streszczenia MUST być identyczne

### Requirement: Różnice między rewizjami po ścieżkach dokumentu

Pakiet MUST podawać zmiany między dwiema rewizjami jednej strategii jako listę zmian. Każda zmiana MUST nieść ścieżkę w
tej samej postaci co problemy walidacji (`entries[0].when`), rodzaj (dodane, usunięte, zmienione) oraz wartość przed i po.
Domyślnie porównanie MUST dotyczyć rewizji poprzedniej. Inna kolejność kluczy w dokumencie MUST NOT być zmianą.

#### Scenario: Zmiana stopu

- **WHEN** rewizja 5 różni się od rewizji 4 tylko stopem
- **THEN** lista zmian MUST mieć jedną pozycję pod ścieżką `exits.stop` z wartością przed i po

#### Scenario: Pierwsza rewizja

- **WHEN** porównanie dotyczy rewizji 1 bez wskazania innej
- **THEN** odpowiedź MUST mówić, że to pierwsza rewizja, zamiast zgłaszać błąd

### Requirement: Zapis wskazuje rewizję, na której się opiera

Zapis rewizji MAY wskazywać rewizję, na której oparto zmianę. Gdy ostatnia rewizja strategii jest inna niż wskazana, a
zapisywana treść różni się od ostatniej, zapis MUST zostać odrzucony jako konflikt z numerem ostatniej rewizji i MUST NOT
niczego zapisać. Zapis bez wskazanej podstawy MUST działać jak dotąd.

#### Scenario: Zapis na nieaktualnej podstawie

- **WHEN** zapis wskazuje podstawę 4, a ostatnią rewizją jest 5
- **THEN** zapis MUST zostać odrzucony z numerem 5, a rewizja 6 MUST NOT powstać
