# The screen is mostly refusals

## Why

Platforma strategii działa na produkcji i nie ma ekranu. Operator nie może dziś ani
uruchomić obserwacji, ani zobaczyć, co moduł zdecydował — a `/openapi.json` oddaje 401,
bo terminal nie ma scope'u do tej aplikacji i nie prosi o token. Moduł stoi i nie ma jak
go zacząć używać.

Sedno projektu tej podstrony jest odwrotne, niż podpowiada intuicja. **Dobrze
zaprojektowana strategia odrzuca ponad 95% obserwowanych świec**, więc ekran nad nią jest
w przeważającej części listą „nie, ponieważ…". Ekran zbudowany wokół setupów byłby pusty
przez większość czasu i bezużyteczny dokładnie wtedy, gdy operator go potrzebuje — bo
pytanie, które ludzie zadają takim systemom, brzmi „czemu nic się nie dzieje", a nie „co
kupiliśmy". Odmowy są treścią, nie szumem, i mają dwa różne lekarstwa: dziura w pokryciu
jest odpowiadana backfillem, odmowa strategii — czytaniem strategii.

## What Changes

- Nowa podstrona `Strategie` w terminalu: katalog wpisów, obserwacje, decyzje z powodami
  i zachowane raporty backtestu. Lista decyzji **nie filtruje domyślnie odmów** i pokazuje
  rodzaj odmowy jako pierwszorzędną informację, nie jako szczegół.
- Operator może z niej **założyć obserwację** (strategia + instrument + parametry) oraz ją
  włączyć i wyłączyć. Bez tego moduł nie ma jak zacząć działać: dziś nie ma ani jednej
  obserwacji i nie istnieje droga, żeby powstała.
- `modules/strategy`: `openapi.py` drukujący dokument bez uruchamiania procesu — źródło
  dla generatora, tak jak mają market-data, teams i polymarket-data.
- Terminal: `contract.strategy.generated.ts` z tego dokumentu, wpis w `contract.mjs`,
  własny klient i własny scope (`VITE_ENTRA_SCOPE_STRATEGY`), bo każdy moduł stoi za
  własną bramką i przyjmuje token wystawiony na własną audiencję.
- `infra/`: **delegowany scope w Easy Auth strategii**. Dziś ta rejestracja go nie ma —
  powstała dla wołających maszynowych — więc przeglądarka nie ma o co poprosić i token
  operatora nie istnieje. To jest jedyna przyczyna dzisiejszego 401.
- **Wycięte przy archiwizacji (2 września 2026), do `a-decision-and-a-report-can-be-read`:**
  podgląd odczytów, na których stanęła decyzja, i widok zachowanych raportów backtestu.
  Oba wymagania czekały na pierwszą decyzję i pierwszy raport do obejrzenia, których
  w chwili archiwizacji nadal nie było; spec główny nie ma nieść wymagania bez ekranu.
  Poziomy i stosunek zysku do ryzyka są w wierszu decyzji; klient czyta już `/backtests`.
- Poza zakresem: wykresy nad decyzjami, uruchamianie backtestu z ekranu (to komenda,
  świadomie), edycja wpisu strategii (wpis jest kodem w obrazie).

## Capabilities

### New Capabilities

- `terminal-strategy`: co operator widzi i może zrobić nad platformą strategii — katalog,
  obserwacje, decyzje z powodami, raporty; oraz czego ten ekran nie robi.

### Modified Capabilities

- `terminal-identity`: terminal zdobywa token per moduł, a lista modułów rośnie o
  strategię — wymaganie mówiące, że moduł bez scope'u jest wołany bez poświadczenia,
  zyskuje piąty adres.

## Impact

- `modules/strategy/strategy/openapi.py` (nowy) — bez zmian w zachowaniu modułu.
- `modules/terminal`: `src/strategy/**` (nowe), `src/data/config.ts`, `src/app/tabs.ts`,
  `scripts/contract.mjs`, `vite.config.ts` (proxy), konfiguracja Static Web App.
- `infra/app-service.tf`: scope w `module.strategy_easy_auth`, adres w `terminal_*`
  wyjściach; `terraform apply` przed wdrożeniem terminala, jak zwykle.
- CI: job `terminal` już dziś biegnie na zmianach w `modules/workbench/` i
  `market_data/contract.py`; ta zmiana dokłada `modules/strategy/` do tego samego filtra,
  bo `contract:check` jest sprawdzianem tego szwu.
