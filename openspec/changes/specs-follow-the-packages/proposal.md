## Why

Rachunek po refactorze (kierunek D) zapowiadał „skonsolidować 64 mikro-specki
w specyfikacje per moduł". **Obie połowy tego zdania nie przeżyły pomiaru**, i to jest
powód, dla którego ta zmiana wygląda inaczej, niż zapowiadała karta.

**Nie jest ich 64 i nie są mikro.** Jest 61 specek, 10 420 linii, 389 wymagań — średnio
171 linii na speckę. Poniżej 80 linii jest **11 z 61**; największa, `terminal-chart`, ma
634. Nie ma tu korpusu mikro-specek, jest długi ogon jedenastu małych.

**„Per moduł" pogorszyłoby czytanie.** Scalenie dałoby pięć plików, z czego dwa po ponad
trzy tysiące linii: terminal 3 168 (15 specek, 111 wymagań, 341 scenariuszy) i workbench
3 573 (23 specki). Plik, w którym każda zmiana produkuje diff w trzytysięcznym pliku, nie
jest ułatwieniem. Karta obiecywała przy tym „tańszą sesję agenta" — a specki nie wchodzą do
kontekstu sesji, czyta się je na żądanie. CLAUDE.md, która wchodzi, przestała je wymieniać
w tym samym kierunku D, więc ten cel jest już osiągnięty bez ruszania specek.

**Duplikacja jednak istnieje — tylko w innym miejscu, i daje się policzyć.** Z 389 wymagań
**33 są drugim albo trzecim powtórzeniem nazwy już gdzieś postawionej** (356 nazw
unikalnych). Nie rozkładają się przypadkowo. Układają się w trzy grona i każde ma tę samą
przyczynę:

| Grono | Powtórzeń | Gdzie | Co ten kod dziś naprawdę robi |
|---|---|---|---|
| baza i migracje | 9 nazw × 3 | `agent-` / `market-data-` / `teams-database-connection` | `packages/tc-runtime` |
| dostęp z przeglądarki | 5 nazw × 2–3 | `agent-` / `market-data-` / `teams-browser-access` | `packages/tc-runtime` (Easy Auth) |
| powierzchnia narzędzi | 3 nazwy × 2–3 | `market-data-tools`, `trading-mcp-tools`, `workbench-team-tools` | `packages/tc-mcp-kit` |

`agent-database-connection` i `teams-database-connection` mają **identyczną listę dziewięciu
wymagań, nazwa w nazwę** — 230 i 153 linie mówiące to samo o **jednym** procesie, bo od
20 sierpnia agent i teams są jednym modułem. `market-data-database-connection` dzieli z nimi
siedem z dziewięciu.

A `packages/` **nie ma ani jednej specki.** To jest cała diagnoza: specki opisują świat
sprzed `packages-replace-the-hand-copies`, w którym trzy moduły robiły to samo każdy u
siebie. Kod przestał tak wyglądać; wymagania nie.

Repo ma na to własną zasadę, tylko dla testów: **„A shared package is tested once, in
`packages/`. A consumer gets at most one integration test that the real pairing works"**
(CLAUDE.md, reguła 5). Ta zmiana stosuje ją do wymagań, bo to ta sama sytuacja i ten sam
tryb awarii — poprawka podróżuje kopiowaniem.

## What Changes

**Nie ubywa specek — ubywa powtórzeń.** To jest teza tej zmiany, a nie jej rozczarowanie:
33 postawienia wymagania stają się 11, a każde staje tam, gdzie stoi kod, który je spełnia.

**Trzy nowe specki, po jednej na współdzieloną zdolność:**

- `tc-runtime-database-connection` — dziewięć wymagań o tożsamości zamiast hasła, szyfrowaniu,
  braku poświadczeń w logach, migracji we własnym starcie, blokadzie doradczej i własności
  tego, co migracja tworzy;
- `tc-runtime-browser-access` — uznany adres wywołujący, brak poświadczeń w logach
  i odpowiedziach, poświadczenie nie w adresie, brak wiary w warstwę przed sobą;
- `tc-mcp-kit-tool-surface` — opis narzędzia jako część kontraktu, zapisany sufit
  powierzchni, oznaczenie narzędzia zapisującego.

**Konsumenci zostają i chudną do tego, co jest ich własne.** `market-data-database-connection`
zatrzymuje „Wygasające poświadczenie jest odnawiane", którego nie ma żadna inna;
`market-data-tools` zatrzymuje swoje jedenaście narzędzi i swój sufit z liczbą;
`trading-mcp-tools` swoje oznaczenie zapisu na czterech narzędziach. Każdy konsument
zatrzymuje **najwyżej jedno** wymaganie mówiące, że prawdziwe sparowanie z pakietem działa —
dokładnie to, co reguła 5 daje testom.

