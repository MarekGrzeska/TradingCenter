## Why

Operator widzi dziś rachunek wyłącznie przez agenta — zdaniem w rozmowie, na żądanie. Nie
ma ekranu, na którym stoi to, co przy handlu jest tłem: które konta demo istnieją, ile na
nich jest, co jest otwarte i czy przybyło od ostatniego spojrzenia. Doładowanie, które
właśnie powstało (`demo-account-is-the-operators-to-set`), też jest dostępne tylko przez
model.

Ekranu nie da się zrobić bez wcześniejszej decyzji, bo **terminal nie ma jak dosięgnąć
gatewaya**: gateway jest niepubliczny, wpuszcza dwa adresy wyjściowe (market-data i
trading-mcp), a przeglądarka nie jest żadnym z nich. Ta zmiana tę regułę odwraca — świadomie
i z ceną wypisaną w `design.md`.

## What Changes

- **BREAKING (architektura):** `capital-gateway` przestaje być modułem osiągalnym wyłącznie
  z dwóch adresów. Staje przed nim Easy Auth, a lista adresów przestaje być drzwiami.
  To, co je zastępuje, to dwa mechanizmy naraz: poświadczenie sprawdzane w kodzie modułu i
  rejestr mówiący, która tożsamość ma dostęp do której powierzchni — ten sam kształt, który
  `market-data` ma od czasu, gdy wpuściła do siebie narzędzia.
- Moduł zaczyna uznawać **dwa rodzaje poświadczenia**: klucz współdzielony, którym posługują
  się moduły, oraz uwierzytelnionego wołającego, którego aplikację moduł rozpoznaje —
  przeglądarka nie uniesie klucza i nigdy nie powinna go zobaczyć.
- Wołający z przeglądarki sięga **wyłącznie po rachunek**: konta, pozycje, przełączenie
  konta i korektę salda. Zlecenia, zamykanie pozycji i strumień pozostają poza jego
  zasięgiem, mimo że przeszedł te same drzwi.
- `terminal` dostaje zakładkę **Accounts**: konta demo z saldem, środkami dostępnymi i
  wynikiem, pozycje konta aktywnego, doładowanie i przełączenie konta. Odświeżanie cykliczne
  — dostawca nie streamuje stanu rachunku, więc „na bieżąco" znaczy tu odpytywanie.
- Pozycje pokazane są dla konta **aktywnego**, nie dla wszystkich. Zebranie pozycji z
  pozostałych wymagałoby przełączania się po kolei, a każde przełączenie zrywa strumień
  notowań i zmienia konto, na które pójdzie następne zlecenie.

## Capabilities

### New Capabilities

- `terminal-accounts`: ekran rachunku w terminalu — co pokazuje, jak się odświeża, co
  operator może z niego zrobić i co MUST powiedzieć, zanim to zrobi.

### Modified Capabilities

- `capital-access-control`: poświadczenie ma dwie postacie; dostęp jest rozstrzygany trasa
  po trasie, a nie raz przy drzwiach.

## Impact

- `infra/app-service.tf`: rejestracja Easy Auth dla gatewaya, lista wpuszczanych aplikacji,
  zniesienie reguł adresowych jako drzwi. `azuread_*` w tym module oznacza **apply
  operatora, lokalnie** — CI odmówi planu, który to rusza.
- `modules/capital-gateway`: `config.py` (lista aplikacji przeglądarki), warstwa dostępu
  trasa-po-trasie obok istniejącego sprawdzenia klucza, `app.py`.
- `modules/terminal`: nowa zakładka i jej ekran, klient HTTP gatewaya, `.env.example`,
  proxy Vite w dev (klucz zostaje po stronie serwera dev, nigdy w bundlu).
- Ekran **nie zadziała po samym wdrożeniu obrazu**: potrzebuje `terraform apply`, który
  postawi Easy Auth i wpuści terminal — ta sama para, którą CLAUDE.md opisuje dla narzędzi
  archiwum („The archive's tools arrive at apply, not at deploy").
- Bez migracji. Bez zmian w `market-data`, `workbench` i `trading-mcp` — ich droga do
  gatewaya (klucz) zostaje nietknięta.
