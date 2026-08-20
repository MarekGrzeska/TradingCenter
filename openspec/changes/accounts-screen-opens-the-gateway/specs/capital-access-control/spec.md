## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Każde wywołanie niesie poświadczenie

Moduł wystawia trasy, które składają zlecenia i zamykają pozycje. MUST wymagać poświadczenia od
każdego wywołującego — na trasach HTTP i przy zestawianiu połączenia WebSocket. Wywołanie bez
poświadczenia albo z poświadczeniem nieuznanym MUST zostać odrzucone przed dotknięciem providera,
odpowiedzią `401`.

Poświadczenie ma dwie postacie i moduł MUST uznawać obie: **klucz współdzielony**, którym
posługują się moduły wołające go po sieci wewnętrznej, oraz **uwierzytelniony wołający**,
którego aplikację moduł rozpoznaje z oświadczeń tokenu. Druga postać istnieje, ponieważ
przeglądarka nie może nieść klucza: sekret w pobranym kodzie jest sekretem opublikowanym.
Moduł MUST sprawdzać obie sam — rozpoznanie aplikacji jest jego własnym sprawdzeniem, nie
zaufaniem do listy w konfiguracji platformy.

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

#### Scenario: Zestawienie WebSocketa bez poświadczenia

- **WHEN** konsument zestawia połączenie WebSocket bez poświadczenia
- **THEN** moduł odmawia zestawienia połączenia
- **AND** nie zapisuje konsumenta do rozgłaszania
