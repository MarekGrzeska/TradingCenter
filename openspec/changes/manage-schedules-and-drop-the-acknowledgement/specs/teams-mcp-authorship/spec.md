## MODIFIED Requirements

### Requirement: Moduł nie rozszerza uprawnień, które operator już ma

Zestaw narzędzi MUST NOT pozwolić operatorowi zrobić niczego, czego nie mógłby zrobić sam w
terminalu. Każda odmowa modułu `teams` — cudzy zespół, wyczerpana granica dobowa, rewizja
nie do uruchomienia — MUST obowiązywać tak samo, gdy o to samo prosi model.

Zdanie działa też w drugą stronę i to jest ta strona, której brakowało: czego operator może
dokonać w terminalu, tego MUST móc dokonać przez model. Zestaw, który zakłada harmonogram, a
zatrzymać go każe iść do terminala, jest polityką dostępu zapisaną tutaj, a nie w `teams` —
tyle że napisaną przez pominięcie.

Nowa droga do modułu nie jest nową polityką dostępu. Gdyby była, każda decyzja zapisana w
`teams` musiałaby być zapisana drugi raz tutaj — i rozjechałaby się przy pierwszej poprawce.

#### Scenario: Granica dobowa zatrzymuje przebieg zamówiony z czatu

- **WHEN** model uruchamia przebieg zespołu, który wyczerpał dobową granicę kosztu
- **THEN** przebieg MUST NOT ruszyć
- **AND** model dostaje odmowę nazywającą granicę i liczbę, która ją wyczerpała

#### Scenario: Odmowa modułu dociera do operatora jego słowami

- **WHEN** `teams` odmawia zapisu, nazywając agenta albo narzędzie, przez które odmowa zapadła
- **THEN** ten sam powód MUST dotrzeć do modelu
- **AND** MUST NOT zostać zastąpiony komunikatem ogólnym

#### Scenario: Czynność dostępna w terminalu jest dostępna z czatu

- **WHEN** operator może wykonać czynność na swoim harmonogramie w terminalu
- **THEN** zestaw narzędzi ma czynność, którą model robi to samo
- **AND** odmowa, jeśli padnie, pochodzi z `teams`, a nie z braku narzędzia
