# terminal-alerts Specification

## Purpose
Zakładka Alerty w terminalu: reguły, ich historia i kreator, w którym operator niczego nie wpisuje z
pamięci. Do tego pole na zdanie, które wypełnia kreator za operatora.
## Requirements
### Requirement: Regułę można zmienić zdaniem

Każda reguła MUST mieć „Zmień zdaniem…”, gdy szkice są dostępne. Wynik MUST otworzyć formularz edycji tej reguły
wypełniony zmienioną postacią, z tym, jak zdanie zostało zrozumiane; reguła MUST zmienić się dopiero po zapisie
formularza przez operatora.

#### Scenario: Zmiana zdaniem

- **WHEN** operator wpisuje zdanie przy regule i prosi o zmianę
- **THEN** MUST otworzyć się formularz edycji z propozycją, a lista reguł MUST pozostać bez zmian do zapisu

### Requirement: Lista reguł mówi, co każda reguła ostatnio zrobiła

Zakładka MUST pokazywać każdą regułę z nazwą, źródłem w słowach, adresatem, stanem (włączona,
wyłączona i z jakiego powodu), ostatnim sprawdzeniem albo zdarzeniem oraz ostatnim odpaleniem z jego
wynikiem. Reguła z wadą MUST być wyróżniona, a liczba takich reguł MUST być widoczna bez przewijania.

#### Scenario: Reguła stanu, której narzędzie nie odpowiada

- **WHEN** ostatnie sprawdzenia reguły skończyły się niedostępnością
- **THEN** wiersz reguły MUST to mówić z powodem, zamiast pokazywać ją jako spokojną

### Requirement: Kreator nie ma pola na nazwę z pamięci

Kreator MUST dawać wybór, a nie pole tekstowe, dla: źródła, typu zdarzenia, atrybutu, narzędzia,
instrumentu, pola wyniku, porównania i adresata. Wartości wybiera się z katalogu pakietu. Pola
filtra MUST powstawać ze schematu typu zdarzenia albo argumentów narzędzia. Wartość atrybutu
tekstowego, który producent oznaczył jako mający kilka wartości wartych wyboru (kanał, autor, zespół),
MUST być wybierana spośród wartości widzianych w zachowanych zdarzeniach; wartość jeszcze niewidziana
wpisuje się wyłącznie przez wyraźną opcję „inna wartość”. Wpisywane są liczby, nazwa reguły i szablon.
Odmowa zapisu MUST być pokazana przy polu, którego dotyczy.

#### Scenario: Reguła na kanał YouTube

- **WHEN** operator wybiera typ „film odczytany”
- **THEN** kreator MUST pokazać kanały widziane w filmach do wyboru i pole oceny jako liczbę
- **AND** nazwa kanału spoza tej listy MUST wymagać wyboru „inna wartość”

#### Scenario: Instrument spoza śledzonych

- **WHEN** archiwum podaje listę śledzonych instrumentów
- **THEN** argument `symbol` MUST być listą wyboru z tych instrumentów

### Requirement: Szablon ma podgląd

Kreator MUST pokazywać podgląd treści wiadomości wypełnionej przykładowym zdarzeniem tego typu albo
ostatnią wartością warunku, zanim reguła zostanie zapisana.

#### Scenario: Szablon z atrybutem

- **WHEN** operator wpisuje szablon odwołujący się do kanału i oceny
- **THEN** podgląd MUST pokazać te pola wypełnione wartościami przykładu

### Requirement: Zdanie wypełnia kreator, nie zapisuje

Zakładka MUST mieć pole na zdanie. Wynik szkicu MUST otwierać kreator wypełniony szkicem, z wadami
szkicu pokazanymi przy polach. Reguła MUST powstać dopiero po zatwierdzeniu kreatora przez operatora.
Gdy szkice są niedostępne, pole MUST mówić dlaczego.

#### Scenario: Szkic z wadą

- **WHEN** szkic wraca z instrumentem, którego archiwum nie śledzi
- **THEN** kreator MUST otworzyć się wypełniony, z wadą przy polu instrumentu, a zapis MUST być niedostępny, dopóki wada nie zniknie

### Requirement: Historia odpaleń jest czytelna bez bazy

Dla każdej reguły zakładka MUST pokazywać ostatnie odpalenia z czasem, źródłem, treścią i wynikiem,
w tym pominięcia z powodu czasu martwego, zdławienia, niedostępności i odpuszczenia.

#### Scenario: Reguła zdławiona

- **WHEN** reguła została zdławiona sufitem wysyłek
- **THEN** historia MUST pokazywać zdławione odpalenia z tym powodem

### Requirement: Formularz wybiera adresata i bota osobno

Formularz reguły MUST mieć obok pola „Kogo powiadomić” pole „Którym botem”, w którym MUST być tylko boty, przez które
wybrany adresat jest związany. Gdy adresat ma jednego bota, pole MUST go podpowiadać i MAY go pozostawić pustym; gdy
kilku, MUST wymagać wyboru i MUST domyślnie podpowiadać bota, którego wiązanie odbiera. Lista reguł MUST mówić, przez
którego bota reguła idzie, a regułę bez bota o dwuznacznym adresacie MUST pokazywać jako wadliwą z tym powodem.

#### Scenario: Adresat z kilkoma botami

- **WHEN** operator wybiera adresata związanego przez trzy boty
- **THEN** pole bota MUST wymagać wyboru jednego z tych trzech i MUST NOT oferować innych botów

#### Scenario: Reguła sprzed zmiany

- **WHEN** reguła zapisana bez bota wskazuje adresata o jednym wiązaniu
- **THEN** lista MUST pokazać ją jako działającą, a edycja MUST wypełnić pole bota tym jedynym botem

