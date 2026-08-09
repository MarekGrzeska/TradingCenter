## Why

Terminal ma dziś dwie zakładki mówiące o instrumentach i żadna nie odpowiada na pytanie, które
operator zadaje naprawdę: **co archiwizujemy, od kiedy i w jakich interwałach**. `Instruments`
przegląda katalog providera — kilkaset pozycji, z których 99% nikogo nie interesuje — a `Archive`
trzyma listę par, gdzie ten sam instrument w czterech interwałach zajmuje cztery wiersze. Wykres
przyjmuje dowolny symbol wpisany z ręki i dopiero po fakcie mówi, że ta para nie jest zbierana.

Drugi brak jest cięższy. Dodanie pary to dziś jedno kliknięcie w ciemno: nie wiadomo, ile danych
zostanie ściągnięte ani ile to potrwa, głębokość jest globalną stałą (`default_backfill_bars`), a
kiedy uzupełnianie zawiedzie, jedynym śladem jest wiersz `last_fill` żyjący w pamięci procesu i
ginący przy restarcie. Nie ma jak ponowić nieudanego dociągnięcia bez zdjęcia i ponownego dodania
pary.

## What Changes

- **BREAKING** Zakładki `Instruments` i `Archive` łączą się w jedną, `Instruments`. Pokazuje
  wyłącznie instrumenty archiwizowane — jeden wiersz na instrument, wszystkie jego interwały w
  jednej kolumnie skrótem (`1m · 5m · 1h · 1D`), oraz od kiedy dane są zebrane — jedną datą, gdy
  wszystkie interwały sięgają równie daleko wstecz, i rozbitą na interwały, gdy nie. Przeglądarka
  katalogu providera znika jako osobny widok.
- Dodawanie instrumentów przestaje być formularzem, a staje się kreatorem: autocomplete klasy
  aktywów → autocomplete instrumentu w tej klasie → multiselect interwałów → data **OD**. Autocomplete
  powstaje jako jeden reużywalny komponent i obsługuje wszystkie trzy zastosowania w terminalu.
- Zakres to **wyłącznie data OD**; koniec jest zawsze „teraz", a para po dociągnięciu zbiera dalej
  na żywo. Data OD wcześniejsza niż historia providera MUST zostać przycięta do tego, co provider
  faktycznie ma — wpisanie roku 1850 znaczy „wszystko, co się da", a nie błąd walidacji.
- Zatwierdzenie kreatora **nie dodaje niczego od razu**. Otwiera dialog, który dla każdej pary
  (instrument × interwał) pokazuje przycięty zakres, szacowaną liczbę świec i szacowany rozmiar,
  z sumą na dole, i prosi o akceptację. Estymatę liczy `market-data` tym samym kodem, który
  następnie dzieli pracę na kawałki, więc dialog pokazuje dokładnie to, co zostanie wykonane.
- Akceptacja tworzy **zlecenie dociągania** — nowe pojęcie w `market-data`. Zlecenie dzieli się na
  kawałki (para × okno czasu), wykonywane po kolei pod istniejącym budżetem ruchu do gatewaya.
  Postęp zlecenia to ukończone kawałki wobec wszystkich, więc procent na ekranie jest mierzony,
  a nie zmyślony.
- Kawałek, który zawiedzie, **nie przerywa zlecenia**. Pozostałe kawałki lecą dalej, zlecenie kończy
  się stanem częściowym z nazwaną przyczyną, a ponowienie obejmuje wyłącznie kawałki nieudane.
- Historia zleceń i kawałków przenosi się do bazy `market-data` (nowa tabela, nowa migracja). Dziś
  `FillOutcome` żyje w pamięci i ginie przy restarcie, więc zakładka oparta na nim kłamałaby po
  każdym starcie modułu.
- Nowa zakładka terminala **Data History**: per instrument i per interwał — co i kiedy się
  dociągnęło, ile świec, jaki zakres, oraz stan. W toku pokazuje procent, po sukcesie zieloną
  informację o zakończeniu, po porażce przyczynę i przycisk ponowienia. Odpytuje co 10 s.
