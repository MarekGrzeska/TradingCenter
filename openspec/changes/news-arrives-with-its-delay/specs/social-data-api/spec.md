## MODIFIED Requirements

### Requirement: Kontrakt wyłącznie czyta

Kontrakt MUST NOT publikować trasy, która zbiera, wzbogaca albo kasuje cokolwiek. Nie może też
zmieniać niczego poza jednym wyjątkiem opisanym niżej. Zbiór jest czynnością pętli modułu,
a nie zdolnością klienta.

Odróżnia to ten moduł od `polymarket-data`, gdzie trasy zmieniające stan są, bo tam istnieje lista
obserwacji, którą operator układa. Tutaj nie ma czego układać: źródło jest zbierane w całości.

Jedynym wyjątkiem jest znacznik zachowania newsa (`social-data-news-ingest`). Kontrakt MAY
publikować trasę, która stawia albo zdejmuje ten znacznik przy jednym newsie. Ta trasa MUST NOT
zmieniać niczego innego: ani treści newsa, ani jego momentów, ani żadnego posta. Znacznik jest
decyzją operatora o retencji, a nie edycją archiwum.

#### Scenario: Klient szuka drogi do wymuszenia zbioru

- **WHEN** klient przegląda dokument kontraktu
- **THEN** MUST NOT znaleźć trasy kasującej ani wymuszającej pobranie ze źródła
- **AND** jedyną trasą zapisującą MUST być ta, która stawia albo zdejmuje znacznik zachowania newsa

#### Scenario: Znacznik nie dotyka treści

- **WHEN** klient stawia znacznik zachowania przy newsie
- **THEN** tytuł, lead, adres i wszystkie momenty newsa MUST zostać bez zmian
