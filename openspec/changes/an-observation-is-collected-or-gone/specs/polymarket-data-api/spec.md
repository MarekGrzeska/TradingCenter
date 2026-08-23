## ADDED Requirements

### Requirement: Obserwacje zakłada się i usuwa przez kontrakt

Kontrakt MUST pozwalać odczytać listę obserwacji, objąć wydarzenie obserwacją i usunąć
obserwację. Wskazanie wydarzenia MUST przyjmować zarówno adres strony dostawcy, jak i sam
identyfikator wydarzenia, i MAY nieść grupę, do której wydarzenie ma trafić.

Objęcie obserwacją MUST być niepodzielne: albo powstaje obserwacja wraz z całą strukturą rynków
i wyników, albo nie powstaje nic. Wydarzenie już obserwowane MUST NOT tworzyć drugiej obserwacji —
powtórzone żądanie MAY zaktualizować grupę i MUST powiedzieć, że obserwacja już trwała.

**Zatrzymanie obserwacji bez usunięcia jej MUST NOT być czynnością kontraktu.** Obserwacja albo
jest zbierana, albo jej nie ma: trzeci stan to miejsce na liście, które nic nie robi, a jego
jedynym producentem było żądanie istniejące po to, żeby je wytwarzać.

#### Scenario: Objęcie obserwacją po adresie

- **WHEN** operator wskazuje adres strony wydarzenia
- **THEN** powstaje obserwacja wraz z rynkami i wynikami tego wydarzenia
- **AND** odpowiedź niesie to, co zostało zapisane

#### Scenario: Wydarzenie objęte obserwacją po raz drugi

- **WHEN** operator wskazuje wydarzenie, które jest już obserwowane
- **THEN** nie powstaje druga obserwacja
- **AND** odpowiedź stwierdza, że obserwacja już trwała

#### Scenario: Usunięcie obserwacji przez kontrakt

- **WHEN** operator usuwa obserwację wydarzenia
- **THEN** wydarzenie znika z listy obserwacji
- **AND** nie pozostaje po nim ani jedna próbka ani jeden zapis zebranego zakresu

#### Scenario: Usunięcie obserwacji, której moduł nie prowadzi

- **WHEN** operator usuwa obserwację wydarzenia, którego moduł nie obserwuje
- **THEN** odpowiedź nazywa to wprost, zamiast zgłaszać awarię

## MODIFIED Requirements

### Requirement: Kasowanie danych jest czynnością kontraktu, a nie narzędzia

Kasowanie zebranej historii MUST być osiągalne wyłącznie przez kontrakt REST. Żądanie MUST
wskazywać, czego dotyczy, i MUST NOT być skutkiem ubocznym niczego innego. To samo MUST
obowiązywać usunięcie obserwacji w całości — wraz z wydarzeniem, jego rynkami, wynikami
i wszystkim, co dla niego zebrano.

Skasowanie MUST usunąć próbki i zapis zebranego zakresu razem, w jednej niepodzielnej operacji —
zakres uchodzący za zebrany po usunięciu próbek jest wiążący dla planowania i sprawi, że
uzupełnianie już tam nie wróci. Usunięcie obserwacji MUST być niepodzielne w tym samym sensie:
obserwacja bez swojej historii i historia bez swojej obserwacji są oba stanem, którego nikt nie
zamawiał.

#### Scenario: Operator kasuje historię wydarzenia

- **WHEN** operator kasuje zebraną historię wydarzenia
- **THEN** ani jedna jego próbka nie pozostaje w archiwum
- **AND** ani jeden zapis zebranego zakresu tego wydarzenia nie pozostaje w archiwum

#### Scenario: Kasowanie przerwane w połowie

- **WHEN** kasowanie nie może dojść do końca
- **THEN** archiwum zostaje w stanie sprzed kasowania

#### Scenario: Zapytanie o okres po skasowaniu

- **WHEN** konsument pyta o okres, który przed skasowaniem był zebrany
- **THEN** archiwum stwierdza, że tego okresu nie zebrało
- **AND** MUST NOT stwierdzać, że nie było wtedy notowań

## REMOVED Requirements

### Requirement: Obserwacje są zarządzalne przez kontrakt

**Reason**: zarządzanie obserwacją to teraz objęcie i usunięcie, a nie objęcie i zakończenie.
Wymaganie zostało zastąpione przez „Obserwacje zakłada się i usuwa przez kontrakt", które niesie
niezmienioną połowę o obejmowaniu i nową o usuwaniu. Rozdzielone, a nie zmodyfikowane, bo dwa
jego scenariusze opisywały czynność, której już nie ma, a scenariusz opisujący czynność nieistnie-
jącą jest gorszy od jego braku.

**Migration**: konsumenci wołający `DELETE /events/{id}/tracking` wołają
`DELETE /events/{id}` — z tą różnicą, że historia znika razem z obserwacją. Odczyt listy
i objęcie obserwacją nie zmieniają się wcale.
