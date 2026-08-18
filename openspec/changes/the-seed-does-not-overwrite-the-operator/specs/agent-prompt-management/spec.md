## ADDED Requirements

### Requirement: Zasiew z wdrożenia nie przykrywa tego, co zapisał operator

Treść promptu wstawiana przez migrację jest wartością domyślną, a nie decyzją. Moduł MUST
odróżniać wiersz wstawiony przez migrację od wiersza zapisanego przez operatora i MUST NOT
pozwolić, by zasiew stał się treścią obowiązującą, gdy operator zapisał cokolwiek po
poprzednim zasiewie.

Wersje MUST być unikatowe. Dwa wiersze o tej samej wersji sprawiają, że odczyt zwraca inną
treść, niż mówi jej numer, a usunięcie zasiewu przy wycofaniu migracji zabiera ze sobą
tekst, którego migracja nigdy nie zapisała.

#### Scenario: Wdrożenie zasiewa prompt, gdy operator nic nie zapisał

- **WHEN** migracja zasiewa nową treść promptu, a najnowszy zapis pochodzi z poprzedniego
  zasiewu
- **THEN** nowa treść zostaje zapisana i staje się obowiązująca

#### Scenario: Wdrożenie zasiewa prompt po zapisie operatora

- **WHEN** migracja zasiewa nową treść promptu, a operator zapisał własną treść po
  poprzednim zasiewie
- **THEN** zasiew nie zostaje zapisany
- **AND** odczyt nadal zwraca treść zapisaną przez operatora

#### Scenario: Dwa zapisy o tej samej wersji

- **WHEN** zapisywana jest treść pod wersją, która już istnieje
- **THEN** magazyn odrzuca zapis, zamiast przyjąć drugi wiersz o tej samej wersji
