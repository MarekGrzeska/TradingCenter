## Verdict

Wszystkie 38 zadań z `tasks.md` wykonane, ze stackiem uruchomionym i przeklikanym na Windows.
Siedem punktów z proposal.md dowiezione: liczba świec i objętość przez kontrakt, rozwinięcie
instrumentu przebudowane (dane + ostrzeżenie o lukach, bez pełnego zakresu), `forming` i wolumen
znikają z wykresu, interwały nazywają się jednakowo wszędzie, trzy puste zakładki i ich mechanizm
usunięte, cały terminal pokazuje czas w `Europe/Warsaw`. Podczas reviewu znaleziono i naprawiono
dwa błędy (test daty granicznej roku, układ rozwinięcia), a przy uruchamianiu stacku kolejne
cztery w skryptach `dev.*` — w tym jeden, który uniemożliwiał start na Windows w ogóle. Trzy luki
w pokryciu testami zostają otwarte świadomie — patrz Gaps; żadna nie dotyczy zachowania tego
changea, tylko brakującej infrastruktury testowej sprzed niego albo integracyjnego pokrycia
jednej już zweryfikowanej jednostkowo funkcji.

## Verified

`modules/market-data`:
- `uv run pytest -q` → 559 passed, 7 skipped, **1 failed**:
  `test_openapi.py::test_the_document_prints_with_no_environment_at_all` — środowiskowe
  (Windows, `WinError 10106` przy starcie procesu z okrojonym `PATH`), potwierdzone jako
  identyczne na niezmodyfikowanej gałęzi (`git stash` → ten sam wynik). Niezwiązane z tym changem.
- `uv run pytest -m db -q` → 321 passed, 7 skipped.
- `uv run ruff check .` → All checks passed.
- `uv run pyright` → 0 errors, 0 warnings, 0 informations.

`modules/terminal`:
- `pnpm typecheck` → czysto.
- `pnpm lint` → czysto.
- `pnpm contract:check` → Contract is up to date.
- `pnpm vitest run` → 300 passed, **4 failed** — wszystkie cztery to jedna i ta sama przyczyna:
  `Number.prototype.toLocaleString()` na tej maszynie domyślnie formatuje liczby po polsku
  (spacja jako separator tysięcy: `12 431`, nie `12,431`), a istniejące testy (sprzed tego
  changea) asertują amerykański format z przecinkiem. Potwierdzone jako identyczne na
  niezmodyfikowanej gałęzi. Niezwiązane z tym changem — CI używa `en-US` i tam te testy przechodzą.
  Nie naprawiane tutaj: to nie jest plik ani zachowanie, którego ten change dotyczy.

`./scripts/dev.ps1` — uruchomiony przez operatora na Windows, cały stack wstał, ręczne przejście
po zakładkach potwierdziło zmiany na ekranie: objętość per interwał w rozwinięciu, polskie daty
ze strefą, jednakowe nazwy interwałów, brak `forming`, brak wolumenu, brak trzech pustych
zakładek. Layout rozwinięcia poprawiony po tym przejściu — patrz Findings.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Low | `modules/terminal/src/instruments/AddInstrumentWizard.test.tsx:122` | Test „starts at the beginning of the current year" liczył oczekiwaną wartość z `new Date().getUTCFullYear()`, podczas gdy komponent po tym changu liczy domyślną datę z `todayInWarsaw()`. Przez godzinę–dwie każdego Sylwestra (gdy w Warszawie jest już 1 stycznia, a w UTC jeszcze 31 grudnia) test zgłosiłby fałszywą usterkę. | FIXED — test przeliczony na `todayInWarsaw()`, ten sam sposób, w jaki liczy to sam komponent. |
| Low | `modules/terminal/src/instruments/InstrumentsView.tsx` (`IntervalVolume`) | Pierwsza wersja rozwinięcia sklejała liczbę świec, objętość i datę w jeden ciąg tekstu; druga rozstrzeliła je przez `justify-between`, przez co nic nie trzymało pionu między interwałami i kolumny falowały. | FIXED — jeden `grid-cols-[2.5rem_7rem_4.5rem_1fr_auto]` wspólny dla każdego wiersza, liczby do prawej + `tabular-nums`. Wykryte dopiero na ekranie, nie w teście — testy sprawdzały treść, nie układ. |

### Znalezione przy uruchamianiu stacku

Nie należą do diffu samego changea (`scripts/**` nie jest ani specem, ani kontraktem, ani infrą),
ale zostały znalezione podczas weryfikacji task 8.2 i jadą na tej samej gałęzi.

