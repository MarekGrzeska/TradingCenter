## MODIFIED Requirements

### Requirement: Instrumenty wyszukuje się po frazie

Terminal MUST pozwalać wyszukać instrumenty po frazie i MUST pokazać dla każdego wyniku symbol,
nazwę, klasę aktywów oraz informację, czy da się nim handlować. Bieżące bid i ask MUST być pokazane
tam, gdzie źródło je podaje. Wyszukiwanie MUST być dostępne jako podpowiedzi przy polu wyboru
instrumentu, a nie jako osobny widok listy — instrument wybiera się tam, gdzie jest potrzebny.
Wyszukiwanie MUST dać się zawęzić do jednej klasy aktywów.

#### Scenario: Wyszukiwanie po frazie

- **WHEN** operator wpisuje frazę w polu wyboru instrumentu
- **THEN** terminal pokazuje pasujące instrumenty z symbolem, nazwą, klasą aktywów i flagą
  handlowalności

#### Scenario: Wyszukiwanie zawężone do klasy

- **WHEN** wybrana jest klasa aktywów, a operator wpisuje frazę
- **THEN** podpowiedzi obejmują wyłącznie instrumenty tej klasy

#### Scenario: Fraza bez wyników

- **WHEN** żaden instrument nie pasuje do frazy
- **THEN** terminal stwierdza, że nic nie znaleziono, zamiast pokazywać pustą listę bez komentarza

#### Scenario: Wyszukiwanie zawodzi

- **WHEN** źródło danych nie odpowiada na wyszukiwanie
- **THEN** terminal pokazuje, co zawiodło, wraz z możliwością ponowienia

#### Scenario: Pisanie w polu wyszukiwania

- **WHEN** operator pisze frazę znak po znaku
- **THEN** terminal MUST NOT wysyłać zapytania po każdym znaku
- **AND** pokazuje wynik ostatniej wpisanej frazy, nawet gdy wcześniejsza odpowiedź wróci później

### Requirement: Katalog instrumentów mówi, gdy jest niepełny

Terminal MUST pozwalać wyliczyć instrumenty danej klasy aktywów bez wpisywania frazy i MUST pokazać,
że wynik został ucięty, gdy źródło to zgłasza. Lista ucięta MUST NOT wyglądać jak kompletna, bo
operator wybierający z niej instrument do archiwizowania podejmuje decyzję na podstawie tego, co
widzi.

#### Scenario: Wyliczenie instrumentów klasy

- **WHEN** operator wybiera klasę aktywów i nie wpisuje żadnej frazy
- **THEN** terminal pokazuje instrumenty tej klasy do wyboru

#### Scenario: Katalog ucięty

- **WHEN** źródło zgłasza, że wyliczenie zostało ucięte
- **THEN** terminal stwierdza to przy podpowiedziach
- **AND** wskazuje, że wpisanie frazy sięga poza to, co zostało wyliczone

#### Scenario: Katalog kompletny

- **WHEN** źródło zwraca wyliczenie bez ucięcia
- **THEN** terminal podaje liczbę instrumentów bez ostrzeżenia o niekompletności

## ADDED Requirements

### Requirement: Podpowiadanie zachowuje się wszędzie tak samo

Terminal wybiera z listy w kilku miejscach — klasa aktywów, instrument, instrument archiwizowany na
wykresie — i MUST zachowywać się w nich identycznie: wybór z klawiatury strzałkami i Enterem,
zamknięcie Escape, jawny komunikat o braku dopasowań, jawny komunikat o porażce źródła z możliwością
ponowienia oraz czytelne wskazanie, że wybór jest już dokonany i da się go cofnąć. Zachowanie tych
pól MUST NOT różnić się między miejscami użycia.

#### Scenario: Wybór z klawiatury

- **WHEN** operator porusza się po podpowiedziach strzałkami i zatwierdza Enterem
- **THEN** wybrana pozycja zostaje przyjęta, tak samo w każdym miejscu, gdzie terminal podpowiada

#### Scenario: Rezygnacja z wyboru

- **WHEN** operator naciska Escape przy otwartych podpowiedziach
- **THEN** podpowiedzi zamykają się, a wcześniejszy wybór pozostaje nietknięty

#### Scenario: Cofnięcie dokonanego wyboru

- **WHEN** wybór jest już dokonany
- **THEN** pole pokazuje, co zostało wybrane, i pozwala to wyczyścić bez przeładowania widoku

### Requirement: Klasy aktywów są wyliczalne

Terminal MUST pozwalać wybrać klasę aktywów z listy klas, których źródło używa, a nie z frazy
wpisanej ręcznie. Lista MUST obejmować wszystkie klasy, jakimi źródło opisuje instrumenty.

#### Scenario: Wybór klasy

- **WHEN** operator otwiera pole klasy aktywów
- **THEN** widzi klasy używane przez źródło i wybiera jedną z nich

#### Scenario: Klasa spoza listy

- **WHEN** operator wpisuje frazę niepasującą do żadnej klasy
- **THEN** terminal stwierdza, że taka klasa nie istnieje, i nie pozwala przejść dalej

## REMOVED Requirements

### Requirement: Wynik wyszukiwania trafia do slotu

**Reason**: Na wykres trafiają wyłącznie instrumenty archiwizowane, więc droga z surowego wyniku
wyszukiwania wprost do slotu prowadziłaby do wykresu bez danych. Wybór instrumentu do slotu odbywa
się teraz z listy archiwizowanych.

**Migration**: Zachowanie opisuje wymaganie „Slot przyjmuje wyłącznie instrument archiwizowany"
w zdolności `terminal-grid`. Instrument nieobecny w archiwum dokłada się najpierw w zakładce
`Instruments`.
