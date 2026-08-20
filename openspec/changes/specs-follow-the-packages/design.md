## Context

`packages/` istnieje od `packages-replace-the-hand-copies` i nie ma w `openspec/specs/`
ani jednego wpisu. To nie była decyzja — nikt jej nie zapisał. Wynikało to z reguły, którą
repo miało wcześniej i która brzmiała prosto: **zdolność należy do modułu, bo moduł jest
tym, co się wdraża**. Pakiet nie jest wdrażany, więc nie miał czego opisywać.

Pomiar pokazuje, co ta reguła kosztowała: dziewięć wymagań o bazie i migracjach stoi
w trzech speckach naraz, `agent-database-connection` i `teams-database-connection` mają
listę identyczną nazwa w nazwę, a kod, który je wszystkie spełnia, jest jeden i leży
w `tc-runtime`. Wymaganie w trzech egzemplarzach to ta sama klasa awarii, którą repo już
raz nazwało po imieniu przy testach: **poprawka podróżuje kopiowaniem**.

## Goals / Non-Goals

**Cel:** każde wymaganie postawione raz, w miejscu, gdzie stoi kod, który je spełnia.

**Nie-cel:** mniej plików. Liczba specek po tej zmianie jest w przybliżeniu ta sama
i to jest w porządku — mierzone jest powtórzenie, nie objętość.

**Nie-cel:** ruszanie treści. Żadne wymaganie nie zmienia sensu, żaden scenariusz nie
zmienia nazwy.

## Decisions

### Pakiet dostaje własną zdolność w `openspec/specs/`

Trzy nowe specki z przedrostkiem nazwy pakietu: `tc-runtime-database-connection`,
`tc-runtime-browser-access`, `tc-mcp-kit-tool-surface`.

**Dlaczego to nie łamie „no module imports another module".** Ta reguła jest o *runtime*
i nie zmienia się tu ani o literę. Pakiet już dziś jest zależnością build-time pod trzema
warunkami, które `docs/architecture.md` wylicza, i jednym z tych warunków jest: *„every
consumer's tests running on every change to the package"*. Specka pakietu jest tym samym
zdaniem o wymaganiach: skoro zmiana pakietu musi przejść testy każdego konsumenta, to
wymaganie, które pakiet spełnia, jest wspólne i ma jedno miejsce.

**Dlaczego przedrostek nazwy pakietu, a nie osobny katalog.** OpenSpec adresuje zdolności
płaską nazwą i tak działa `--strict`; katalog `openspec/specs/packages/` byłby nową
konwencją do obsłużenia w narzędziu, żeby powiedzieć to, co przedrostek mówi bez zmian.

### Konsument zatrzymuje najwyżej jedno wymaganie o sparowaniu

Nie zero. Specka pakietu mówi, że mechanizm jest poprawny; nie mówi, że ten moduł go
naprawdę używa — a to jest osobny fakt i osobny tryb awarii. `market-data` może przestać
wołać `tc_runtime.migrate` i wszystkie dziewięć wymagań pakietu nadal będzie spełnionych,
podczas gdy moduł nie zmigruje.

To jest dokładnie ta sama para, którą repo już przyjęło dla testów: pakiet testowany raz,
konsument dostaje **jeden** test integracyjny, że prawdziwe sparowanie działa.

### Odrzucone: jeden moduł jako „właściciel" wymagania

Postawić dziewięć wymagań w `market-data-database-connection` i kazać pozostałym dwóm
wskazywać na nie prozą.

Odrzucone, bo to jest ta sama duplikacja z dodatkową nieprawdą: `market-data` nie jest
właścicielem tego mechanizmu, tylko jednym z trzech konsumentów, i skasowanie tego modułu
zabrałoby wymagania obowiązujące dwa inne. Wybór właściciela byłby arbitralny i przetrwałby
tylko do pierwszego usunięcia modułu — a to repo usunęło w tym tygodniu dwa.

### Odrzucone: zostawić jak jest, zapisać powód

Legalny wynik i został poważnie rozważony, bo tak skończyło C. Odrzucony, bo tu pomiar
wypada w drugą stronę: przy C stosunek zysku do kosztu wyszedł 1,4 : 1 i doszły trzy ceny,
których liczby nie pokazywały. Tu koszt jest jednorazowy i wyłącznie w prozie, żaden kod
nie drgnie, a tryb awarii jest udokumentowany w tym repo z datami — poprawka wchodzi do
jednej kopii z trzech.

### Odrzucone: „per moduł", czyli to, co zapowiadała karta D

Pięć plików, z czego terminal 3 168 linii i workbench 3 573. Odrzucone na własnym pomiarze
karty: obiecywała tańszą sesję agenta, a specki nie wchodzą do kontekstu sesji. Zysk był
zaadresowany do niewłaściwego kosztu.

## Risks / Trade-offs

**Nazwa scenariusza zmieniona przez pomyłkę blokuje archiwizację** — to jest ryzyko
operacyjne tej zmiany i jedyne poważne. Przeciwdziałanie jest mechaniczne, nie staranne:
zliczenie nazw wymagań i scenariuszy przed i po, z warunkiem, że **zbiór nazw jest
identyczny**, a zmienia się wyłącznie krotność. Wpisane w `tasks.md` jako krok, nie jako
zalecenie.

**Wymaganie może zgubić kontekst modułu.** „Migruje dokładnie jeden proces naraz" czyta się
inaczej przy `market-data`, gdzie stawką jest największa tabela w repo i 1500 sekund
czekania, niż przy workbenchu z dwoma łańcuchami po 300. Przeciwdziałanie: liczby, które są
modułu, zostają w specce modułu; wymaganie pakietu mówi o mechanizmie, nie o wartościach.

**`packages/` zyskuje kategorię, której nie miał**, więc następny pakiet będzie miał pytanie
„czy pisać speckę". Odpowiedź, którą ta zmiana ustanawia: wtedy i tylko wtedy, gdy pakiet
spełnia wymaganie, które inaczej stałoby u każdego konsumenta osobno. `tc-openai` bierze
dziś jeden konsument, więc specki nie dostaje — i to jest test tej reguły, nie wyjątek od niej.

## Migration Plan

Bez migracji danych. Kolejność w `tasks.md` ma jeden warunek: specka pakietu powstaje
**przed** odchudzeniem pierwszego konsumenta, żeby żadna nazwa wymagania nie zniknęła
z korpusu nawet na jeden commit.

## Open Questions

Czy `workbench-database-connection` ma być jedną zdolnością, czy dwiema — proces ma dwa
łańcuchy migracji, dwie bazy i dwa klucze blokady. Propozycja mówi: jedną, bo dwa łańcuchy
są dwiema wartościami tego samego wymagania, a nie dwoma wymaganiami. Do rozstrzygnięcia
przy pisaniu, gdy będzie widać, ile scenariuszy naprawdę różni się między `agent` a `teams`.
