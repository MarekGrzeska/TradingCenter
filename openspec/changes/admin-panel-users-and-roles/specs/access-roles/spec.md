## Purpose

Rozróżnia osoby wchodzące do aplikacji po roli: `admin` robi wszystko jak dotąd, `viewer` tylko czyta archiwum
z telefonu. Rola jest egzekwowana na serwerze, nie w ekranie, bo ekran da się obejść własnym klientem.

## ADDED Requirements

### Requirement: Rola osoby pochodzi z tokenu wystawionego przez Entra

Każdy proces za bramą tokenów (workbench, gateway) MUST ustalać rolę osoby wyłącznie z claimu `roles` zweryfikowanego
tokenu — nie z nagłówka, ciała ani parametru wysłanego przez klienta. Dwie role istnieją: `admin` i `viewer`.
Brama MUST zdejmować z przychodzącego żądania każdy nagłówek ról, zanim zapisze własny, tak jak robi to z nagłówkami
tożsamości. Wywołanie wewnętrzne, dowodzące się wspólnym kluczem, MUST nieść rolę odrębną od `admin` i `viewer`
(`internal`), żeby usługa nie musiała udawać osoby.

#### Scenario: Klient podaje własną rolę

- **WHEN** żądanie niesie nagłówek ról, a token osoby ma rolę `viewer`
- **THEN** proces widzi wyłącznie `viewer`, z tokenu

#### Scenario: Wywołanie wewnętrzne kluczem

- **WHEN** inna usługa wewnętrznej sieci woła proces ze wspólnym kluczem
- **THEN** żądanie niesie rolę `internal` i nie podlega polityce `viewera`

### Requirement: Brak roli oznacza brak dostępu

Osoba z ważnym tokenem, której token nie niesie roli `admin` ani `viewer`, MUST dostać `403` na każdej trasie procesu
z wyjątkiem `GET /me`. Brak claimu `roles` MUST NOT być czytany jako „wszystko wolno". Dotyczy to także tokenu
wydanego przed nadaniem roli: dopóki nie zostanie odnowiony, jego właściciel nie wchodzi.

#### Scenario: Gość bez przypisanej roli

- **WHEN** gość tenanta, któremu nie nadano roli, woła `GET /polymarket/events`
- **THEN** dostaje `403`

#### Scenario: Token sprzed nadania roli

- **WHEN** osoba dostała rolę, ale jej token jeszcze jej nie niesie
- **THEN** dostaje `403` do czasu odnowienia tokenu

### Requirement: Admin ma dostęp jak dotychczas

Osoba z rolą `admin` MUST mieć dostęp do tego, do czego ma go dziś operator: czat i teams, wszystkie trasy
`/market`, `/polymarket`, `/social`, `/youtube`, `/alerts`, `/telegram` oraz gateway.

#### Scenario: Operator po wdrożeniu

- **WHEN** operator z rolą `admin` używa terminala
- **THEN** żadna trasa, z której korzystał wcześniej, nie odpowiada `403`

### Requirement: Viewer czyta archiwum i niczego poza tym

Osoba z samą rolą `viewer` MUST móc wywołać wyłącznie `GET` pod `/social` i `/polymarket` (w tym newsy) oraz
`GET /me` i `/health`. Każde inne żądanie — inna metoda pod tymi prefiksami, czat, teams, `/market`, `/youtube`,
`/alerts`, `/telegram` oraz każda trasa gatewaya — MUST dostać `403`, zanim dotrze do handlera. Dotyczy to także
tras MCP pakietów: viewer MUST NOT dotknąć narzędzi agenta, które sięgają po konto.

#### Scenario: Viewer czyta posty

- **WHEN** `viewer` woła `GET /social/posts`
- **THEN** dostaje dane

#### Scenario: Viewer próbuje zapisu

- **WHEN** `viewer` woła `PUT /social/news/keep` albo `DELETE /polymarket/events/{id}`
- **THEN** dostaje `403` i nic się nie zmienia

#### Scenario: Viewer próbuje agenta

- **WHEN** `viewer` woła trasę czatu albo `/polymarket/mcp`
- **THEN** dostaje `403`

#### Scenario: Viewer prosi gateway o token terminala

- **WHEN** `viewer` zdobędzie token gatewaya przez rejestrację terminala i woła gateway
- **THEN** gateway odmawia, bo token nie niesie roli `admin`

### Requirement: Osoba może zapytać, kim jest

Proces MUST odpowiadać na `GET /me` każdej osobie z ważnym tokenem, także bez roli, listą jej ról z tokenu.
Odpowiedź służy ekranom do pokazania „brak dostępu" i do ukrycia akcji; MUST NOT być jedyną obroną, bo ją
egzekwuje bramka z poprzednich wymagań.

#### Scenario: Ekran pyta o rolę

- **WHEN** osoba z rolą `viewer` woła `GET /me`
- **THEN** odpowiedź zawiera `viewer` i żadnej innej roli

#### Scenario: Osoba bez roli

- **WHEN** osoba bez roli woła `GET /me`
- **THEN** odpowiedź ma pustą listę ról

### Requirement: Praca lokalna bez tokenów nie wymaga ról

Proces uruchomiony poza serwerem, gdzie nikt nie okazuje tokenu, MUST NOT wprowadzać ról ani odmów z ich powodu.
`GET /me` MUST wtedy odpowiadać `admin`.

#### Scenario: Stos lokalny

- **WHEN** operator pracuje lokalnie bez `SERVER_MODE`
- **THEN** żadna trasa nie odpowiada `403` z powodu roli
