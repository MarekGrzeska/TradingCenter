# Design — a-strategy-can-be-clicked-together

## Context

Motywacja w proposal.md. Ta sekcja notuje wyłącznie stan zastany, który kształtuje kształt
rozwiązania:

- `StrategySpec` już jest kontraktem wpisu: fakty z odwołaniami do własnych parametrów,
  parametry z zakresami, `evaluate` jako zwykła funkcja. Nic w runtime nie wie, skąd wpis
  pochodzi — czyta się to najlepiej w `tests/test_layering.py`, które zabrania runtime'owi
  nazwać wpis po imieniu.
- Katalog wskaźników market-daty ogłasza na drucie `params` z `min`/`max`/`default` oraz
  `lines` z kluczami (`IndicatorCatalogueEntryOut`). To jest gotowe źródło tego, co da się
  wyklikać; **żadna zmiana po stronie archiwum nie jest potrzebna** i to jest nietrywialny
  fakt, bo bez niego ta zmiana ciągnęłaby za sobą drugi moduł.
- Zespoły w workbenchu odrzucają definicję w chwili zapisu (`teams/validation.py`) i trzymają
  niezmienne rewizje (`team_revisions.definition` jako JSONB). Ten sam kształt, ta sama
  racja — nie ma powodu wymyślać drugiego.
- `parameter_sets` są już append-only, a decyzja już nazywa wersję parametrów. Brakuje
  drugiej połowy pochodzenia, nie całości.

## Goals / Non-Goals

**Goals:**

- Reguła, którą operator składa na ekranie, przechodzi przez tę samą pętlę, ten sam zapis
  i ten sam backtest co wpis kodowy — bez gałęzi „jeżeli wyklikana".
- Pytanie „czemu to weszło" ma odpowiedź złożoną z trzech niezmiennych rzeczy: rewizji
  reguły, wersji parametrów i snapshotu faktów.
- Interpreter tak samo czysty i tak samo deterministyczny jak ręcznie napisane `evaluate`,
  sprawdzone testem, nie deklaracją.

**Non-Goals:**

- Język ogólnego przeznaczenia. Wszystko, czego nie potrzebują baseline i pierwsza strategia
  SMC, jest poza zakresem — dokładanie węzła jest tanie, odbieranie go nie.
- Strojenie parametrów przez maszynę (sweep, optymalizacja). Backtest umie porównać rewizje;
  wybór należy do operatora.
- Wykonanie na koncie, w każdym trybie. Bez zmian i bez wyjątków.
- Import definicji z pliku albo z modelu. Reguła powstaje na ekranie albo w kodzie.

## Decisions

**1. Decyzja nr 1 z `a-strategy-is-a-catalogue-entry` zostaje odwrócona w połowie: wpis
pochodzi z obrazu albo z rewizji w bazie.** Tamten zapis brzmiał „wpis strategii jest kodem
w obrazie; w bazie są tylko parametry", a uzasadnieniem było, że interpreter i tak jest
kodem do wdrożenia. Co się zmieniło: nic w samym fakcie — interpreter faktycznie jest kodem
do wdrożenia — zmienia się rachunek. Interpreter wdraża się **raz**; strategia jako kod
wdraża się **za każdym razem**. Tamta decyzja porównała koszt jednorazowy z kosztem
jednostkowym, i przy jednej strategii w katalogu ta pomyłka nic nie kosztowała.

Drugie zdanie tamtej decyzji — „strategia bez przejrzanego kodu nie powinna istnieć" —
zostaje w mocy jako wymaganie, a zmienia się to, co je spełnia. Reguła wyklikana nie
przechodzi review i nigdy nie przejdzie, więc jego funkcję przejmują cztery rzeczy
wymienione w proposal.md. Ta lista **nie jest** retoryką: każda jej pozycja ma w tej zmianie
test albo już go miała.