- **BREAKING** Na wykres trafiają wyłącznie instrumenty archiwizowane. Pole symbolu w slocie siatki
  przestaje być polem tekstowym i staje się autocomplete, którego jedynym źródłem jest lista
  archiwizowanych par.
- `capital-gateway` dostaje filtr katalogu po klasie aktywów, bo bez niego drugi autocomplete
  patrzyłby na katalog ucięty obchodem i pokazywał niepełną listę jako pełną.

## Capabilities

### New Capabilities

- `market-data-jobs`: zlecenia dociągania historii — czym jest zlecenie i kawałek, jak dzieli się
  praca, jak liczony jest postęp, co się dzieje z kawałkiem, który zawiódł, jak wygląda ponowienie
  i dlaczego ta historia jest trwała.
- `terminal-collection-history`: zakładka `Data History` — co operator widzi o dociąganiu per
  instrument i per interwał, jak często to się odświeża i skąd ponawia nieudane.

### Modified Capabilities

- `terminal-data-manager`: zakładka staje się jedynym miejscem mówiącym, co jest archiwizowane;
  wiersz opisuje instrument, a nie parę; dodawanie przechodzi przez kreator i dialog akceptacji
  zamiast formularza z jednym interwałem.
- `terminal-instruments`: wyszukiwanie instrumentu przestaje być osobnym widokiem katalogu i staje
  się reużywalnym autocomplete z kaskadą klasa aktywów → instrument; wynik wyszukiwania nie trafia
  już wprost do slotu siatki.
- `terminal-grid`: slot przyjmuje symbol wyłącznie z listy archiwizowanych instrumentów, wybierany
  z autocomplete zamiast wpisywany.
- `market-data-api`: kontrakt zyskuje estymatę zlecenia, tworzenie zlecenia dla wielu par naraz
  z datą OD, odczyt zleceń wraz z postępem oraz ponowienie nieudanych kawałków.
- `market-data-ingest`: uzupełnianie wstecz jest wykonywaniem kawałków zlecenia o zadanym oknie
  czasu, a nie pojedynczym fillem o głębokości z konfiguracji.
- `market-data-tracking`: śledzona para niesie moment, od którego historia ma być pokryta, a
  dodanie wielu par jest jedną decyzją operatora.
- `capital-market-data`: katalog instrumentów daje się zawęzić do jednej klasy aktywów i wyliczyć
  w tej klasie bez ucięcia.

## Impact

- **`modules/terminal`** — największa część zmiany. Nowy komponent autocomplete (`src/ui/`),
  przebudowa `src/instruments/` i skasowanie `src/archive/` jako osobnej zakładki, nowy katalog
  `src/history/`, zmiana `src/app/tabs.ts` (`archive` znika, `data-history` dochodzi),
  `src/grid/SymbolField.tsx` przestaje być polem tekstowym, rozszerzenie `src/data/archive.ts`
  i `src/data/source.ts` o zlecenia.
- **`modules/market-data`** — nowy moduł zleceń obok `ingest/`, przepisanie `ingest/backfill.py` na
  wykonywanie kawałków, rozszerzenie `tracking.py` o datę OD, nowe endpointy w `app.py`
  i modele w `contract.py`, **nowa migracja Alembic** na tabele zleceń i kawałków.
- **`modules/capital-gateway`** — parametr `asset_class` w `GET /instruments` oraz podniesiony
  pułap obchodu dla zapytania z filtrem (`adapter.list_instruments`).
- **Kontrakty** — `POST /pairs` zyskuje pole daty OD; stara postać żądania pozostaje ważna i znaczy
  „domyślna głębokość", więc konsument spoza terminala nie pęka.
- **Adres `/archive`** przestaje istnieć jako zakładka; wchodzące na niego zakładki przeglądarki
  trafią na stronę „nie ma takiej zakładki".
