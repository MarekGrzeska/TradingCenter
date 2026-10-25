## Context

Motywacja w proposal.md. Stan, który kształtuje podejście:

- Pakiet `strategies` z etapu 1 ma REST bez `/mcp` i bez narzędzi. `RevisionOut.author` zna już wartość `agent`, ale
  nic jej nie zapisuje. `report` w `RunOut` jest słownikiem bez kształtu, a dzienna krzywa kapitału liczy się w
  `reports.daily_equity` i przepada po policzeniu metryk.
- Narzędzia pakietów trafiają do rozmowy jako wywołania serwera FastMCP w procesie (`workbench/local_tools.py`). Opisy
  narzędzi są jedynym, co model czyta przed wywołaniem, bo instrukcje serwera do promptu rozmowy nie trafiają. Tura ma
  sufit 8 wywołań (`agent/graph.py`).
- Panel agenta należy do terminala, nie do zakładki. Tura może nieść migawkę wykresu (`SendMessageIn.chart`), która
  trafia do promptu tej tury i nie trafia do transkryptu. Terminal ogłasza koniec tury przez `agentActivity` i
  celowo nie czyta wyników cudzych narzędzi.
- Terminal nie ma dziś edytora kodu. Wykres (`chart/Chart.tsx`) dostaje symbol, interwał i źródło, a przyjmuje żądanie
  kadru i rysunki.
- `a-strategy-is-a-document` nie jest zarchiwizowana, więc jej możliwości nie ma jeszcze w `openspec/specs`. Delty
  tej zmiany do `strategies-*` tylko dopisują. Etap 1 trzeba zarchiwizować przed etapem 2.

## Goals / Non-Goals

**Goals:**
- Pętla „opis → dokument → streszczenie → backtest → raport” bez wychodzenia z terminala.
- Agent pisze i uruchamia, ale nie ustawia kosztów, nie zasypuje kolejki i nie wydaje werdyktu.
- Każda liczba i każde zdanie o strategii na ekranie pochodzi z pakietu. Terminal je tylko przedstawia.

**Non-Goals:**
- Postęp liczenia w trakcie uruchomienia (wystarczy stan i odświeżanie).
- Drugi tryb edytora (YAML, bloki) i edycja dokumentu bez tekstu.
- Podpowiedź spreadu z bieżącej ceny bramy w formularzu profilu. To możliwe później, bo terminal czyta bramę, ale
  godzinowego profilu z jednej ceny nie wyprowadzi.

## Decisions

### D1. Rozmowa w istniejącym panelu, a zakładka podaje otwartą strategię

Zakładka nie ma własnego czatu. Tura wysłana z panelu, gdy zakładka jest na ekranie, niesie `strategy`: identyfikator,
rewizję bazową i niezapisany tekst edytora. To pole siostrzane `chart` i ma to samo zachowanie: kontekst jednej tury,
poza transkryptem. Po turze zakładka czyta stan od nowa na sygnał `agentActivity`. Nie czyta wyniku `save_strategy`,
więc terminal nie trzyma kopii cudzej powierzchni narzędzi.

*Odrzucone:* osobny czat w zakładce, czyli drugi interfejs rozmowy, drugie listy sesji i panel, który przestaje być
jeden (`terminal-agent-chat`, „Panel należy do terminala, nie do zakładki”). Odrzucone też ogólne pole „co widzi
operator” jako wolny tekst: nie da się go sprawdzić typem ani sufitem, a model nie odróżni identyfikatora od opisu.

### D2. Agent zapisuje rewizje sam, bez kroku zatwierdzenia

`save_strategy` zapisuje rewizję z autorem `agent`. Alerty wybrały odwrotnie (żadne narzędzie nie zapisuje reguły, tylko
ją proponuje), bo reguła działa: wysyła powiadomienia. Rewizja nie działa na nic. Jest niezmienna, cofa się ją
przywróceniem wcześniejszej, a licznik prób liczy uruchomienia, nie rewizje. Zapis od razu daje operatorowi to, czego
potrzebuje do kontroli: streszczenie z dokumentu i różnicę względem poprzedniej rewizji.

*Odrzucone:* propozycja do zatwierdzenia w edytorze, czyli stan „szkic agenta”, którego nie ma w bazie. Operator
musiałby wtedy kliknąć zapis przy każdej poprawce, a backtest szkicu wymagałby rewizji i tak.

### D3. Zapis wskazuje rewizję bazową, a konflikt to 409

Operator w edytorze i agent w turze piszą do tej samej strategii. Bez podstawy późniejszy zapis cicho cofnąłby
wcześniejszy. Nic by nie przepadło, bo rewizje są niezmienne, ale ostatnia rewizja nie byłaby tą, o której myśli
operator, i nikt by tego nie zauważył. Terminal i narzędzie zawsze podają podstawę. REST bez podstawy działa jak w
etapie 1. Treść równa ostatniej rewizji nie jest konfliktem.

