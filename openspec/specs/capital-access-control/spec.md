# capital-access-control Specification

## Purpose
Opisuje, kto ma prawo wywołać `capital-gateway` i czego moduł o sobie nie ujawnia, gdy stoi w miejscu
osiągalnym z sieci — czyli warstwę przed wszystkim, co moduł robi z providerem.
## Requirements
### Requirement: Każde wywołanie niesie poświadczenie

Moduł wystawia trasy, które składają zlecenia i zamykają pozycje. MUST wymagać poświadczenia od
każdego wywołującego — na trasach HTTP i przy zestawianiu połączenia WebSocket. Wywołanie bez
poświadczenia albo z poświadczeniem nieuznanym MUST zostać odrzucone przed dotknięciem providera,
odpowiedzią `401`.

Poświadczenie ma dwie postacie — **klucz współdzielony** i **uwierzytelniony wołający**, którego
aplikację moduł rozpoznaje z oświadczeń zwalidowanego tokenu — i **która z nich otwiera drzwi,
zależy od miejsca**. Na produkcji, gdzie przed modułem stoi uwierzytelniający platformy, tożsamością
na trasach HTTP MUST być wyłącznie aplikacja z oświadczeń tokenu: moduł wołający po sieci
wewnętrznej sięga wszystkiego, wołający z przeglądarki rachunku, a klucz współdzielony MUST NOT
otwierać żadnej trasy HTTP, choćby był właściwy. Klucz pozostaje poświadczeniem dokładnie dwóch
miejsc: zestawienia WebSocketa, którego uwierzytelniający platformy nie umie przepuścić, i pracy
lokalnej, gdzie nie ma platformy, która nazwałaby kogokolwiek.

Druga postać istnieje, ponieważ przeglądarka nie może nieść klucza: sekret w pobranym kodzie jest
sekretem opublikowanym. Pierwsza przestaje otwierać trasy HTTP na produkcji, bo klucz jest jeden dla
trzech wołających i wycieka z każdego `.env`, a token nazywa aplikację, której go wydano. Moduł MUST
sprawdzać obie sam — rozpoznanie aplikacji jest jego własnym sprawdzeniem, nie zaufaniem do listy w
konfiguracji platformy.

Ograniczenia dostępu po stronie platformy MUST NOT być traktowane jako spełnienie tego wymagania.
Są warstwą dodatkową, konfigurowaną osobno i osobno psowalną.

#### Scenario: Żądanie bez poświadczenia

- **WHEN** przychodzi żądanie na dowolną trasę modułu poza sondą zdrowia, bez poświadczenia
- **THEN** moduł odpowiada `401`
- **AND** nie wykonuje żadnego wywołania do providera

#### Scenario: Żądanie z nieuznanym poświadczeniem

- **WHEN** przychodzi żądanie z poświadczeniem, którego moduł nie uznaje
- **THEN** moduł odpowiada `401`
- **AND** odpowiedź nie rozróżnia poświadczenia nieistniejącego od błędnego

#### Scenario: Żądanie od uwierzytelnionej aplikacji bez klucza

- **WHEN** przychodzi żądanie bez klucza współdzielonego, niosące uwierzytelnionego
  wołającego, którego aplikację moduł rozpoznaje
- **THEN** moduł przyjmuje żądanie
- **AND** dalszy dostęp rozstrzyga rejestr tras, a nie samo przejście przez drzwi

#### Scenario: Żądanie od uwierzytelnionej aplikacji spoza listy

- **WHEN** przychodzi żądanie od uwierzytelnionej aplikacji, której moduł nie rozpoznaje
- **THEN** moduł odpowiada `401`

#### Scenario: Właściwy klucz bez tożsamości na produkcji

- **WHEN** w konfiguracji produkcyjnej przychodzi żądanie HTTP z właściwym kluczem współdzielonym
  i bez nazwanej aplikacji
- **THEN** moduł odpowiada `401`
- **AND** nie wykonuje żadnego wywołania do providera

#### Scenario: Moduł wołający na produkcji

