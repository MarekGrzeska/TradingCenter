## MODIFIED Requirements

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