| Severity | Where | Finding | Status |
|---|---|---|---|
| Medium | `scripts/dev.ps1:68` | `docker info *> $null` pod `$ErrorActionPreference = "Stop"` wywracał skrypt: PowerShell 5.1 opakowuje każdą linię stderr natywnego programu w `NativeCommandError`, a `-Stop` promuje ją do błędu terminującego **mimo** przekierowania do `$null`. Docker wypisuje na stderr nieszkodliwe `WARNING: No blkio throttle.read_bps_device support` — i to zabijało uruchomienie stacku, zanim skrypt zdążył stwierdzić, że demon działa. `dev.sh` nie miał tego problemu, bo `>/dev/null 2>&1` w bashu nie ma pojęcia strumieni PowerShella. | FIXED — `$ErrorActionPreference` zawężony do `SilentlyContinue` na czas tego jednego wywołania i przywrócony zaraz po. Zweryfikowane na żywo: exit 0, brak crasha. |
| Low | `scripts/dev.ps1:34` | Blok `param()` bez `[CmdletBinding()]` po cichu połykał nieznane flagi do `$args` i szedł dalej, więc literówka w nazwie opcji uruchamiała stack tak, jakby nic nie podano. `dev.sh` odmawia z `unknown option: … (try --help)`. | FIXED — dodany `[CmdletBinding()]`; nieznana flaga daje teraz `A parameter cannot be found that matches parameter name '…'`. |
| Low | `scripts/dev.ps1:83` | Brak fallbacku pnpm → npm, który `dev.sh` ma od początku: maszyna z samym npm dostawała odmowę zamiast działającego dev servera. | FIXED — ta sama logika co w `dev.sh`, wraz z komunikatem o instalacji dobranym do znalezionego menedżera. |
| Low | `scripts/dev.sh:249`, `scripts/dev.ps1:275` | Oba skrypty drukowały w „Ready" martwy link `…/archive` — zakładka zniknęła dawno temu, jej adres trafia dziś na stronę nieznanej zakładki. | FIXED — `Instruments panel …/instruments` w obu. |

Nic więcej nie znaleziono w diffie: obie strony (`market_data/tracking.py`, `contract.py`,
`routers/pairs.py`, `models.py`, `jobs/plan.py`; `InstrumentsView.tsx`, `Chart.tsx`,
`AddInstrumentWizard.tsx`, `GridView.tsx`, `CollectionHistoryView.tsx`, `App.tsx`, `tabs.ts`,
`formatTime.ts`, `resolutionLabel.ts`) przeczytane linia po linii przeciwko diffowi z punktu
rozgałęzienia.

## Spec coverage

### market-data-tracking — „Śledzone pary są wyliczalne wraz ze swoim stanem"

| Scenario | Proven by |
|---|---|
| Odczyt listy śledzonych par | `test_tracking.py::test_the_status_carries_the_newest_candle`, `::test_the_status_carries_the_oldest_candle`, `::test_status_carries_collect_from`, `::test_the_status_carries_the_candle_count` |
| Para, która nie zebrała jeszcze nic | `test_tracking.py::test_a_pair_that_has_collected_nothing_still_appears` (asertuje `candle_count == 0`, nie `count(*)`-owe 1) |
| Zamówiona głębokość jeszcze nieosiągnięta | `test_tracking.py::test_status_carries_collect_from` + `::test_the_status_carries_the_oldest_candle` |
| Zbieranie ustało po cichu | `test_tracking.py::test_the_status_reports_collection_stalled_when_the_market_is_open` |

### market-data-api — „Śledzone pary są zarządzalne przez kontrakt"

| Scenario | Proven by |
|---|---|
| Dodanie pary | `test_app.py::test_a_pair_can_be_taken_on_over_the_contract` |
| Odczyt listy z objętością danych | `test_app.py::test_the_list_carries_how_much_is_collected`, `::test_a_pair_with_nothing_collected_reports_zero_candles` |
| Dodanie wielu par jednym żądaniem | `test_app.py::test_adding_several_pairs_is_one_decision_with_one_job` |
| Jedna z par zostaje odrzucona | `test_app.py::test_a_multi_pair_request_refuses_one_without_losing_the_others` |
| Żądanie bez momentu początku | `test_app.py::test_a_pair_can_be_taken_on_over_the_contract` (brak `collect_from` w ciele) |
| Dodanie pary nieznanej providerowi | `test_app.py::test_a_symbol_the_gateway_will_not_serve_is_refused_with_the_reason` |
| Usunięcie pary | `test_app.py::test_a_pair_can_be_deleted_over_the_contract` |
| Skasowanie pary, która nie jest śledzona | `test_app.py::test_letting_go_of_a_pair_that_was_not_collected_is_a_404` |

