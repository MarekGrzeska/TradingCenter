## Context

Motywacja w proposal.md, a cztery poziomy języka i decyzje operatora w `docs/strategie-i-backtesty-research.html`
(sekcje 10 i 12). Ograniczenia, które kształtują podejście:

- Pakiet workbencha nie importuje innego pakietu (`tests/test_layering.py`). Świece i wskaźniki z `/market` czyta
  się przez REST w procesie (`tc_runtime.caller_access.in_process`).
- Archiwum trzyma stronę bid. `MINUTE` jest źródłem rozdzielczości M5–H4 i włącza się ją per instrument. Katalog
  wskaźników to dane, a nowy wpis jest jednym plikiem w `market_data/indicators/catalogue/`. Wskaźniki liczy się
  na serii archiwum (bez parametru źródła), a odpowiedź `POST /market/indicators` niesie `warmup_bars` i
  `settled`.
- `deploy/postgres/ensure-databases.sh` przy każdym wdrożeniu wykonuje `retire strategy`, czyli usuwa bazę i rolę
  o tej nazwie. `scripts/dev.py` trzyma `STRATEGY_DATABASE_URL` i trzy inne `STRATEGY_*` w `RETIRED_SETTINGS`.
  Lokalne kontenery mogą mieć jeszcze starą bazę `strategy` z `alembic_version` = `0005` (review
  `remove-strategy-platform`).
- Workbench ma `numpy>=2.0`. Na serwerze budżet połączeń to 60 (`scripts/tests/test_pool_budget.py`).

## Goals / Non-Goals

**Goals:**
- Silnik, którego nie trzeba ruszać, żeby dodać strategię albo wskaźnik.
- Backtest wieloletniej serii minutowej w minutach, nie w godzinach, bez wpływu na resztę procesu.
- Każda liczba w raporcie da się odtworzyć i wyjaśnić.

**Non-Goals:**
- Szybkość wystarczająca do przeszukiwania tysięcy wariantów (etap 3 zdecyduje, czy potrzeba ścieżki wektorowej
  także dla stanu).
- Wskaźnik liczony z dowolnej formuły (np. EMA z RSI). Katalog liczy na serii archiwum, a własne funkcje okien
  języka (`average`, `highest` …) pokrywają tylko proste przypadki.
- Przeliczanie walut i wielkości kontraktu (D6).

## Decisions

### D1. Nazwa `strategies`, nie `strategy`, i klucz blokady 8130

Pakiet, prefiks, baza, rola i ustawienia nazywają się `strategies` / `STRATEGIES_*`, a migracje biegną pod
kluczem 8130 (następny wolny numer po 8120 alertów, bo pakiet nigdy nie miał portu).

*Odrzucone: powrót do `strategy`.* Wymagałby usunięcia `retire strategy` (inaczej wdrożenie kasowałoby nową bazę,
bo `retire` biegnie po `ensure`), wyjęcia czterech nazw z `RETIRED_SETTINGS` (zmienia ich znaczenie dla
nieaktualnych `.env`) i lokalnego `docker compose down -v`, bo nowy łańcuch Alembic nie zna rewizji `0005` w
starej bazie. Trzy pułapki w zamian za ładniejszą nazwę.

### D2. Formuły w składni wyrażeń Pythona, parsowane przez `ast` z białą listą

`ast.parse(..., mode="eval")`, potem przejście po drzewie z białą listą typów węzłów. Wszystko inne jest odmową.
Tekst nie dotyka `eval`, `exec` ani `compile`. `close[1]` to `Subscript`, `close @ HOUR_4` to `BinOp(MatMult)`,
a łańcuchowe porównania są natywne. Zero zależności, a składnię zna każdy model, który w etapie 2 będzie pisał
dokumenty. Długość formuły i głębokość drzewa mają sufit, żeby samo parsowanie nie stało się kosztem.

