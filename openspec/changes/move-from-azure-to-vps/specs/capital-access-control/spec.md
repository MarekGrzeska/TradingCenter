## MODIFIED Requirements

### Requirement: Tożsamość pochodzi wyłącznie ze zwalidowanego tokenu

Moduł rozpoznaje uwierzytelnionego wołającego z oświadczeń tokenu. Oświadczenia MUST pochodzić z
tokenu, który zweryfikowano — podpis kluczem wystawcy, wystawca, audiencja i ważność — zanim moduł
uzna kogokolwiek za rozpoznanego. Weryfikację MUST wykonywać proces modułu, przed rejestrem tras,
na każdym żądaniu, które przyszło z zewnątrz. Nagłówek niosący oświadczenia platformy
(`X-MS-CLIENT-PRINCIPAL*`) MUST NOT być traktowany jako tożsamość — na krawędzi MUST być usuwany.

Token nieważny MUST zostać odrzucony, zanim dotknie rejestru tras i jakiejkolwiek trasy, a odmowa
MUST być odróżnialna od odmowy rejestru. Wymaganie MUST dać się sprawdzić z zewnątrz, bez wiedzy o
konfiguracji: żądanie z tokenem nieważnym MUST dostać odmowę uwierzytelnienia.

#### Scenario: Nieważny token nie dociera do trasy

- **WHEN** z zewnątrz przychodzi żądanie z tokenem o złym podpisie, wystawcy, audiencji albo po terminie
- **THEN** zostaje odrzucone przed rejestrem tras
- **AND** odmowa pochodzi od warstwy uwierzytelniającej

#### Scenario: Nagłówek platformy nie jest tożsamością

- **WHEN** żądanie z zewnątrz niesie nagłówek `X-MS-CLIENT-PRINCIPAL` bez ważnego tokenu
- **THEN** moduł MUST NOT uznać wołającego za rozpoznanego
- **AND** odpowiada tak, jak na wywołanie bez poświadczenia

#### Scenario: Terminal z ważnym tokenem zostaje rozpoznany

- **WHEN** terminal wywołuje trasę rachunku z ważnym tokenem swojej aplikacji
- **THEN** moduł rozpoznaje aplikację wołającą z oświadczenia `azp` albo `appid`
- **AND** dalszy dostęp rozstrzyga rejestr tras

## ADDED Requirements

### Requirement: Wywołanie z sieci wewnętrznej uwierzytelnia klucz

Żądanie, które nie przyszło przez krawędź, przyszło siecią wewnętrzną kontenerów, czyli od innej
usługi systemu. Takie żądanie MUST nieść klucz współdzielony usługi, a tożsamość wołającego MUST
wynikać z klucza. Żądanie z sieci wewnętrznej bez ważnego klucza MUST zostać odrzucone. Żądanie z
krawędzi MUST NOT zostać przyjęte na podstawie samego klucza, poza trasą strumienia, która zostaje
wyjątkiem opisanym w wymaganiu o poświadczeniu jednorazowym.

#### Scenario: Workbench woła gateway

- **WHEN** workbench wywołuje gateway siecią wewnętrzną z kluczem współdzielonym
- **THEN** gateway rozpoznaje wołającego jako usługę i przepuszcza żądanie do rejestru tras

#### Scenario: Klucz przyniesiony z zewnątrz

- **WHEN** żądanie z krawędzi niesie klucz współdzielony, ale nie niesie ważnego tokenu
- **THEN** gateway odmawia