### terminal-data-manager

| Scenario | Proven by |
|---|---|
| Przegląd listy | `InstrumentsView.test.tsx` › "puts every resolution of the same instrument in one row, abbreviated" |
| Instrument w wielu interwałach | tamże |
| Zbieranie ustało | `InstrumentsView.test.tsx` › "marks the row and the stalled interval out from the rest" |
| Pokrycie ciągłe | `InstrumentsView.test.tsx` › "says nothing about coverage when it is one continuous range" |
| Pokrycie z lukami | `InstrumentsView.test.tsx` › "names the gaps when coverage is more than one stretch" |
| Rozwinięcie instrumentu | `InstrumentsView.test.tsx` › "shows how many candles are collected, roughly how much they take, and since when" |
| Interwał bez zebranych danych | `InstrumentsView.test.tsx` › "names an interval that has collected nothing, rather than showing a zero" |
| Interwały sięgają różnie daleko | `InstrumentsView.test.tsx` › "gives each interval its own since, when they reach back different distances" |
| Objętości nie da się odczytać | `InstrumentsView.test.tsx` › "tells an unreachable archive apart from an empty one" (panel nie pokazuje wierszy w ogóle, więc zero nigdy nie jest odpowiedzią) |

### terminal-chart

| Scenario | Proven by |
|---|---|
| Kursor nad świecą | Brak dedykowanego testu symulującego hover krzyża — patrz Gaps (sprzed tego changea, nie wprowadzone przez niego). |
| Świeca z wolumenem od źródła | `Chart.test.tsx` › "never shows volume, even when the source carries one" |

### terminal-shell

| Scenario | Proven by |
|---|---|
| Dołożenie zakładki | `App.test.tsx` › "switching tabs updates both the content and the address" |
| Część terminala jeszcze nie istnieje | `App.test.tsx` › "sends the old placeholder addresses to the unknown-tab page, not a tab" |
| Wybór interwału na wykresie | `Chart.test.tsx` › "shows the terminal's own interval labels, never the wire's names" |
| Ten sam interwał w dwóch zakładkach | Wspólnie: `Chart.test.tsx` (jw.) i `InstrumentsView.test.tsx` (m1/h1/day/week w wierszu) — obie strony czytają ten sam `RESOLUTION_LABEL`, więc dwa niezależne testy tej samej stałej są dowodem zgodności; żaden pojedynczy test nie porównuje ich wprost side-by-side. |
| Oś czasu wykresu | Częściowo: `formatTime.test.ts` dowodzi, że `formatTickMark`/`formatCrosshairTime` liczą w `Europe/Warsaw` poprawnie. Samo podłączenie tych funkcji do `createChart`'s `timeScale.tickMarkFormatter`/`localization.timeFormatter` w `Chart.tsx` nie ma testu integracyjnego — patrz Gaps. |
| Terminal otwarty poza Polską | `formatTime.test.ts` › "crosses into the next Warsaw day before UTC does" (strefa jest wpisana na stałe w formatter, niezależnie od otoczenia) |
| Zmiana czasu letniego na zimowy | `formatTime.test.ts` › "shows CEST in summer" / "shows CET in winter" / `warsawMidnightEpochSeconds` zima/lato |
| Data podana przez operatora | `AddInstrumentWizard.test.tsx` › "reads the picked date as the start of that day in Warsaw, not in UTC" |

## Gaps

- **Kursor nad świecą** (`terminal-chart`) — nie ma testu symulującego zdarzenie krzyża
  (`subscribeCrosshairMove`) i sprawdzającego odczyt OHLC pod kursorem wprost. Test „follows the
  forming candle…" ćwiczy te same wartości pośrednio (przez najnowszy słupek, nie przez hover).
  Ten test istniał — a raczej nie istniał — przed tym changem; change usunął tylko wolumen z
  odczytu, nie dotykając testowej luki wokół samego hovera.
- **Oś czasu wykresu** (`terminal-shell`) — atrapa `createChart` w `Chart.test.tsx` odrzuca drugi
  argument (opcje), więc żaden test nie może dziś zweryfikować, że `Chart.tsx` rzeczywiście
  przekazuje `formatTickMark`/`formatCrosshairTime` do biblioteki. Formattery same są przetestowane
  w izolacji (`formatTime.test.ts`); brakuje testu spinającego je z komponentem. Rozszerzenie
  atrapy o przechwytywanie opcji wykracza poza zakres „kilku małych zmian" tego changea.
