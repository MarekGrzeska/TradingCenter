## MODIFIED Requirements

### Requirement: Świeca w budowie jest oznaczona

Świeca w budowie zmienia się przy każdym kwotowaniu i nie jest utrwalana. Każda wiadomość
niosąca świecę MUST stwierdzać, czy jest ona zamknięta, czy w budowie, żeby konsument mógł je
odróżnić.

Moduł MUST udostępniać świecę w budowie także **odczytem**, a nie wyłącznie w subskrypcji.
Konsument, któremu wystarczy cena teraz, MUST NOT być zmuszany do otwarcia strumienia:
uścisk dłoni, bilet i utrzymywane połączenie są ceną za ciąg zmian, a nie za jedno pytanie.
Odczytana świeca MUST być tą samą, którą niósłby snapshot subskrypcji w tej chwili.

Świeca w budowie MUST NOT być utrwalana — ani przy odczycie, ani przy publikacji. Odczyt
oddaje to, co moduł trzyma w pamięci, i nic z tego nie zapisuje.

Gdy konsument nie wskaże rozdzielczości, moduł MUST odpowiedzieć z najdrobniejszej
śledzonej rozdzielczości, która świecę w budowie ma. To moduł wie, który feed naprawdę
przynosi kwotowania; wołający zgadujący rozdzielczość dostałby „brak" dla pary, której cena
jest dostępna. Wskazaną rozdzielczość moduł MUST uszanować. Odpowiedź MUST nazywać
rozdzielczość, z której pochodzi.

Odpowiedź bez świecy w budowie MUST nieść powód, który da się odróżnić: para nie jest
śledzona, rynek jest zamknięty, albo rynek jest otwarty i mimo to nic nie przychodzi.
Ostatni z nich jest awarią zbierania i MUST NOT czytać się jak cisza rynku.

#### Scenario: Odbiorca rozróżnia świece

- **WHEN** konsument odbiera świecę z subskrypcji
- **THEN** wiadomość stwierdza, czy świeca jest zamknięta, czy w budowie

#### Scenario: Odczyt ceny teraz

- **WHEN** konsument prosi o świecę w budowie śledzonej pary, której rynek jest otwarty
- **THEN** dostaje ją bez otwierania subskrypcji
- **AND** odpowiedź stwierdza, że okres jest w budowie, i nazywa rozdzielczość

#### Scenario: Rozdzielczość nie została wskazana

- **WHEN** konsument prosi o świecę w budowie, nie wskazując rozdzielczości
- **THEN** odpowiedź pochodzi z najdrobniejszej śledzonej rozdzielczości, która taką świecę
  ma
- **AND** nazywa tę rozdzielczość

#### Scenario: Rynek jest zamknięty

- **WHEN** konsument prosi o świecę w budowie pary, której rynek jest zamknięty
- **THEN** odpowiedź nie niesie świecy
- **AND** stwierdza, że rynek jest zamknięty, a nie że danych brak

#### Scenario: Rynek otwarty, a świecy nie ma

- **WHEN** rynek pary jest otwarty, a moduł nie ma dla niej świecy w budowie
- **THEN** odpowiedź stwierdza to jako stan zbierania, nie jako ciszę rynku

#### Scenario: Odczyt niczego nie utrwala

- **WHEN** konsument odczytuje świecę w budowie
- **THEN** archiwum świec zamkniętych pozostaje niezmienione
