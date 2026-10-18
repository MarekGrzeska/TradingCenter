## Purpose

Źródło „stan”: reguła, która sama pyta o wartość — cenę, wskaźnik, prawdopodobieństwo — i odpala, gdy
warunek przestaje być fałszywy. Do tego czego takie pytanie nie może kosztować.

## ADDED Requirements

### Requirement: Wartość warunku pochodzi z narzędzia tylko do odczytu

Wartość, którą porównuje reguła stanu, MUST pochodzić z wywołania narzędzia z katalogu narzędzi
procesu, oznaczonego jako tylko do odczytu, tą samą drogą, którą czyta je rozmowa. Pakiet MUST NOT
liczyć własnych wskaźników, czytać cudzej bazy ani wywoływać narzędzia zapisującego.

Wskaźnik policzony drugi raz tutaj to druga odpowiedź na to samo pytanie. Alert reagujący na inną
wartość niż ta, którą zobaczy operator w terminalu, jest gorszy niż brak alertu.

#### Scenario: Warunek na wskaźniku

- **WHEN** reguła porównuje RSI(14) EURUSD z progiem
- **THEN** wartość MUST pochodzić z tego samego narzędzia, którego używa rozmowa

### Requirement: Reguła odpala na zboczu, nie na stanie

Reguła stanu MUST odpalić w chwili, w której warunek przeszedł z niespełnionego w spełniony. Warunek,
który przy kolejnych sprawdzeniach pozostaje spełniony, MUST NOT dawać kolejnych odpaleń. Zbocze w
czasie martwym po poprzednim odpaleniu MUST zostać zapisane jako pominięte z tego powodu i MUST NOT
przesuwać początku czasu martwego.

#### Scenario: Cena utrzymuje się nad progiem

- **WHEN** warunek przechodzi w spełniony i pozostaje taki przez dziesięć sprawdzeń
- **THEN** reguła MUST odpalić dokładnie raz

#### Scenario: Cena miga wokół progu

- **WHEN** warunek przestaje być spełniony i spełnia się ponownie przed upływem czasu martwego
- **THEN** reguła MUST NOT odpalić, a historia MUST nazywać czas martwy jako powód

### Requirement: Niedostępność wartości to trzeci stan

Gdy narzędzie nie odpowiada, odmawia albo jego wynik nie zawiera liczby pod wskazanym polem, reguła MUST
zapisać sprawdzenie jako niedostępność z powodem i MUST NOT traktować go jako warunku niespełnionego.
Odmowa narzędzia MUST być zapisana odrębnie od nieosiągalności. Pierwsze sprawdzenie po niedostępności
MUST porównywać z ostatnim znanym wynikiem, a nie z fałszem.

Gdyby niedostępność liczyła się jako fałsz, każdy powrót narzędzia po awarii przy cenie nad progiem
wyglądałby jak zbocze i dawał fałszywy alert.

#### Scenario: Archiwum rynku nie odpowiada

- **WHEN** narzędzie ceny nie odpowiada przy sprawdzeniu
- **THEN** reguła MUST NOT odpalić, a historia MUST mieć wpis nazywający niedostępność

#### Scenario: Powrót narzędzia przy spełnionym warunku

- **WHEN** ostatni znany wynik był spełniony, potem nastąpiła niedostępność, a następne sprawdzenie jest spełnione
- **THEN** reguła MUST NOT odpalić

### Requirement: Sprawdzanie nie kosztuje modelu

Sprawdzenie warunku MUST NOT wywoływać modelu językowego.

#### Scenario: Tysiąc sprawdzeń bez odpalenia

- **WHEN** reguła stanu jest sprawdzana wielokrotnie, a warunek się nie spełnia
- **THEN** MUST NOT powstać żadne wywołanie modelu ani wiersz jego zużycia

### Requirement: Interwał sprawdzania ma dolną granicę

Interwał sprawdzania reguły MUST być nie krótszy niż granica z ustawień pakietu. Zapis reguły z
krótszym interwałem MUST zostać odrzucony z powodem nazywającym granicę. Jedna reguła MUST być
sprawdzana co najwyżej raz naraz, także przy wielu instancjach procesu.

#### Scenario: Interwał poniżej granicy

- **WHEN** operator zapisuje regułę z interwałem krótszym niż granica
- **THEN** zapis MUST zostać odrzucony, a komunikat MUST podawać granicę

### Requirement: Przebicie poziomu nie ginie między sprawdzeniami

Reguła stanu nad ceną MAY porównywać ekstremum bieżącego okresu (najwyższą albo najniższą cenę
tworzącej się świecy) zamiast ceny ostatniej. Kreator MUST proponować ekstremum jako domyślne dla
porównań „powyżej” i „poniżej” ceny.

Szpilka, która przebiła poziom i wróciła między dwoma sprawdzeniami, to ten alert, na który operator
czekał.

#### Scenario: Szpilka między sprawdzeniami

- **WHEN** cena przebija 1,10 i wraca poniżej, zanim nastąpi następne sprawdzenie, a reguła porównuje najwyższą cenę okresu
- **THEN** reguła MUST odpalić przy tym sprawdzeniu
