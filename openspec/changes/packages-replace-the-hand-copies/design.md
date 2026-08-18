## Context

Powód jest w `proposal.md` („Why"). Tu liczy się jedno: **co naprawdę jest kopią**, bo plan
iteracji 1 zakładał trzy pakiety, a pomiar z 18 sierpnia 2026 zgadza się tylko z dwoma.

Zmierzono identyczność linia po linii (`difflib.SequenceMatcher` na liniach, bez `autojunk`)
dla każdej pary plików o tej samej nazwie w siedmiu modułach Pythona. Bliźniakiem nazywamy
parę ≥ 70%:

| Plik | Para | Identyczność |
|---|---|---|
| `db.py` | agent ↔ teams | **97,1%** |
| `routers/models.py` | agent ↔ teams | 93,8% |
| `migrate.py` | agent ↔ teams / ↔ market-data | 91,8% / 83,6% |
| `auth.py` | agent ↔ teams | 86,4% |
| `network_identity.py` | teams-mcp ↔ trading-mcp / ↔ market-mcp | 86,2% / 76,9% |
| `schema_version.py` | agent ↔ teams / ↔ market-data | 83,8% / 83,3% |
| `provider.py` | agent ↔ teams | 79,4% |

I to, co bliźniakiem **nie** jest, choć plan tak zakładał:

| Plik | market↔teams | teams↔trading | market↔trading |
|---|---|---|---|
| `__main__.py` | 45,7% | 66,7% | 45,7% |
| `server.py` | 35,9% | 39,1% | 58,2% |
| `config.py` | 36,7% | 18,8% | 24,0% |
| `client.py` | 14,8% | 32,1% | 15,9% |
| `errors.py` | 25,0% | 10,5% | 8,1% |

Dwie liczby z planu wymagają sprostowania: `provider.py` jest identyczny w 79,4%, nie 95%, a
suma ręcznych kopii ponad pierwszy egzemplarz to **~959 linii**, nie ~2000+. Trzecia rzecz
jest ważniejsza od obu: `db.py` jest bliźniakiem **wyłącznie** agent ↔ teams. `market-data`
ma własny, 299-linijkowy, zbieżny w 56% — z trzydziestominutowym oknem na migrację największej
tabeli w repo. To nie jest kopia, która się rozjechała; to jest inny plik.

## Goals / Non-Goals

**Goals:**

- Jeden egzemplarz kodu, który dziś jest kopiowany ręcznie i **zmierzenie** dowodzi, że jest
  kopią.
- Niezależność wdrożenia modułu zachowana konstrukcyjnie, nie obietnicą: pakiet wchodzi do
  obrazu przy buildzie.
- Poprawka we wspólnym kodzie odpala w CI testy wszystkich modułów, które go biorą — inaczej
  zamieniamy dryf kopii na cichą regresję u sąsiada.
- Nowy moduł Pythona zaczyna od zależności, nie od kopiowania sześciu plików.

**Non-Goals:**

- Ujednolicanie plików, które różnią się naprawdę. Zob. D1.
- Jakakolwiek zmiana granicy runtime. Moduły nadal rozmawiają wyłącznie kontraktem, mają
  osobne bazy, osobne tożsamości i imienne listy wywołujących.
- Usuwanie martwego balastu — osobna zmiana, zob. `proposal.md`, „Poza zakresem".
- Wspólne zależności runtime „przy okazji". Pakiet niesie tylko to, czego wymaga jego własny
  kod.

## Decisions

### D1. Dwa pakiety, nie trzy — `tc-mcp-kit` nie powstaje

**Decyzja:** powstają `tc-runtime` i `tc-openai`. Materiał, który plan przeznaczał dla
`tc-mcp-kit`, rozchodzi się na dwie strony: `network_identity.py` i wspólny `_detail` wchodzą
do `tc-runtime` jako jego pod-moduły, a `server.py`, `client.py`, `config.py` i `errors.py`
zostają u siebie, nietknięte.

**Dlaczego:** tabela w „Context". Cztery pliki, które miały być trzonem `tc-mcp-kit`, mają
8–58% wspólnych linii. To nie są kopie, które się rozjechały — to są pliki, które różnią się,
bo różnią się moduły: `trading-mcp` ma 86-linijkową taksonomię błędów, bo odróżnia odmowę
providera od awarii dostępu; `market-mcp` ma 13, bo jego odmowa ma jeden kształt. Wspólny
pakiet nad nimi byłby dokładnie tą „wspólną klasą bazową, która po cichu ogranicza cztery
moduły" — rzeczą, przed którą przestrzega `docs/architecture.md` i której ta zmiana **nie**
podważa.

**Rozważone alternatywy:**

- *Trzy pakiety, `tc-mcp-kit` chudy (`network_identity` + `_detail` + skrypt kontraktu).*
  Zaleta: moduły nie-MCP nie ciągną zależności MCP. Odrzucone, bo `network_identity.py` nie
  ma zależności MCP — to zwykły ASGI middleware, a `_detail` to `httpx`. Trzeci pakiet na
  ~150 linii kosztowałby więcej w `pyproject.toml` siedmiu modułów, niż oszczędza.
- *Trzy pakiety i sprowadzenie rozbieżnych plików do wspólnego kształtu.* Największy zysk w
  liczbach i jedyna droga do `tc-mcp-kit` w kształcie z planu. Odrzucone: to jest wymuszona
  abstrakcja nad plikami zmierzonymi jako różne w 65–92%, czyli zamiana kosztu widocznego w
  diffie na coupling, którego żaden kontrakt nie zapisuje. Reguła, którą tu łamiemy, dotyczy
  transportu poprawek — nie jest zaproszeniem do scalania wszystkiego, co ma tę samą nazwę.

### D2. Próg podziału to pomiar, nie nazwa pliku

**Decyzja:** do pakietu trafia to, co ma ≥ 70% wspólnych linii z drugą kopią **i** czego
różnica daje się wyrazić parametrem, a nie gałęzią `if module == ...`.

**Dlaczego:** obie połówki są potrzebne. Sam próg wpuściłby `__main__.py` przy 66,7%
(teams-mcp ↔ trading-mcp), gdzie różnica to inny moduł serwera — parametr uczciwy. Sam „daje
się sparametryzować" wpuściłby `config.py`, gdzie da się wszystko, tylko wynik ma siedem
przełączników. Konkretnie: `db.py` wchodzi, bo jedyna różnica agent ↔ teams to stała klucza
advisory locka (8030 / 8050) — to jest argument funkcji. `market-data/db.py` **nie** wchodzi,
mimo tej samej nazwy.

**Rozważona alternatywa:** przenosić plik, gdy ma tę samą nazwę w dwóch modułach. Odrzucone
przez ten sam pomiar — `config.py` istnieje we wszystkich siedmiu i jest zbieżny w 48,9%.

### D3. Zapiekany w obraz, nie instalowany z rejestru

**Decyzja:** pakiet jako zależność **ścieżkowa** w `[tool.uv.sources]` każdego konsumenta —
**bez** `uv workspace`. Dockerfile kopiuje `packages/` przed `uv sync`. Żadnej publikacji do
rejestru, żadnego wersjonowania semantycznego, żadnego kroku wydania.

*Poprawione 18 sierpnia 2026, przy wdrożeniu grupy 1.* Pierwotnie stało tu „uv workspace w
katalogu głównym, pakiety jako path-owe zależności" — dwie rzeczy naraz, i ta pierwsza była
błędem. Workspace w uv zwija wszystkich członków do **jednego** `uv.lock` w katalogu
głównym; siedem modułów ma dziś siedem własnych locków, a wspólny znaczyłby, że podbicie
zależności w jednym module re-rozwiązuje pozostałe sześć, a konflikt wersji między dwoma
modułami blokuje oba. To jest dokładnie ten rodzaj sprzężenia, którego ta zmiana miała
**nie** wprowadzać. Sama zależność ścieżkowa daje całe dzielenie kodu i zostawia każdemu
modułowi jego własny lock — sprawdzone: po wpięciu `tc-runtime` agent nadal ma swój
`uv.lock` i sam go rozwiązuje.

**Dlaczego:** cały koszt reguły, którą łamiemy, brał się z ręcznego transportu — nie z
istnienia rejestru. Wersjonowanie wprowadziłoby to, czego reguła się bała, tylko z drugiej
strony: moduł zostający na starej wersji pakietu to dryf z numerem. Zapieczenie przy buildzie
daje jedną wersję prawdy w repozytorium i osobny obraz na moduł.

**Rozważone alternatywy:** publikować pakiety do prywatnego rejestru i przypinać wersje —
odrzucone jako aparat dla organizacji z wieloma zespołami i wieloma repozytoriami; tu jest
jeden operator i jedno repo. Oraz `uv workspace`, odrzucony z powodu wspólnego locka
opisanego wyżej.

**Skutek uboczny, którego propozycja nie przewidziała.** Zależność ścieżkowa prowadzi poza
katalog modułu, więc kontekst builda obrazu musi być katalogiem głównym repozytorium, a nie
katalogiem modułu. To znaczy: `context: .` i `file: modules/<x>/Dockerfile` w każdym
`deploy-*.yml` konsumenta, przepisane ścieżki `COPY`, oraz `.dockerignore` w rootcie, żeby
kontekstem nie stało się każde `.venv` w drzewie. Obraz odwzorowuje układ repozytorium
(`/app/packages`, `/app/modules/<x>`), bo ścieżka w `pyproject.toml` jest względna wobec
repozytorium i spłaszczony obraz musiałby ją przepisywać — czyli mieć drugie miejsce, w
którym te dwie rzeczy mogą się rozjechać.

### D4. `market-data` bierze `tc-runtime` częściowo

**Decyzja:** `market-data` bierze `migrate.py` i `schema_version.py` z pakietu, a `db.py`
zostawia u siebie. Nie zmuszamy go do wspólnego `db.py` ani nie odbieramy mu dwóch pozostałych.

**Dlaczego:** pomiar. 83,6% i 83,3% to bliźniaki; 56,2% to nie. Konsument pakietu bierze z
niego to, co u niego jest kopią — pakiet nie jest paczką „wszystko albo nic". To także test
projektu pakietu: jeśli `migrate.py` da się wziąć bez `db.py`, moduły są sprzężone luźno.

### D5. Job `packages` w CI odpala testy wszystkich zależnych

**Decyzja:** zmiana pod `packages/` ustawia `true` dla filtra **każdego** modułu, który
deklaruje zależność od zmienionego pakietu.

**Dlaczego:** bez tego zamieniamy dryf, który jest widoczny w diffie, na regresję, która nie
jest widoczna nigdzie. To ta sama myśl, która stoi za istniejącymi filtrami: `market-mcp`
biegnie, gdy rusza się `market_data/contract.py`, bo trzyma jego snapshot. Tu zależność jest
mocniejsza, bo dosłowna.

## Risks / Trade-offs

**Poprawka w pakiecie psuje moduł, o którym autor nie myślał** → job `packages` (D5) odpala
testy wszystkich zależnych, a nie tych z diffa. To jest cała cena, którą płacimy za
współdzielenie, i płacimy ją w CI, nie na produkcji.

**Pakiet staje się wysypiskiem — trafia do niego wszystko, co ma tę samą nazwę** → D2 daje
próg mierzalny, a nie uznaniowy, i ten sam skrypt pomiarowy zostaje w repo, żeby dało się
powtórzyć pomiar przy każdym kandydacie.

**Moduł przestaje dać się skasować przez usunięcie katalogu** — `docs/architecture.md` obiecuje
dziś dokładnie to → obietnica zostaje, w węższej formie: skasowanie modułu usuwa jego katalog
i wpis z workspace'u; pakiet zostaje, jeśli ma innego konsumenta, i znika razem z ostatnim. To
jest zmiana, którą trzeba **zapisać** w nowej regule, nie przemilczeć.

**Migracja siedmiu modułów naraz to jeden wielki PR** → `tasks.md` prowadzi ją modułami:
`tc-runtime` powstaje z jednym konsumentem i dopiero potem przychodzą pozostali. Każdy krok
zostawia repo z przechodzącymi testami.

**Advisory lock po sparametryzowaniu klucza dostaje złą wartość** → klucz zostaje stałą
**modułu**, przekazywaną przy wywołaniu; test w każdym module asercuje, że jego wartość jest
tą, którą był (8030 / 8050 / market-data). Klucz kolidujący między modułami zablokowałby
migracje dwóch baz naraz, więc to jest dokładnie ten tryb awarii, który zasada nr 5 każe
przetestować.

## Migration Plan

1. `packages/tc-runtime` powstaje z **jednym** konsumentem (`agent`), z testami pakietu
   przeniesionymi z testów agenta. `teams` i `market-data` dochodzą osobno.
2. `packages/tc-openai` po `tc-runtime`, bo `provider.py` jest jedynym plikiem, którego dwa
   warianty wejścia trzeba zaprojektować, a nie tylko przenieść.
3. Moduły MCP na końcu — biorą z `tc-runtime` tylko middleware tożsamości i `_detail`.
4. Dokumentacja (`docs/architecture.md`, `CLAUDE.md`, README) **w tym samym PR co pierwszy
   pakiet**, nie na końcu: przez cały czas trwania migracji reguła w repo ma być prawdziwa.

**Wycofanie.** Na każdym etapie: przywrócić plik w module z historii gita i usunąć zależność
z jego `pyproject.toml`. Pakiet zostaje dla pozostałych konsumentów. Nic nie jest wdrożone
inaczej niż dotąd, więc wycofanie nie dotyka produkcji — obraz po prostu wraca do poprzedniej
zawartości.

## Open Questions

- Czy `market-data` docelowo bierze też wspólny `db.py`. Odpowiedź wymaga rozstrzygnięcia, czy
  trzydziestominutowe okno migracji da się wyrazić parametrem, czy jest własnością tego modułu
  — a to widać dopiero, gdy `tc-runtime/db.py` obsłuży dwóch konsumentów. Odłożone bezpiecznie:
  D4 mówi, że `market-data` bierze pakiet częściowo, więc odpowiedź „nie" nie zmienia niczego
  w zadaniach.