*Odrzucone:* własna gramatyka (Lark), bo to nowa zależność i składnia, której modele nie znają. CEL, bo jest
projektowany pod warunki na pojedynczych wartościach, a serie, przesunięcia i interwały trzeba by do niego
doklejać. Starlark, bo to już programy (poziom L4) i wymaga piaskownicy.

### D3. Wskaźniki tylko z `/market`, przez REST w procesie

Każde wywołanie wskaźnika katalogu w dokumencie staje się jednym `POST /market/indicators` dla
(symbol, rozdzielczość) jego kontekstu. Lista funkcji katalogu w walidatorze i w `GET /language` pochodzi z
`GET /market/indicators`, czytanego przy każdej walidacji (katalog jest mały). Dzięki temu nowy wpis działa bez
zmiany pakietu. Funkcje własne języka (okna, zdarzenia, czas) są semantyką języka, nie wskaźnikami, i liczy je
silnik.

*Odrzucone:* przeniesienie jądra wskaźników do `packages/` (zmiana zasady nośnej, osobna decyzja) i własna kopia
matematyki (dwie odpowiedzi na jedno pytanie, które rozjadą się przy pierwszej poprawce).

### D4. Dwie fazy ewaluacji: wektorowo bez stanu, świeca po świecy ze stanem

Formuły, które nie odwołują się do stanu pozycji ani historii transakcji, liczy się na numpy dla całej osi naraz:
przesunięcia są nieujemne, okna patrzą wstecz, a dopasowanie innej serii to wyszukanie ostatniego punktu z
chwilą dostępności ≤ *t* (`searchsorted`). Formuły ze stanem (wyjścia, `losses_in_row` w limitach) interpreter
liczy w pętli brokera, na bieżącym barze, czytając gotowe kolumny pierwszej fazy. Wymaganie „naraz = świeca po
świecy” ze `strategies-backtest` jest testem tego podziału.

*Odrzucone:* czysty interpreter świeca po świecy (prosty, ale setki tysięcy świec × dziesiątki węzłów w Pythonie
to dziesiątki sekund na jedno uruchomienie, a etap 3 mnoży uruchomienia) oraz czysto wektorowy silnik (nie
wyrazi stanu pozycji, trailingu ani stopu dnia).

### D5. Dane czytane w procesie, liczenie w osobnym procesie roboczym

Część asynchroniczna czyta serie z `/market` w miesięcznych porcjach, składa tablice i oddaje je razem ze
sprawdzonym drzewem dokumentu do `ProcessPoolExecutor` (liczba robotników = `STRATEGIES_RUN_CONCURRENCY`,
domyślnie 1). Robotnik nie ma połączenia z bazą ani klienta HTTP: dostaje tablice, oddaje transakcje i metryki.
Zapis raportu i transakcji robi znów część asynchroniczna. Robotnik to ten sam obraz, ta sama tożsamość i ta sama
granica bezpieczeństwa, a nie nowy proces w rozumieniu „jeden proces na granicę”.

*Odrzucone:* `asyncio.to_thread` (liczenie w czystym Pythonie pod GIL dławi pętlę zdarzeń, która serwuje strumień
świec i rozmowę), osobna usługa w Compose (nowa jednostka wdrożenia dla zadania, które mieści się w procesie) i
sama komenda CLI jak w starej platformie (odcina terminal i agenta etapu 2).

### D6. Pieniądz nominalny: 1 jednostka × 1 punkt = 1 jednostka kapitału

Silnik nie zna wielkości kontraktu ani waluty instrumentu. Raport liczy pieniądz jako jednostki × punkty i mówi to
wprost. Główną jednostką jest R, które od tego założenia nie zależy. Pobieranie specyfikacji instrumentu z bramy
wymagałoby drogi do niej, a pakiet celowo żadnej nie ma.

### D7. Stop jest obowiązkowy

R potrzebuje mianownika. Strategia „bez stopu” zapisuje stop szeroki. *Odrzucone:* raport tylko w pieniądzu dla
strategii bez stopu, czyli dwa rodzaje raportów i porównania, które nie mają wspólnej jednostki.

