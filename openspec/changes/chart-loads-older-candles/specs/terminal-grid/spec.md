## MODIFIED Requirements

### Requirement: Slot przyjmuje wyłącznie instrument archiwizowany

Symbol w slocie MUST być wybierany z listy, której jedynym źródłem jest lista instrumentów
archiwizowanych przez archiwum, i która MUST pokazywać je wszystkie naraz — lista jest z założenia
krótka, bo ogranicza ją pułap par zbieranych przez archiwum. Slot MUST NOT przyjmować symbolu wpisanego
z ręki ani wymagać wpisania frazy, żeby zobaczyć, co jest do wyboru — wykres pary, której nikt nie
zbiera, nie ma czego pokazać, a operator dowiadywał się o tym dopiero z komunikatu przy pustym wykresie.

#### Scenario: Wybór instrumentu do slotu

- **WHEN** operator otwiera pole instrumentu w slocie
- **THEN** widzi wszystkie instrumenty archiwizowane i wyłącznie je
- **AND** wybranie jednego z nich ustawia go w slocie

#### Scenario: Instrument spoza archiwizowanych

- **WHEN** archiwum nie zbiera danego instrumentu
- **THEN** lista wyboru go nie zawiera
- **AND** terminal wskazuje zakładkę `Instruments` jako miejsce, gdzie dokłada się instrument do
  archiwizowanych

#### Scenario: Nic nie jest archiwizowane

- **WHEN** archiwum nie zbiera ani jednego instrumentu
- **THEN** pole instrumentu mówi to wprost i kieruje do zakładki `Instruments`
- **AND** MUST NOT pokazywać pustej listy bez wyjaśnienia

#### Scenario: Listy archiwizowanych nie da się odczytać

- **WHEN** archiwum nie odpowiada na pytanie, co zbiera
- **THEN** pole instrumentu mówi, że nie da się teraz wybrać instrumentu, wraz z możliwością
  ponowienia
- **AND** slot zachowuje instrument już w nim ustawiony
