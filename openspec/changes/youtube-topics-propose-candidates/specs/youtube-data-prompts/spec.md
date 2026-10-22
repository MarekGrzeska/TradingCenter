## ADDED Requirements

### Requirement: Kanał czyta nowe filmy swoim promptem

Każdy kanał MUST mieć przypisany dokładnie jeden prompt. Dopisanie bez wskazania promptu MUST przypisać zasiany.
Film MUST dostać prompt kanału w chwili, gdy zostaje zauważony. Film wskazany do analizy, także z listy kandydatów,
MUST dostać prompt wskazany razem z nim albo zasiany. Ten prompt MUST być promptem filmu: pętla MUST czytać film
właśnie nim. Zmiana promptu kanału MUST dotyczyć filmów zauważonych od tej chwili i MUST NOT zmieniać promptu filmów
już zauważonych. Temat MUST NOT mieć promptu.

#### Scenario: Zmiana promptu kanału

- **WHEN** operator zmienia prompt kanału, którego filmy są już odczytane
- **THEN** nowe filmy kanału MUST być czytane nowym promptem, a odczyty starszych MUST zostać bez zmian

#### Scenario: Prompt usunięty z wyboru

- **WHEN** klient przypisuje kanałowi prompt usunięty albo nieistniejący
- **THEN** kontrakt MUST odmówić z powodem

## REMOVED Requirements

### Requirement: Kanał i temat czytają nowe filmy swoim promptem
**Reason**: Temat nie wprowadza już filmów do archiwum, więc nie ma czego czytać jego promptem. Wymaganie zastępuje „Kanał czyta nowe filmy swoim promptem”.
**Migration**: Migracja zdejmuje prompt z tematów. Filmy zauważone wcześniej przez temat zachowują swój prompt i odczyty.