- **WHEN** w konfiguracji produkcyjnej przychodzi żądanie od aplikacji z listy modułów
  wołających, bez klucza
- **THEN** moduł przyjmuje żądanie na każdej trasie, także składającej zlecenie

#### Scenario: Klucz lokalnie

- **WHEN** poza konfiguracją produkcyjną przychodzi żądanie z właściwym kluczem współdzielonym
- **THEN** moduł przyjmuje żądanie

#### Scenario: Zestawienie WebSocketa bez poświadczenia

- **WHEN** konsument zestawia połączenie WebSocket bez poświadczenia
- **THEN** moduł odmawia zestawienia połączenia
- **AND** nie zapisuje konsumenta do rozgłaszania

### Requirement: Tożsamość pochodzi wyłącznie ze zwalidowanego tokenu

Moduł rozpoznaje uwierzytelnionego wołającego z oświadczeń tokenu. Oświadczenia MUST pochodzić z
tokenu, który ktoś zweryfikował — podpis, wystawca i audiencja — zanim moduł uzna kogokolwiek za
rozpoznanego. Nagłówek niosący oświadczenia, którego nie poprzedziła weryfikacja, MUST NOT być
traktowany jako tożsamość: jest wtedy tym samym, czym jest nagłówek od dowolnego wołającego, czyli
danymi, a nie stwierdzeniem.

Wdrożenie MUST postawić przed modułem uwierzytelniającego, który **odrzuca** token nieważny,
zamiast przepuszczać żądanie dalej bez oświadczeń. Konfiguracja, w której nieważny token dociera
do modułu nierozpoznany, MUST być traktowana jako niespełnienie tego wymagania, a nie jako
łagodniejszy wariant — jej objawem jest odmowa dla każdego wołającego z przeglądarki, nieodróżnialna
od wygasłej sesji operatora.

Wymaganie MUST dać się sprawdzić z zewnątrz, bez wiedzy o konfiguracji: żądanie z tokenem
nieważnym MUST zostać odrzucone, zanim dotknie modułu.

#### Scenario: Nieważny token nie dociera do modułu

- **WHEN** przychodzi żądanie z tokenem, którego nie da się zweryfikować
- **THEN** zostaje odrzucone, zanim dotknie modułu
- **AND** odmowa pochodzi od warstwy uwierzytelniającej, nie od rejestru tras modułu

#### Scenario: Oświadczenia bez weryfikacji nie są tożsamością

- **WHEN** żądanie niesie nagłówek z oświadczeniami, którego nie poprzedziła weryfikacja tokenu
- **THEN** moduł MUST NOT uznać wołającego za rozpoznanego
- **AND** odpowiada tak, jak na wywołanie bez poświadczenia

#### Scenario: Terminal z ważnym tokenem zostaje rozpoznany

- **WHEN** terminal wywołuje trasę rachunku z ważnym tokenem swojej aplikacji
- **THEN** żądanie dociera do modułu z oświadczeniami, którym moduł może wierzyć
- **AND** dalszy dostęp rozstrzyga rejestr tras

### Requirement: Bez skonfigurowanego poświadczenia moduł nie wstaje

Moduł uruchomiony bez skonfigurowanego poświadczenia byłby otwartym endpointem handlowym, a brak
konfiguracji nie objawiłby się niczym widocznym. Moduł MUST odmówić startu, gdy poświadczenia nie
skonfigurowano. MUST NOT wstawać w trybie, w którym uwierzytelnianie jest wyłączone.

#### Scenario: Start bez konfiguracji

- **WHEN** moduł startuje bez skonfigurowanego poświadczenia
- **THEN** odmawia startu z komunikatem wskazującym brakującą konfigurację
- **AND** nie zaczyna nasłuchiwać na żadnym porcie

### Requirement: Sonda zdrowia jest jedynym wyjątkiem

Platforma hostująca sprawdza żywotność aplikacji bez żadnego poświadczenia i na tej podstawie
decyduje o restarcie. Dokładnie jedna trasa MUST być osiągalna bez uwierzytelnienia i MUST
odpowiadać wyłącznie stanem modułu. MUST NOT ujawniać nazwy konta, stanu sesji z providerem,
listy tras ani wersji zależności.

