## Purpose

Co moduł dokłada do zebranego posta modelem — tłumaczenie i ocenę wpływu na rynek — i na jakich
warunkach: kiedy liczy, czym stempluje, co robi bez klucza i co się dzieje ze starym odczytem.

## ADDED Requirements

### Requirement: Moduł przechowuje cudzy osąd, ostemplowany

Wzbogacenie MUST być zapisane wraz z nazwą modelu i momentem powstania. Moduł MUST NOT
przedstawiać oceny jako własnej: zapisane jest to, co dany model powiedział w danej chwili,
i tylko w tej formie MUST być wydawane klientowi.

Ocena wpływu MUST być liczbą całkowitą od 1 do 10, a tematy listą krótkich haseł — nie jednym
napisem, który klient musi rozcinać.

#### Scenario: Odpowiedź niesie stempel

- **WHEN** klient odczytuje post z oceną
- **THEN** odpowiedź MUST nieść nazwę modelu i moment, w którym ocena powstała

#### Scenario: Model zwraca coś spoza zakresu

- **WHEN** model zwraca ocenę spoza zakresu 1–10 albo odpowiedź, której nie da się odczytać
- **THEN** moduł MUST NOT zapisać tej oceny
- **AND** post MUST zostać w archiwum jako niewzbogacony

### Requirement: Ocena powstaje przy zbiorze, nie przy pytaniu

Moduł MUST wzbogacać post wkrótce po zebraniu, a nie w chwili, gdy ktoś o niego pyta. Ocena MUST
być dostępna jako kryterium filtrowania i porządkowania w kontrakcie oraz w narzędziach.

Powodem jest zdolność, którą to daje wyżej: osąd zapadający przy pytaniu nie da się filtrować,
rozjeżdża się między dwiema rozmowami o tej samej treści i kosztuje tokeny za każde pytanie
zamiast raz za post.

#### Scenario: Pytanie o posty o wysokim wpływie

- **WHEN** klient prosi o posty z oceną nie niższą niż podana
- **THEN** odpowiedź MUST być zawężona po ocenie już zapisanej
- **AND** MUST NOT wymagać wywołania modelu

### Requirement: Ponowne wzbogacenie nadpisuje odczyt

Zmiana modelu albo instrukcji MUST prowadzić do nadpisania odczytu przy poście, a nie do
przechowania obu. Historią jest post; ocena posta MUST NOT być wersjonowana.

Rachunek za zużycie modelu jest tu wyjątkiem i zostaje — mówi o tym `social-data-store`.

#### Scenario: Post oceniony ponownie

- **WHEN** post zostaje wzbogacony po raz drugi, innym modelem
- **THEN** przy poście MUST być widoczny wyłącznie nowy odczyt wraz z nazwą tego modelu

### Requirement: Brak skonfigurowanego modelu jest stanem wspieranym

Moduł bez skonfigurowanego dostępu do modelu MUST wystartować, zbierać i odpowiadać na pytania.
Brak wzbogaceń MUST być wtedy nazwany wprost przez kontrakt i przez narzędzie statusu — klient MUST
móc odróżnić „model nie jest skonfigurowany" od „model nie znalazł nic wartego oceny".

#### Scenario: Wdrożenie bez klucza

- **WHEN** moduł startuje bez skonfigurowanego dostępu do modelu
- **THEN** MUST zbierać posty i wydawać je bez tłumaczenia i bez oceny
- **AND** stan „model nieskonfigurowany" MUST być czytelny w odpowiedzi o stan modułu

### Requirement: Nieudane wzbogacenie nie zatrzymuje zbioru

Błąd po stronie modelu — odmowa, przekroczony limit, zerwane połączenie — MUST NOT przerwać pętli
zbioru ani zatrzymać wzbogacania pozostałych postów. Post, którego nie udało się wzbogacić, MUST
zostać w archiwum i MUST być podjęty ponownie w kolejnym przebiegu.

#### Scenario: Model odmawia w środku serii

- **WHEN** wzbogacanie jednego posta kończy się błędem
- **THEN** pozostałe posty z tej serii MUST zostać wzbogacone
- **AND** post, który się nie udał, MUST zostać spróbowany ponownie później

### Requirement: Wzbogacane jest bieżące okno, nie całe archiwum

Moduł MUST ograniczać wzbogacanie do okna, które sam zbiera, i MUST NOT wzbogacać posta, który ma
już aktualny odczyt. Archiwum rosnące bez końca MUST NOT prowadzić do rosnącego bez końca rachunku
za model.

#### Scenario: Archiwum ma tysiąc niewzbogaconych postów sprzed okna

- **WHEN** pętla wzbogacania rusza
- **THEN** MUST wziąć wyłącznie posty z bieżącego okna
