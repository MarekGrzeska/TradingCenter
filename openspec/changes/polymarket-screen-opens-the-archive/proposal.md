## Why

`polymarket-data` zbiera od 22 sierpnia 2026 i jedynym sposobem, żeby cokolwiek z tego
zobaczyć, jest zapytać model. To odwraca kierunek, w którym ten terminal działa wszędzie
indziej: operator patrzy sam, a model jest drugą parą oczu, nie jedyną. Prawdopodobieństwo
zdarzenia porusza się wolno i znaczenie ma dopiero w oknie — cyfra podana w zdaniu przez
agenta nie pokazuje ruchu, a właśnie ruch jest tym, po co ten moduł powstał.

Drugi powód jest twardszy. **Kasowanie zebranej historii jest trasą REST i dziś nie sięga
po nią nikt** — `REST_CALLER_APPLICATION_IDS` jest puste, a terminal nie jest wymieniony
w `allowed_applications` modułu. Zdolność, którą specyfikacja świadomie odebrała narzędziom
modelu jako jedyną nieodwracalną, nie ma więc żadnych drzwi. Ekran je otwiera i jest
jedynym miejscem, w którym mogą się otworzyć.

## What Changes

- **NOWA zakładka `Polymarket`** — jeden wpis w rejestrze zakładek, bez zmian w pozostałych
  (`terminal-shell`, „Rejestr zakładek jest otwarty").
- **Lista obserwowanych** — wydarzenie, jego rynki i wyniki, aktualne prawdopodobieństwo
  **jednym żądaniem migawki** na całą listę, nie po żądaniu na wynik. Rynek dwuwynikowy jest
  szczególnym przypadkiem wielowynikowego, a nie odwrotnie, i ekran MUST pokazywać wydarzenie
  zamiast udawać, że każdy rynek jest niezależną monetą.
- **Zmiany w oknach 5m/15m/1h/4h/12h/24h/7d**, liczone przez moduł przy odczycie. Okno bez
  pokrycia MUST być nazwane brakiem z przyczyną, nigdy narysowane jako zero — to ta sama
  granica, którą kontrakt REST już trzyma, i przeniesienie jej na ekran jest połową wartości
  tej zakładki.
- **Objęcie i zakończenie obserwacji, oraz grupy.** Zakończenie obserwacji zatrzymuje
  próbkowanie i **nie rusza danych** — ekran MUST to powiedzieć, bo przycisk nazwany „stop"
  obok danych czyta się jak kasowanie.
- **Wykres serii prawdopodobieństwa** dla wybranego wyniku, z zakresem czasu i **narysowaną
  granicą najstarszego osiągalnego momentu**. Skala 0..1, nie procenty. To nie jest wykres
  świecowy z podmienioną serią: świeca ma cztery ceny i wolumen, ta seria ma jedną wartość
  i dziury, o których trzeba powiedzieć wprost.
- **Kasowanie zebranej historii — tutaj i nigdzie indziej**, z potwierdzeniem nazywającym,
  czego dotyczy i że jest nieodwracalne. Świadomie w zakresie: zdolność bez drzwi jest
  zdolnością, której nie ma.
- **Infrastruktura.** Rejestracja Easy Auth `polymarket-data` dostaje **delegowany zakres**
  (`access_as_user`), którego dziś nie ma, bo jedynym wołającym miał być workbench z tokenem
  klienta. Terminal zostaje pre-autoryzowany, dopisany do `allowed_applications` modułu
  i do `REST_CALLER_APPLICATION_IDS`. `TOOL_CALLER_APPLICATION_IDS` MUST NOT dostać terminala:
  rozdział powierzchni jest tu całym mechanizmem.
- **Poza zakresem:** alerty i powiadomienia (to workbench), sterowanie tą zakładką przez
  agenta na wzór `agent-chart-control`, oraz zestawianie serii prawdopodobieństwa z ceną
  instrumentu na jednym wykresie. Ostatnie jest kuszące i jest osobną decyzją — dwie osie
  o różnym znaczeniu na jednym obrazku to twierdzenie o korelacji, którego nikt tu jeszcze
  nie zmierzył.

## Capabilities

### New Capabilities

- `terminal-polymarket`: zakładka rynków predykcyjnych — co pokazuje lista, jak czytane są
  zmiany w oknach i brak pokrycia, co robi objęcie i zakończenie obserwacji, jak wygląda
  seria prawdopodobieństwa wraz z granicą pokrycia, i gdzie stoi jedyne w terminalu
  kasowanie zebranej historii.

### Modified Capabilities

- `terminal-identity`: wymaganie „Każde wywołanie archiwum niesie poświadczenie" jest
  napisane o **archiwum** — wylicza świece, pokrycie, zlecenia, usunięcia i katalog
  instrumentów. Terminal woła dziś także workbench i gateway, a wraz z tą zmianą czwarty
  backend, i każdy z nich ma **własną publiczność tokenu**: poświadczenie nie jest jedno,
  jest jedno na moduł. Wymaganie MUST zostać uogólnione do każdego backendu, który terminal
  woła, z zachowaniem tego, co naprawdę niesie — że dokładanie jest własnością wspólnej
  warstwy wywołań, a nie decyzją pojedynczego wywołania.

**Czego ta zmiana w specyfikacjach nie rusza, choć wyglądało, że ruszy.** `terminal-shell`
mówi wprost, że dołożenie zakładki MUST NOT wymagać zmian w pasku ani w pozostałych
zakładkach — nowa zakładka wchodzi w to wymaganie bez jednego słowa zmiany, i to jest ta
sama zasługa uogólnienia, co przy trzecim serwerze narzędzi w workbenchu.
`polymarket-data-caller-access` również nie: trzyma kategorię „wołający sięgający po kontrakt
REST" jako pojęcie, a dopisanie terminala do tej listy jest konfiguracją, nie wymaganiem.
`terminal-market-data` tym bardziej — to jedno wejście na **świece i strumień**, a seria
prawdopodobieństwa nie jest ani jednym, ani drugim.

## Impact

**Terminal.** Nowy katalog `modules/terminal/src/polymarket/` z widokiem, listą, wykresem
i własnym klientem po `contract.polymarket.generated.ts`, który **już istnieje** — wygenerowano
go w `polymarket-data-joins-the-stack` właśnie po to, żeby ta zmiana zaczynała od typów, które
są prawdziwe. Jeden wpis w `src/app/tabs.ts`. Warstwa wywołań dostaje czwartą bazę adresu
i czwarty zakres.

**Infrastruktura, i to ona wyznacza kolejność.** `infra/app-service.tf`: delegowany zakres
w `module.polymarket_data_easy_auth`, `azuread_application_pre_authorized` dla terminala,
terminal w `allowed_applications` i w `REST_CALLER_APPLICATION_IDS`. To jest zmiana
`azuread_*`, więc `apply` jest operatora z konstrukcji, i obowiązuje ta sama pułapka co przy
każdym module: **ustawienia MUST dotrzeć do aplikacji przed obrazem, który ich wymaga** —
tu jednak odwrotnie niż zwykle, bo to obraz *terminala* zaczyna wołać, a odmowa przy pustej
liście czyta się w terminalu jako moduł nieosiągalny, nie jako brak uprawnienia.

**Czego ta zmiana nie rusza.** `polymarket-data` — ani jednej trasy, ani jednego narzędzia:
kontrakt, którego ten ekran potrzebuje, jest już wdrożony i sprawdzony. `market-data`,
`capital-gateway`, `trading-mcp`, workbench.
