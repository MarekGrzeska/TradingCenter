## MODIFIED Requirements

### Requirement: Harmonogram układa się rytmem i godziną, nie wyrażeniem czasowym

Terminal MUST pozwalać ułożyć harmonogram przez wybór rytmu (co N minut, co godzinę,
codziennie, w wybrane dni tygodnia, w wybrany dzień miesiąca) i godziny, bez wpisywania
wyrażenia czasowego. Wyrażenie czasowe MUST pozostać dostępne jako droga dla rytmu, którego
kreator nie obejmuje, i MUST być schowane poza domyślnym widokiem formularza. Harmonogram,
którego wyrażenia nie da się opisać żadnym rytmem, MUST być pokazany tym wyrażeniem i MUST
dać się edytować bez utraty tego, co niesie.

Przy rytmie powtarzającym się częściej niż raz na dobę terminal MUST pozwalać wskazać dni
tygodnia, tym samym wyborem dni, którym układa się rytm tygodniowy. Operator, który umie
wyłączyć weekend w jednym rytmie i nie umie w drugim, ma do wyboru wyrażenie czasowe — czyli
tę drogę, której to wymaganie ma mu oszczędzić.

Formularz MUST NOT trzymać dwóch stanów jednego wyzwolenia: komplet zaznaczonych dni i brak
ograniczenia dni to jeden i ten sam harmonogram, więc MUST być jednym stanem formularza.
Operator, który widzi dwa, nie wie, który z nich zapisał.

Odznaczenia ostatniego dnia MUST NOT dać się dokonać: harmonogram, który nie wyzwala się w
żaden dzień, nie jest harmonogramem, a formularz, który pozwala go ułożyć, odmawia dopiero
przy zapisie — wyglądając do tej chwili na skończony.

Zespół układa operator rynku, nie administrator systemu. Pole z pięcioma gwiazdkami jest
dla niego zamkniętymi drzwiami, a wpisane w nie na wyczucie wyrażenie jest gorsze niż brak
harmonogramu, bo wygląda na działające.

#### Scenario: Harmonogram codzienny

- **WHEN** operator wybiera rytm „codziennie" i godzinę 9:00
- **THEN** zapisany harmonogram wyzwala się codziennie o 9:00 czasu polskiego
- **AND** operator nie wpisał żadnego wyrażenia czasowego

#### Scenario: Weekend wyłączony przy rytmie godzinowym

- **WHEN** operator wybiera rytm „co godzinę", minutę 35 i odznacza sobotę oraz niedzielę
- **THEN** zapisany harmonogram wyzwala się od poniedziałku do piątku
- **AND** operator nie wpisał żadnego wyrażenia czasowego

#### Scenario: Podgląd nadąża za dniami

- **WHEN** operator odznacza sobotę i niedzielę w układanym harmonogramie
- **THEN** pokazane najbliższe wyzwolenia nie zawierają soboty ani niedzieli

#### Scenario: Rytm dobowy nie ma dni tygodnia

- **WHEN** operator wybiera rytm „codziennie"
- **THEN** kreator nie pokazuje wyboru dni tygodnia przy tym rytmie
- **AND** wybór dni jest dostępny pod rytmem tygodniowym

#### Scenario: Operator odznacza ostatni dzień

- **WHEN** operator odznacza ostatni pozostały dzień tygodnia
- **THEN** dzień zostaje zaznaczony, a harmonogram dalej ma dzień, w którym się wyzwala

#### Scenario: Operator zaznacza z powrotem wszystkie dni

- **WHEN** operator zaznacza z powrotem sobotę i niedzielę przy rytmie godzinowym
- **THEN** harmonogram jest tym samym, co harmonogram bez wskazania dni
- **AND** opis harmonogramu nie wymienia dni tygodnia

#### Scenario: Rytm spoza kreatora

- **WHEN** operator otwiera harmonogram, którego wyrażenia kreator nie obejmuje
- **THEN** widzi to wyrażenie i może je poprawić
- **AND** zapis nie zamienia go na inny rytm