**Trzy pary agent/teams stają się jedną specką każda**, bo opisują jeden proces: `*-models`
(dwie z trzech nazw wspólne), `*-tool-access` (trzy wspólne), `*-usage` (jedna wspólna) →
`workbench-models`, `workbench-tool-access`, `workbench-usage`. To domknięcie B na poziomie
wymagań: kod scalił się 20 sierpnia, specki zostały dwie.

**Czego ta zmiana świadomie nie rusza.** `agent-trading` i `teams-trading` **zostają
osobno**, i to jest wynik pomiaru, nie przeoczenie: nie dzielą **ani jednej** nazwy
wymagania. Rozmowa nie narzuca własnych granic handlowych, a rewizja zespołu niesie swoje —
to są dwa różne wymagania o dwóch różnych rzeczach, które przypadkiem mają podobny tytuł
pliku. Tak samo `agent-chat`, `agent-chart-*`, `teams-runs`, `teams-schedules`,
`teams-triggers`, `teams-catalogue` i cały terminal. Ogon jedenastu małych specek zostaje
nietknięty — sprawdzony po jednej, żadna nie jest fragmentem sąsiedniej.

**Nazwy scenariuszy nie zmieniają się ani o znak.** Wymaganie przenoszone do specki pakietu
idzie z całym ciałem i wszystkimi scenariuszami, jak stoi. To jest twardy warunek, nie
staranność: OpenSpec blokuje archiwizację przy zmianie nazwy scenariusza, więc każda taka
edycja zablokowałaby kolejne zmiany.

## Capabilities

### New Capabilities

- `tc-runtime-database-connection`
- `tc-runtime-browser-access`
- `tc-mcp-kit-tool-surface`

### Modified Capabilities

- `market-data-database-connection`, `market-data-browser-access`, `market-data-tools` —
  tracą wymagania przeniesione do pakietu, zatrzymują własne;
- `trading-mcp-tools`, `workbench-team-tools` — jak wyżej;
- `agent-database-connection` + `teams-database-connection` → `workbench-database-connection`;
- `agent-browser-access` + `teams-browser-access` → `workbench-browser-access`;
- `agent-models` + `teams-models` → `workbench-models`;
- `agent-tool-access` + `teams-tool-access` → `workbench-tool-access`;
- `agent-usage` + `teams-usage` → `workbench-usage`.

Zmiana kwalifikuje się przez **pierwszą** kategorię wyzwalacza (`openspec/specs/**`) i
dotyka **czwartej**: czy pakiet w `packages/` ma własne wymagania, jest pytaniem
o architekturę, a nie o porządek plików. Dlatego jest `design.md`.

## Impact

**Wyłącznie `openspec/specs/**`.** Ani jednej linii kodu, żadnej migracji, żadnego
kontraktu, żadnego pliku w `infra/`. Testy, które dziś dowodzą tych wymagań, zostają tam,
gdzie są — a tam, gdzie reguła 5 już została zastosowana i test stoi w `packages/`, specka
wreszcie mówi to samo.

**Weryfikacja**: `openspec validate --strict` po każdym scaleniu, oraz zliczenie nazw
wymagań przed i po — 389 postawień pod 356 nazwami ma stać się 367 pod 356. Ani jedna nazwa
nie może zniknąć z korpusu; wolno jej tylko przestać występować dwa razy.

**Czego to nie naprawia.** Terminal ma 15 specek i 3 168 linii i po tej zmianie nadal będzie
miał 15 — nie dzieli z nikim ani jednego wymagania, bo nie bierze żadnego pakietu. Jeżeli
tamten zbiór komuś przeszkadza, to jest osobne pytanie i nie o duplikację.

## Artefakty tej zmiany

`design.md` — **tak**: decyzja „pakiet dostaje własną zdolność w `openspec/specs/`" jest
nowa, ma dwie odrzucone alternatywy i zmienia to, czym w tym repo jest specka.

`tasks.md` — **tak**: praca idzie przez trzynaście plików i kolejność ma znaczenie
(specka pakietu przed odchudzeniem konsumenta, inaczej wymaganie znika z korpusu w połowie
operacji).

`review.md` — **tak, po wdrożeniu**: jedyną obroną tej zmiany jest liczenie nazw przed i po,
a to nie jest test w CI.