*Odrzucone:* blokada strategii na czas tury, bo trzeba by ją zwalniać po zerwanej turze, i scalanie zmian, bo dokument to
nie tekst wieloosobowy.

### D4. Streszczenie z drzewa dokumentu, nie z modelu

`summary.py` przechodzi po sprawdzonym dokumencie i jego drzewach formuł i składa zdania po polsku. Każda pozycja
rejestru (`vocabulary.py`) dostaje sformułowanie obok opisu dla modelu, a test odmawia pozycji bez niego. Wskaźniki
katalogu mają postać nazwy z parametrami (`EMA(20)`, `BBANDS(20, 2), linia upper`). Konstrukcja bez sformułowania
zostaje dosłowna. Streszczenie jest tanie, więc liczy się przy każdym `POST /validate` i każdym odczycie rewizji.

*Odrzucone:* streszczenie pisane przez model. Druga lektura modelu może powtórzyć błędne zrozumienie albo je
wygładzić, kosztuje tokeny przy każdej walidacji na żywo i nie da się jej przetestować raz. Kontrola, która może
kłamać tak samo jak to, co kontroluje, nie jest kontrolą.

### D5. Różnice po ścieżkach, liczone w pakiecie

`changes.py` porównuje dwa dokumenty jako drzewa: słowniki po kluczach, listy po indeksie. Wynik to lista ścieżek w
postaci problemów walidacji. Z tej samej funkcji korzystają trasa i odpowiedź `save_strategy`, więc agent mówi
operatorowi dokładnie to, co pokaże historia.

*Odrzucone:* różnica wierszy sformatowanego JSON-u w terminalu. Ślepo traktuje kolejność kluczy i wcięcia, a agent
dostałby inną różnicę niż ekran.

### D6. Koszty to profil instrumentu ustawiany przez operatora

Tabela `cost_profiles` (instrument → model kosztów, ostatni zapis wygrywa) ma ten sam model `CostModel` co uruchomienie.
Formularz terminala wypełnia się z profilu. `run_backtest` bierze koszty tylko z profilu. Uruchomienie zapisuje
wartości w `request`, jak w etapie 1, więc zmiana profilu nie rusza historii.

*Odrzucone:*
- Koszty wpisywane przy każdym uruchomieniu: 24 wartości spreadu za każdym razem kończą się jedną liczbą, a to fałszuje
  strategie minutowe.
- Koszty podawane przez agenta: model wpisze wiarygodnie wyglądające liczby i oceni własną pracę.
- Koszty z ostatniego uruchomienia strategii: pierwszego uruchomienia z rozmowy nie byłoby jak zrobić, a zależność
  byłaby ukryta.

### D7. Narzędzia tylko w rozmowie, bez `/mcp`

Serwer FastMCP pakietu powstaje, żeby `ConversationLocalTools` miało co wołać, ale nie jest montowany pod
`/strategies/mcp`. Nikt go przez sieć nie woła, bo operator nie ma klienta MCP, a drzwi do narzędzi zapisujących, których
nikt nie używa, to tylko powierzchnia ataku. Narzędzia nie trafiają do zespołów: harmonogram uruchamiałby backtesty, o
które nikt nie prosił, dzieliłby z operatorem kolejkę o współbieżności 1 i pompowałby licznik prób. Nie trafiają też do
katalogu alertów, bo odczyt strategii nie jest wartością do obserwowania.

*Odrzucone:* montaż jak w pozostałych pakietach, dla jednolitości. Jednolitość nie jest powodem otwierania drzwi.

### D8. `run_backtest` czeka krótko na wynik i trzyma jedno uruchomienie agenta naraz

Narzędzie kolejkuje uruchomienie i czeka na sygnał kolejki w procesie (bez odpytywania bazy) najwyżej 20 s. Pomiar
etapu 1: strategia HOUR z losowym wejściem ×100 na roku zajmuje około 2 s. Krótkie uruchomienie kończy się więc w tej samej
turze, a długie oddaje identyfikator do `read_run`. Gdy jakieś uruchomienie agenta czeka albo się liczy, narzędzie
odmawia. Przy suficie 8 wywołań i oczekiwaniu wewnątrz narzędzia agent może zrobić najwyżej kilka uruchomień w turze,
jedno po drugim, a nie kilkadziesiąt naraz w kolejce.

*Odrzucone:*
- Zwrot od razu: każde „uruchom” wymagałoby drugiej tury, żeby usłyszeć wynik.
- Czekanie do końca: uruchomienie MINUTE może liczyć się minutami, a tura nie ma wtedy sufitu czasu.
- Dobowy limit uruchomień agenta: liczba, której nikt nie umie dobrać. Kolejka po jednym i licznik prób mówią więcej.

### D9. Edytor: CodeMirror 6 nad JSON-em, zakładka ładowana leniwie