#### Scenario: Platforma odpytuje sondę

- **WHEN** przychodzi żądanie na trasę sondy zdrowia bez poświadczenia
- **THEN** moduł odpowiada stanem swojej żywotności
- **AND** odpowiedź nie niesie żadnej informacji o koncie, sesji ani konfiguracji

### Requirement: Na produkcji moduł nie publikuje swojego API

Interaktywna dokumentacja i schemat OpenAPI podają gotową mapę tras razem z tymi handlowymi.
Na produkcji moduł MUST NOT wystawiać ani interaktywnej dokumentacji, ani schematu OpenAPI.
Poza produkcją MUST je wystawiać — na nich opiera się generowanie kontraktu dla konsumentów.

#### Scenario: Odpytanie o dokumentację na produkcji

- **WHEN** żądanie trafia na ścieżkę dokumentacji lub schematu OpenAPI w konfiguracji produkcyjnej
- **THEN** moduł odpowiada `404`

#### Scenario: Odpytanie o schemat poza produkcją

- **WHEN** żądanie trafia na ścieżkę schematu OpenAPI w konfiguracji nieprodukcyjnej
- **THEN** moduł zwraca schemat
- **AND** generowanie kontraktu z tego schematu działa jak dotąd

### Requirement: Poświadczenie wywołującego nie trafia do logów

Moduł loguje żądania, a poświadczenie przychodzi w każdym z nich. Moduł MUST NOT umieszczać
poświadczenia wywołującego w logach, komunikatach błędów ani odpowiedziach.

#### Scenario: Odrzucone żądanie trafia do logu

- **WHEN** moduł odrzuca żądanie z powodu poświadczenia i loguje to zdarzenie
- **THEN** log niesie ścieżkę, metodę i powód odrzucenia
- **AND** nie niesie poświadczenia ani jego fragmentu

### Requirement: Wołający z przeglądarki sięga tylko po rachunek

Moduł MUST rozstrzygać dostęp trasa po trasie, a nie raz przy drzwiach. Wpuszczenie
aplikacji przez warstwę platformy MUST NOT oznaczać dostępu do wszystkiego, co moduł
wystawia: platforma autoryzuje aplikację, nie trasę, a ten moduł wystawia obok siebie
odczyt rachunku i składanie zleceń.

Wołający uwierzytelniony jako terminal MUST mieć dostęp wyłącznie do tras rachunku:
wyliczenia kont, odczytu pozycji i zleceń oczekujących, przełączenia konta aktywnego oraz
korekty salda konta demo. Składanie zleceń, zamykanie pozycji, zmiana stopów, anulowanie
zleceń oczekujących oraz strumień MUST być dla niego niedostępne — odmową, nie błędem
providera.

Trasa nieujęta w rejestrze MUST być dla takiego wołającego odmówiona, a nie przepuszczona.
Domyślna odpowiedź jest tu ważniejsza niż jakikolwiek pojedynczy wpis: trasa dopisana za
miesiąc byłaby inaczej osiągalna dla przeglądarki w dniu, w którym powstaje, i nic by tego
nie powiedziało.

Tożsamością jest **aplikacja wołająca**, odczytana z własnych oświadczeń tokenu, a nie
nagłówek nazywający zalogowaną osobę.

#### Scenario: Terminal czyta konta

- **WHEN** wołający uwierzytelniony jako terminal odczytuje konta
- **THEN** moduł odpowiada listą kont

#### Scenario: Terminal próbuje złożyć zlecenie

- **WHEN** wołający uwierzytelniony jako terminal wywołuje trasę składającą zlecenie
- **THEN** moduł odmawia przed dotknięciem providera
- **AND** odmowa nazywa brak uprawnienia, a nie awarię providera

#### Scenario: Nowa trasa nie staje się dostępna sama

- **WHEN** moduł wystawia trasę nieujętą w rejestrze dostępu
- **THEN** wołający z przeglądarki dostaje odmowę