**2. Reguła to typowane drzewo węzłów, nie tekst.** Odrzucone: język tekstowy z parserem
(lekser, gramatyka, komunikaty o błędach składni, runda tekst↔struktura w edytorze — wszystko
to jest kosztem, którego drzewo nie ma) oraz płaska lista warunków (nie wyraża arytmetyki
poziomów, a bez niej nie da się wyrazić nawet baseline'u, w którym `stop = close − k · ATR`).

Słownik węzłów jest zamknięty i wygląda tak:

| rodzaj | węzły |
|---|---|
| liczbowe liście | `const`, `param(name)`, `fact(key, line, offset)`, `bar(field, offset)` |
| liczbowe działania | `arith(+ − × ÷)`, `call(abs, min, max, round)` |
| liczbowa zmiana ramki | `previous(of)` |
| logiczne | `compare(< ≤ > ≥)`, `logic(all, any, not)`, `crossed(above/below)` |

`crossed` i `previous` działają jednym mechanizmem: środowisko ewaluacji niesie przesunięcie
ramki, a `fact`/`bar` dodają je do swojego `offset`. Dzięki temu `crossed_above(a, b)` to
dokładnie „`a` pod `b` o świecę wcześniej i nad `b` teraz", policzone z tych samych wyrażeń,
a nie z dwóch osobnych deklaracji, które mogą się rozjechać.

Definicja składa się z faktów, parametrów, **uporządkowanej listy bramek** (`when` + `reason`),
listy setupów (warunek, kierunek, poziomy, punktacja) oraz nazwanych cech. To odwzorowuje
jeden do jednego to, jak dziś czyta się `_evaluate` baseline'u — najtańsza i najczęstsza
odmowa pierwsza, każda z własnym powodem.

**3. Brak odczytu propaguje się logiką trójwartościową, a odmowa jest domknięta.** Każdy
węzeł liczbowy zwraca `float | None`, każdy logiczny `bool | None`; dowolny operand `None`
daje `None`, z wyjątkami Kleenego (`all` z jawnym fałszem jest fałszem, `any` z jawną prawdą
jest prawdą). Warunek, który wyszedł `None`, **odmawia** — nie „nie odmawia". To jest jedyny
bezpieczny kierunek dla systemu, który decyduje o pieniądzach, i jest to największa
pojedyncza wygrana interpretera nad ręcznym kodem: dziś każdy wpis musi sam napisać
`if None in (...)`, i pominięcie tego wygląda dokładnie jak przecięcie średnich, którego nie
było. Definicja niesie własny tekst `unsettled_reason`, bo „nie ustabilizowało się" znaczy co
innego dla średniej niż dla struktury.

**4. Interpreter jest `evaluate` jednego `StrategySpec`, a nie drugą ścieżką w pętli.**
`spec_from_rule(...)` buduje zwykły `StrategySpec`, którego `evaluate` to `partial(interpret,
rule)`. Runtime nie zyskuje żadnej gałęzi „jeżeli wyklikana"; zyskuje jeden resolver
w miejsce `catalogue.get`. Alternatywa — `if` w pętli i w backteście — kosztowałaby dokładnie
tę własność, o którą chodziło przy budowie platformy.

Czystość interpretera nie jest deklaracją: `tests/test_layering.py` obejmuje `rule.py`
i `interpreter.py` tą samą regułą, którą obejmuje wpisy katalogu (żadnego we/wy, żadnego
zegara, wolno znać wyłącznie kontrakt), a determinizm ma własny test na powtórzeniu.

**5. Wyklikana strategia ma zwykłe `strategy_id` — tekstowy identyfikator, nie nowy rodzaj
klucza.** `watches`, `decisions`, `parameter_sets` i cała powierzchnia MCP dalej pracują na
`strategy_id`. `strategy_definitions.strategy_id` jest unikalne i odrzucane, gdy koliduje
z identyfikatorem wpisu kodowego. Alternatywa — osobny wymiar „definicja" obok „strategii" —
rozlałaby się na sześć tabel i cztery powierzchnie po to, żeby wyrazić to samo.

**6. Zestaw parametrów należy do rewizji, nie do strategii.** Wartość dopuszczalna pod
rewizją N może być poza zakresem albo w ogóle nieznana pod N+1, a zestaw, którego nie da się
przypisać do deklaracji, jest liczbami bez znaczenia. Kolumna dochodzi jako nullowalna, bo
wpisy kodowe deklaracji w bazie nie mają. Zgodność (rewizja ↔ zestaw) jest wymuszana przy
zakładaniu obserwacji i przy backteście; dotychczasowa pobłażliwość `resolve_params` wobec
nieznanych kluczy zostaje wyłącznie przy odczycie starych zapisów, gdzie jest po to, żeby
stara decyzja dała się przeczytać.

**7. Obserwacja przypina rewizję, nie śledzi najnowszej.** Watch niesie
`strategy_revision_id`; zapisanie nowej rewizji **nie** zmienia tego, co liczy się na
produkcji. Odrzucone: tryb „zawsze najnowsza" wzorem harmonogramów zespołów — tam rewizja
zmienia sposób rozmowy, tu zmieniłaby regułę pod stopami działającej obserwacji, a decyzje
z obu stron tej chwili wyglądałyby na porównywalne. Przejście na nową rewizję jest osobnym,
jawnym ruchem (ten sam upsert, który dziś podmienia zestaw parametrów).

**8. Odmowa przy zapisie jest wygodą; sprawdzeniem właściwym zostaje moment zakładania
obserwacji.** Katalog archiwum może się zmienić między jednym a drugim, a `check_facts_are_
announced` świadomie nie żyje w imporcie, bo odpowiedź da się mieć tylko przez zapytanie.
Zostają oba. **Gdy archiwum nie odpowiada w chwili zapisu — zapis jest odrzucany**, a nie
przyjmowany jako „niezwalidowany": definicja, o której nie da się nic powiedzieć, jest
gorsza niż jej brak, a operator ma jeden ruch do wykonania. Koszt: konfigurator nie działa,
gdy archiwum leży. Przyjęty świadomie — bez archiwum i tak nie ma czego wyklikać, bo to jego
katalog wypełnia wybieraki.

**9. Co da się odrzucić statycznie, jest odrzucane przy zapisie; reszta zostaje odmową przy
świecy.** Statycznie: nieogłoszony wskaźnik, nieistniejąca linia, nieznany parametr
wskaźnika, wartość poza jego zakresem, **zakres własnego parametru szerszy niż zakres
parametru wskaźnika, na który wskazuje** (to jest ten check, którego brak wychodzi dopiero
odmową archiwum w środku nocy), nieznany klucz faktu, nieznany parametr strategii,
rozdzielczość spoza słownika, przekroczone sufity, pusty tekst powodu, setup bez poziomów.
Dynamicznie — i tak musi zostać: `entry == stop`, bo to wynik arytmetyki na odczytach,
i pilnuje tego `Decision.__post_init__`, który już istnieje.

**10. `baseline_ma_cross` zostaje kodem i dostaje bliźniaka-drzewo, spiętego testem złotym.**
Trzy powody, w kolejności rosnącej wagi: podłoga, którą można przestawić klikaniem, nie jest
podłogą; wpis kodowy liczy się bez odczytu z bazy, więc punkt odniesienia da się przeliczyć,
gdy nic nie stoi; a przede wszystkim — wyrażenie baseline'u jako drzewa i porównanie
decyzja-po-decyzji jest jedynym uczciwym testem, czy słownik węzłów jest dość wyrazisty
i czy interpreter liczy to, co się wydaje. Gdyby drzewo tego nie wyrażało, wiadomo to w dniu
pierwszym, a nie przy SMC.

**Jedna różnica między bliźniakami jest zamierzona i test ją nazywa:** wpis kodowy liczy
`extension_atr` tylko przy wejściu, bliźniak liczy cechy zawsze, więc jego odmowy niosą
o jedną cechę więcej. To jest kierunek „więcej informacji", a nie rozjazd logiki — test
wymaga równości akcji, powodu, rodzaju odmowy, poziomów i punktacji, oraz żeby cechy wpisu
kodowego były podzbiorem cech bliźniaka o tych samych wartościach.

**11. Backtest woła rewizję z bazy, ale ścieżka bez bazy zostaje.** `--revision N`
(domyślnie najnowsza), rewizja w raporcie i w `backtest_runs`. `compare()` **nie** odmawia
przy różnych rewizjach — zestawienie dwóch rewizji jednej definicji to główny powód, dla
którego ta komenda istnieje — ale raport rewizję drukuje, bo tabela bez tego jest
nieczytalna. Odmowy zostają tam, gdzie były: symbol, zakres, koszty. Komenda z wyklikaną
strategią wymaga bazy; z wpisem kodowym nie wymaga niczego poza archiwum, i to jest
utrzymane celowo.

## Risks / Trade-offs

- [Interpreter, który liczy „prawie" to samo co ręczny kod] → test złoty bliźniaka
  baseline'u decyzja po decyzji na tych samych faktach; różnica jest błędem, nie niuansem.
- [Wyklikana reguła bez review trafia na produkcję] → totalność języka, odmowa przy zapisie,
  brak drogi do konta, przypięta rewizja i wymóg pobicia baseline'u. Żadna z tych czterech
  nie jest wystarczająca sama.
- [Operator wyklikuje regułę czytającą czterdzieści wskaźników i zajeżdża archiwum] → sufity
  na liczbę faktów, węzłów i głębokość, odrzucane przy zapisie; pętla i tak czyta jednym
  zapytaniem na rozdzielczość.
- [Trzy niezmienne rzeczy zamiast jednej to trzy miejsca, w których pochodzenie może się
  rozjechać] → jeden test akceptacyjny na całość: odtworzenie zapisanej decyzji z jej
  rewizji, jej zestawu parametrów i jej snapshotu musi dać identyczną decyzję.
- [Konfigurator wymaga archiwum, którego może nie być] → świadomie (decyzja 8); komunikat
  mówi, czego brakuje, a nie „nie udało się zapisać".

## Migration Plan

Migracja 0003 jest wyłącznie addytywna: dwie nowe tabele i cztery nullowalne kolumny. Nie
przepisuje żadnego istniejącego wiersza, bo istniejące wiersze pochodzą od wpisów kodowych
i rewizji nie mają — `NULL` znaczy tu dokładnie to, co znaczy, i nie jest brakiem danych.

Wdrożenie zwykłe: moduł migruje własną bazę we własnym lifespanie pod blokadą 8080, jak
dotąd. Żadnego kroku operatora, żadnego apply — ta zmiana nie dotyka `infra/`, nie zakłada
tożsamości i nie zmienia listy dopuszczonych aplikacji.

Odwrót: definicji nie trzeba usuwać — wystarczy zatrzymać obserwacje, które je wskazują.
Wpisy kodowe pracują dalej bez zmian, bo nigdy nie przechodzą przez tabelę rewizji.

## Open Questions

- Czy `pending_setups` kiedykolwiek zacznie być pytane per rewizja. Dziś nie: wyzwalacz
  workbencha pyta „czy jest setup", a nie „czy jest setup pod rewizją 7", i agregacja po
  definicji jest tym, czego chce. Do rozstrzygnięcia, gdy pojawi się pierwsza definicja
  z dwiema rewizjami obserwowanymi jednocześnie.
- Czy zakres własnego parametru zawężony do zakresu wskaźnika powinien być poprawiany
  automatycznie zamiast odrzucany. Odrzucany, dopóki nie wiadomo, że to uwiera — cicha
  korekta zakresu to zmiana znaczenia definicji bez śladu.