Tekst w edytorze to dokument w tej postaci, w jakiej jest zapisany i hashowany. Składnię JSON sprawdza lokalnie parser
edytora. Problemy z `POST /validate` przychodzą po przerwie w pisaniu, a ich ścieżka i kolumna trafiają na pozycję w
tekście przez drzewo składni JSON edytora. Podpowiedzi biorą się z `GET /language` (czytanego raz przy wejściu) i z nazw w
samym dokumencie. Zakładka jest ładowana leniwie (`React.lazy`), więc pozostałe zakładki nie płacą za edytor.

*Odrzucone:*
- Monaco: kilka megabajtów i robotnicy Vite dla jednego pola tekstowego.
- `textarea`: bez zaznaczeń w miejscu błędu i bez podpowiedzi.
- Widok YAML: druga postać tego samego dokumentu, tłumaczona w obie strony, podczas gdy agent pisze JSON.

### D10. Krzywa kapitału w raporcie, `ENGINE_VERSION` 2

`reports.build` zapisuje dzienną krzywą, którą już liczy (`equity: [[t, value], …]`). Dziesięć lat to około 3650
punktów. Złote strategie nagrywają cały raport, więc nowe pole zmienia nagranie. Wersja silnika rośnie do 2, a raport v1
mówi, dlaczego nie ma krzywej. Wyniki się nie przesuwają, więc to wyjątek od reguły „wyższa wersja = przesunięty wynik”,
zapisany w commicie nagrania.

*Odrzucone:* krzywa liczona w terminalu z transakcji. Nie zna wyceny otwartej pozycji ani narosłego finansowania, więc
narysowałaby inną krzywą niż ta, z której raport liczy obsunięcie, i wymagałaby czytania wszystkich stron transakcji.

### D11. Nazwy interwałów: wyjątek dla tekstu dokumentu

Terminal pokazuje `h4`, a język zapisuje `HOUR_4`. Edytor pokazuje tekst języka bez zmian, a podpowiedź pokazuje obie
nazwy (delta `terminal-shell`).

*Odrzucone:* przepisywanie nazw w tekście edytora, bo zapisany dokument różniłby się od pokazanego. Odrzucone też
aliasy `h4` w języku: dwie pisownie jednej rzeczy dają dwa hashe tej samej strategii.

## Risks / Trade-offs

- [Pisanie dokumentu zjada sufit 8 wywołań] → `strategy_language` raz, a zapis oddaje wszystkie problemy naraz. Pętla
  „język, zapis z błędami, zapis poprawny” to 3–4 wywołania. Jeśli pomiar pokaże, że to za mało, sufit jest w kodzie
  rozmowy i jego zmiana to osobna decyzja.
- [Streszczenie brzmi mechanicznie i operator przestaje je czytać] → sformułowania per funkcja i dosłowność tylko w
  ostateczności. Streszczenie jest kontrolą, nie prozą.
- [Listy porównywane po indeksie: wejście dopisane na początku zmienia wszystkie kolejne] → wejść jest kilka. Zgoda.
- [Walidacja na żywo przy każdej przerwie w pisaniu] → katalog to pliki, lista par ma pamięć 60 s, a walidacja idzie tylko
  dla zmienionego tekstu i widocznej zakładki. Skill `db-cost-check` przed merge.
- [Tekst edytora w kontekście tury powiększa prompt] → wysyłany tylko wtedy, gdy różni się od rewizji, i ma sufit.
- [Brak profilu kosztów na produkcji blokuje agenta] → oczekiwane. Odmowa mówi, gdzie ustawić profil, a operator robi to
  raz na instrument.
- [`compare_runs` odmawia między v1 a v2] → produkcja ma jeden dzień uruchomień. Zgoda.
- [Operator zmienia strategię w trakcie tury] → kontekst opisuje chwilę pytania, a odczyt po turze i rewizja bazowa
  (D3) chronią przed zapisem na cudzej podstawie.

## Migration Plan

1. Archiwizacja `a-strategy-is-a-document`, najpóźniej przed archiwizacją tej zmiany. Delty `strategies-*` tej zmiany
   dopisują do jej specyfikacji, a odwrotna kolejność zostawiłaby `openspec/specs/strategies-*` bez `## Purpose`.
2. Merge = wdrożenie. Migracja `0002` biegnie w lifespanie pod kluczem 8130 i tylko dodaje: tabelę `cost_profiles` oraz
   `runs.requested_by` z domyślnym `operator`. `deploy-vps.yml` buduje terminal z `VITE_STRATEGIES_HTTP`.
3. Po wdrożeniu: skill `deploy-watch`, potem profile kosztów dla instrumentów zbieranych na `MINUTE`.
4. Wycofanie: poprzednie obrazy. Stary kod nie czyta nowej tabeli ani kolumny, a jego `INSERT INTO runs` korzysta z
   wartości domyślnej.

## Open Questions

- Czas oczekiwania `run_backtest` (20 s), sufit tekstu edytora w kontekście tury i sufit powierzchni narzędzi: liczby
  ustali pomiar przy implementacji. Wymagania mówią tylko, że są nazwane.