### D8. Złote strategie na danych syntetycznych z ziarna

Generator świec z ziarnem (kod w testach, nie plik danych), kilka dokumentów referencyjnych pokrywających
konstrukcje języka, typy zleceń, luki, rozstrzygnięcia pesymistyczne i finansowanie, oraz zapisane wyniki z
`engine_version`. Odpowiedzi `/market/indicators` dla tych danych są zapisanym nagraniem (dubel na transporcie).
Skrypt regenerujący odmawia nadpisania wyników, jeśli `ENGINE_VERSION` nie wzrosła względem zapisanej.

*Odrzucone:* wycinek prawdziwego archiwum w repo (megabajty danych dostawcy w historii gita, a regresja semantyki
silnika nie potrzebuje prawdziwego rynku).

## Risks / Trade-offs

- [Język okaże się za ciasny] → `notes` i odmowy walidatora pokazują, czego brakuje. Lista przykładów, których
  nie da się zapisać, jest wkładem do decyzji o L4 albo o nowej funkcji, a nie powodem do furtki w L3.
- [Luka w białej liście] → test na każdy typ węzła `ast` spoza listy, sufit długości i głębokości, brak `eval`
  sprawdzany testem odczytującym źródło pakietu pod kątem wywołań wykonujących kod.
- [Duży odczyt z `/market` przy każdym uruchomieniu] → porcje miesięczne, `db-cost-check` dla odczytu świec i
  wskaźników na roku `MINUTE`, limit świec na uruchomienie, jedno uruchomienie naraz. Pamięć podręczna serii
  dopiero, gdy pomiar etapu 3 tego zażąda.
- [Dane archiwum zmieniają się pod spodem (dosypane luki)] → odcisk danych w raporcie wyjaśnia różnicę dwóch
  uruchomień.
- [Wyniki M1 mniej pewne] → licznik rozstrzygnięć pesymistycznych w raporcie. Model nie udaje ticków, których nie
  ma.
- [`retire strategy` zostaje w skrypcie] → D1. Test w `scripts/tests` sprawdza, że żadna nazwa z `ensure` nie
  jest też w `retire`.
- [Skrypty kopii instaluje tylko Ansible] → znane z review `remove-strategy-platform`. Zadanie wdrożeniowe
  instaluje oba ręcznie albo przez Ansible i to sprawdza.

## Migration Plan

1. Przed merge: `STRATEGIES_DB_PASSWORD` w środowisku GitHub `vps` (`deploy/scripts/fill-github-environment.sh`).
   Bez tego deploy zatrzyma się na `env.required`, zanim cokolwiek wyśle.
2. Merge = wdrożenie: `ensure strategies` tworzy bazę i rolę, Compose ustawia `STRATEGIES_DATABASE_URL`, a pakiet
   migruje w swoim lifespanie pod kluczem 8130. `deploy.sh` czeka na zdrowe kontenery i w razie czego cofa obrazy.
3. Po wdrożeniu: skill `deploy-watch`. `backup.sh` i `backup-check.sh` z `strategies` na liście zainstalowane na
   serwerze, a następny nocny zrzut sprawdzony.
4. Wycofanie: poprzednie obrazy. Pusta baza `strategies` nikomu nie przeszkadza, a usunięcie jej to osobna decyzja.

Lista aplikacji `STRATEGIES_REST_CALLER_APPLICATION_IDS` na serwerze to na razie identyfikator terminala (ekran
przyjdzie w etapie 2). Dopisanie aplikacji `az` operatora, żeby wołać REST przed etapem 2, to wybór konfiguracji,
nie zmiana tej propozycji.

## Open Questions

- Domyślne limity (`STRATEGIES_MAX_MINUTE_BARS`, czas uruchomienia, liczba powtórzeń losowego wejścia) ustali
  pomiar na danych dev w zadaniu 4.x. Wartość nie zmienia wymagań, które mówią tylko, że limity istnieją i są
  nazwane w odmowie.
