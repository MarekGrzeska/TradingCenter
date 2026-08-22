## MODIFIED Requirements

### Requirement: Każde wywołanie archiwum niesie poświadczenie

Terminal MUST dokładać poświadczenie do każdego żądania HTTP kierowanego do modułu, który go
wymaga — archiwum (świec, pokrycia, zleceń, usunięć oraz katalogu instrumentów, który archiwum
proxuje), workbencha, gatewaya i archiwum rynków predykcyjnych. Dokładanie MUST być własnością
wspólnej warstwy wywołań, nie decyzją pojedynczego wywołania: trasa dopisana później MUST nieść
poświadczenie bez pamiętania o tym przez autora.

**Poświadczenie nie jest jedno, jest jedno na moduł.** Każdy z tych modułów stoi za własną bramą
i przyjmuje token wystawiony dla **własnej publiczności**, więc wspólna warstwa MUST wiedzieć, po
który zakres pytać dla którego adresu, a token wzięty dla jednego modułu MUST NOT być wysłany do
drugiego. Wymaganie było napisane wtedy, gdy terminal wołał jeden moduł; wyliczanie tras jednego
z nich przestało być tym samym, co reguła, którą naprawdę niesie.

Moduł, dla którego terminal nie ma skonfigurowanego zakresu, MUST być traktowany jak moduł bez
konfiguracji tożsamości (patrz „Brak konfiguracji tożsamości oznacza pracę bez niej"), a nie jak
moduł, do którego wolno wysłać cudze poświadczenie.

#### Scenario: Nowa trasa w kodzie terminala

- **WHEN** do kodu dochodzi wywołanie kolejnej trasy modułu, który wymaga poświadczenia
- **THEN** niesie poświadczenie bez osobnego kroku po stronie wywołującego

#### Scenario: Katalog instrumentów

- **WHEN** wyszukiwarka pyta o instrumenty, a archiwum przekazuje pytanie dalej do gatewaya
- **THEN** żądanie do archiwum niesie poświadczenie tak samo jak żądanie o świece

#### Scenario: Dwa moduły o różnych publicznościach

- **WHEN** terminal woła dwa różne moduły w tej samej sesji operatora
- **THEN** do każdego trafia poświadczenie wystawione dla publiczności tego modułu
- **AND** poświadczenie wzięte dla jednego MUST NOT zostać wysłane do drugiego
