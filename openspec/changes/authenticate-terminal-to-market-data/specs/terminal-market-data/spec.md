## MODIFIED Requirements

### Requirement: Zerwane połączenie wraca samo i mówi o sobie

Strumień MUST być wznawiany po zerwaniu, z odstępem rosnącym między próbami, a stan połączenia
(łączenie, połączony, wznawianie, zamknięty) MUST być dostępny odbiorcom. Luka powstała w czasie
przerwy MUST zostać domknięta, ale terminal MUST NOT dociągać jej sam — subskrypcja rozpoczyna się
snapshotem, więc ponowne połączenie przynosi brakujące świece razem ze stanem bieżącym.

Odmowa, której ponawianie nie naprawi, MUST być odróżniona od zerwania i MUST NOT być ponawiana
bez końca. Archiwum odmawia subskrypcji pary nieśledzonej **przed** handshake'em, a przeglądarka
nie udostępnia statusu odrzuconego handshake'u — nieudane połączenie wygląda więc tak samo jak
niedostępne archiwum. Terminal MUST rozstrzygnąć, które z dwojga zaszło, zanim osiądzie w pętli
ponawiania, i MUST pokazać powód odmowy zamiast stanu wznawiania. Rozstrzygnięcie MUST kosztować
najwyżej jedno pytanie na serię niepowodzeń.

Zestawienie połączenia poprzedza pobranie poświadczenia jednorazowego, więc próba może się nie
udać, zanim jakikolwiek socket zostanie otwarty, i przybywa trzeci rodzaj niepowodzenia obok
zerwania i odmowy dotyczącej pary: **utrata tożsamości**. Terminal MUST odróżnić ją od obu
pozostałych. Utrata tożsamości MUST zatrzymać ponawianie i MUST być pokazana jako wymagająca
zalogowania, bo żadna liczba prób jej nie naprawi. Nieudane pobranie poświadczenia z innej
przyczyny — archiwum nie odpowiada — MUST być czytane jako zerwanie i ponawiane.

Ta sama reguła obowiązuje przy rozstrzyganiu powodu nieudanego handshake'u: porażka rozstrzygnięcia
MUST być czytana jako „ponawiaj dalej", chyba że jest odmową dotyczącą tożsamości — wtedy MUST być
czytana jako utrata tożsamości. Bez tego wyjątku wygasła sesja wyglądałaby jak niedostępne archiwum
i ponawiałaby się bez końca, nigdy nie mówiąc operatorowi, że wystarczy się zalogować.

#### Scenario: Wykres pary, której nikt nie archiwizuje

- **WHEN** widok subskrybuje parę, która nie jest śledzona, a archiwum odmawia połączenia
- **THEN** wykres mówi, że ta para nie jest archiwizowana, i wskazuje, gdzie to zmienić
- **AND** terminal przestaje ponawiać, zamiast pokazywać wznawianie bez końca

#### Scenario: Archiwum nie odpowiada również na pytanie o powód

- **WHEN** połączenie nie dochodzi do skutku, a rozstrzygnięcie powodu też się nie udaje
- **THEN** terminal ponawia dalej z rosnącym odstępem, bo to jest przypadek zerwania

#### Scenario: Rozstrzygnięcie powodu kończy się odmową z powodu tożsamości

- **WHEN** połączenie nie dochodzi do skutku, a pytanie o powód zostaje odrzucone z powodu
  tożsamości
- **THEN** terminal przestaje ponawiać i pokazuje, że operator musi się zalogować
- **AND** MUST NOT pokazywać tego jako niedostępności archiwum

#### Scenario: Poświadczenie jednorazowe nie zostaje wydane, bo sesja wygasła

- **WHEN** terminal prosi o poświadczenie jednorazowe, a archiwum odmawia z powodu tożsamości
- **THEN** terminal nie otwiera połączenia i przestaje ponawiać
- **AND** pokazuje, że operator musi się zalogować

#### Scenario: Poświadczenie jednorazowe nie zostaje wydane, bo archiwum milczy

- **WHEN** terminal prosi o poświadczenie jednorazowe, a archiwum nie odpowiada
- **THEN** terminal ponawia próbę zestawienia z rosnącym odstępem, bo to jest przypadek zerwania

#### Scenario: Połączenie pada

- **WHEN** strumień się zrywa
- **THEN** odbiorcy widzą stan wznawiania, a terminal ponawia próby z rosnącym odstępem
- **AND** każda próba poprzedzona jest pobraniem świeżego poświadczenia jednorazowego

#### Scenario: Połączenie wraca

- **WHEN** strumień zostaje wznowiony po przerwie
- **THEN** snapshot z ponownej subskrypcji uzupełnia świece z okresu przerwy
- **AND** odbiorcy widzą stan połączony
- **AND** terminal nie wysyła osobnego zapytania o historię, żeby domknąć lukę

#### Scenario: Snapshot styka się z posiadaną serią

- **WHEN** snapshot niesie świece, które terminal już ma
- **THEN** świece o tych samych znacznikach czasu podmieniają się, zamiast tworzyć duplikaty
