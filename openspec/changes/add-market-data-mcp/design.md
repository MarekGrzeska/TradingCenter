## Context

Motywacja: `proposal.md`, sekcja Why. Wymagania: cztery pliki w `specs/`. Plan wysokiego
poziomu, z którego ta zmiana wyrosła: `docs/mcp-plan-wdrozenia.html`.

Co zastane kształtuje ten projekt:

- `market-data` publikuje wszystko, czego moduł potrzebuje, i nie jest w tej zmianie
  dotykane: świece z przedziałami niezweryfikowanymi, pokrycie, katalog 57 wskaźników w
  11 grupach oraz ich obliczenie z własnym sufitem żądania.
- Kontrakt `market-data` jest zbudowany **dla wykresu**. Doba świec MINUTE to 1440
  obiektów; sufit obliczenia wskaźników wynosi 200 000 komórek (świece × wskaźniki). To są
  wielkości dobrane pod rysowanie, nie pod czytanie przez model.
- Terminal rozwiązał już raz problem „dwie kopie jednego kontraktu": generuje typy z
  dokumentu OpenAPI drukowanego wprost z modeli `market-data`, procesem uruchamianym w
  katalogu siostrzanym, bez działającego serwera. Ten sam mechanizm stosuje się tutaj.
- Wzorzec „ustawienie wskazuje tryb, konfiguracja niejednoznaczna jest odmawiana przy
  starcie" jest w `market-data/config.py` i w `agent/config.py`. Powielamy go, nie
  współdzielimy — w tym repozytorium nie ma biblioteki wspólnej.
- Plan App Service jest **B1 z jednym workerem** i stoją już na nim trzy aplikacje, a
  czwarta powstaje w `add-agent-chat`.

## Goals / Non-Goals

**Goals:**

- Zestaw narzędzi, który da się ocenić bez agenta — podpięty pod klienta na biurku
  operatora, tą samą drogą, którą ocenia się każdy inny serwer MCP.
- Odpowiedź, której koszt w tokenach jest znany z góry i wpisany w opis narzędzia.
- Rozjazd z kontraktem `market-data` wywracający testy, nie żądanie w produkcji.
- Moduł, którego zakres da się opisać jednym zdaniem: czyta archiwum i liczy z niego.

**Non-Goals:**

- Cokolwiek, co zapisuje. Nie ma narzędzia zapisującego i nie ma przełącznika, który by je
  dołożył — `specs/market-mcp-tools`.
- Własny magazyn świec, choćby jako cache.
- Pozycje i zlecenia z `capital-gateway` — inny profil ryzyka, osobna decyzja.
- Klient MCP po stronie agenta. To zmiana w `modules/agent`, po zamknięciu
  `add-agent-chat`.

## Decisions

### Osobny moduł `modules/market-mcp`, port 8040

Odrzucone: **narzędzia wewnątrz `modules/agent`** — tańsze o cały moduł, ale wiążą zestaw
narzędzi z cyklem życia rozmowy, wkładają dwa profile awarii do jednego procesu (model,
który nie odpowiada, i archiwum, które nie odpowiada) i zamykają drogę każdemu innemu
klientowi MCP. Ocena, czy opis narzędzia jest zrozumiały, wymagałaby wtedy przejścia przez
agenta.

Odrzucone: **trasy MCP w `market-data`** — nie ma nowego wdrożenia ani auth do postawienia,
ale archiwum zaczyna obsługiwać dwie publiczności o sprzecznych wymaganiach: wykres chce
kompletu, model chce streszczenia. To jest drugi kontrakt w module, który ma jeden.

Cena jest realna i płacimy ją świadomie: piąta aplikacja na planie z jednym workerem,
piąty job w CI, piąty workflow wdrożeniowy, powielone kształty DTO.

Nazwa: `market-mcp`, nie `mcp-gateway` — „gateway" znaczy tu okno na dostawcę
(`capital-gateway`).

### Moduł streszcza, a nie przekazuje dalej

To jest decyzja, z której wynika kształt każdego narzędzia. Narzędzie nie oddaje tego, co
odpowiedziało archiwum; liczy z tego odpowiedź na zadane pytanie i oddaje ją.

Odrzucone: **przekazanie odpowiedzi archiwum bez zmian**, z samym sufitem na wielkości.
Prostsze o całą warstwę i wierne kontraktowi — ale model dostaje tablicę liczb i sam robi
z niej arytmetykę: wolniej, drożej i czasem źle. Sufit bez streszczenia daje w zamian
odpowiedź uciętą w połowie okna, co jest gorsze niż zagregowana, bo wygląda na kompletną.

Odrzucone: **decyzja o redukcji po stronie wołającego** (parametr „ile szczegółu"). Model
nie ma jak wiedzieć, że szczegół kosztuje, więc poprosi o wszystko i zrobi to raz na turę.

Konsekwencja dla obliczeń wskaźników: tryb domyślny oddaje stan bieżący — ostatnią wartość
linii, jej nachylenie i odległość od ceny — a pełną serię trzeba wskazać jawnie.
Redukcja jest inna dla każdego z czterech kształtów wyjścia archiwum (`lines`, `markers`,
`zones`, `levels`) i to jest właściwa jednostka podziału pracy w `tasks.md`.

### Bezstanowy, bez bazy danych

Odrzucone: **własny cache świec w Postgresie**. Byłby drugim archiwum tych samych świec, a
`docs/architecture.md` mówi wprost, że danie jednej świecy dwóch pochodzeń jest gorsze niż
niezapisanie jej wcale — przy rozjeździe nikt nie wie, które źródło skłamało. Zysk byłby
i tak pozorny: archiwum stoi obok, w tej samej sieci.

W pamięci procesu zostaje wyłącznie krótkotrwały cache katalogu wskaźników, unieważniany
przez `algorithm_version`, które archiwum podaje w każdej odpowiedzi. Katalog jest jedyną
rzeczą czytaną przy prawie każdym wywołaniu i jedyną, która praktycznie się nie zmienia.

### Kontrakt sprawdzany snapshotem, nie generowanym klientem

Moduł opisuje u siebie wąskie modele obejmujące tylko czytane pola, a zgodności pilnuje
commitowany snapshot dokumentu OpenAPI archiwum plus test asercji pól.

Odrzucone: **import `market_data.contract`** — złamanie reguły nośnej repozytorium.

Odrzucone: **klient generowany z OpenAPI**. Znosi ręczne przepisywanie kształtów, ale
wciąga do modułu wygenerowany kod obejmujący cały kontrakt, w tym trasy, których moduł
nigdy nie zawoła, i zmienia się w całości przy każdej zmianie po tamtej stronie. Test
asercji mówi dokładnie to, na czym nam zależy: *te pola, po które sięgamy, wciąż są*.

Snapshot powstaje procesem uruchamianym w katalogu siostrzanym, nie importem i nie
wołaniem działającego serwera — sprawdzenie wymagające uruchomionej usługi jest
sprawdzeniem, którego nikt nie robi.

### Dwa transporty, jeden zestaw

Streamable HTTP dla agenta stojącego w innym kontenerze; stdio dla klienta na biurku
operatora. Aplikacja ASGI serwera MCP jest zamontowana obok własnej trasy zdrowia, bo
platforma restartuje kontener na podstawie sondy i nie zna protokołu MCP.

Odrzucone: **stary transport HTTP+SSE** — wycofany na rzecz streamable HTTP, dwie trasy i
sesja po stronie serwera za nic. Odrzucone: **WebSocket** — wciągnąłby maszynerię biletów
jednorazowych z `market-data/tickets.py`, która istnieje tam wyłącznie dlatego, że uchwyt
WebSocketu nie uniesie nagłówka. Klient MCP uniesie.

### Brak zapisu jest wymaganiem, nie ustawieniem

Odrzucone: **przełącznik `MCP_ALLOW_WRITES` domyślnie wyłączony**, z narzędziem
rozpoczynającym zbieranie pary za nim. Wygląda ostrożnie i jest tańsze o późniejszą
zmianę zakresu — ale przełącznik jest obietnicą, że kiedyś się go przestawi, a wtedy
różnica między konfiguracją a wymaganiem znika w jednym pliku `.env`, którego nikt nie
czyta na review.

Granica jest sprawdzana tam, gdzie przechodzi każde żądanie: klient HTTP odmawia metod
innych niż czytające, z jednym jawnym wyjątkiem na obliczenie wskaźników. Zakres modułu
da się wtedy sprawdzić jednym testem zamiast czytania dziesięciu narzędzi.

### Sufity są liczbami w kodzie, nie wartościami w konfiguracji

Sufit wpisany w opis narzędzia jest częścią tego, co model o nim wie; sufit w konfiguracji
rozjeżdża się z opisem po pierwszej zmianie i model zaczyna dostawać odmowy za żądania,
które opis obiecywał przyjąć.

Punkt wyjścia, do zmierzenia po E2 i wtedy ewentualnie do poprawienia: 200 świec domyślnie
i 500 twardo, 3 wskaźniki domyślnie i 10 twardo, 200 punktów serii, 20 poziomów
najbliższych cenie. Powyżej sufitu świece są agregowane do grubszego okresu, listy
obcinane do najbliższych cenie albo najnowszych, a fakt odcięcia nazwany w odpowiedzi.

## Risks / Trade-offs

- **Piąta aplikacja na planie B1 z jednym workerem** → Moduł jest bezstanowy i lekki, ale
  nacisk jest realny i dzielony z agentem. Do zmierzenia po wdrożeniu, nie do przewidzenia
  teraz. Wyjście awaryjne: uruchomienie modułu obok agenta w jednym kontenerze, kosztem
  osobnego wdrożenia — moduł zostaje osobny, dzieli się tylko proces.
- **Stały narzut tokenów opisów narzędzi w każdej turze modelu** → Dziesięć narzędzi z
  opisami niesionymi przy każdym wywołaniu modelu. Do zmierzenia po E2 i zestawienia z
  tabelą kosztów agenta. Jeśli zaboli, zestaw dzieli się na profile — nie skraca się
  opisów do nieczytelnych, bo opis jest kontraktem.
- **Model dostaje streszczenie i wyciąga z niego wniosek, którego dane nie niosą** →
  Częściowo nieuchronne. Ograniczamy to jedynym sposobem, jaki działa: niepewność archiwum
  jedzie w treści odpowiedzi jako zdanie (`specs/market-mcp-answers`), a prompt agenta
  każe ją powtórzyć operatorowi.
- **Wersja protokołu MCP i tempo zmian SDK** → Wersja protokołu i data sprawdzenia
  zapisane w README modułu przy pierwszym commicie. Modułu nie chroni to przed zmianą, ale
  pozwala ją rozpoznać.
- **Stan sesji rynku niepublikowany przez archiwum** → `market_status.py` istnieje w
  `market-data`, ale nie ma trasy. Narzędzia mówią „ostatnia świeca sprzed 14 minut", co
  jest faktem, zamiast „rynek zamknięty", co byłoby domysłem. Wystawienie tego to osobna
  zmiana w tamtym module, otwierana dopiero gdy okaże się potrzebna.

## Migration Plan

Nie ma czego migrować: moduł jest nowy, nie ma bazy i nikt jeszcze z niego nie czyta.
Wdrożenie idzie w tej kolejności, bo każdy krok jest osobno odwracalny:

1. Moduł i jego testy, oceniany lokalnie przez klienta na biurku (stdio). Nic w Azure.
2. Infrastruktura i wdrożenie, moduł stoi w sieci i nikt go nie woła.
3. Klient MCP po stronie agenta — osobna zmiana, po zamknięciu `add-agent-chat`.

Wycofanie na każdym z tych kroków to skasowanie tego, co doszło: katalogu modułu, jego
aplikacji w `infra/`, węzła w grafie agenta. Żaden z nich nie zostawia po sobie danych.

## Open Questions

- Czy `list_indicators` ma domyślnie wypisywać wszystkie 57 wpisów, czy wymagać wskazania
  grupy? Odpowiedź zależy od zmierzonego rozmiaru wypisu i nie zmienia ani specyfikacji,
  ani podziału pracy.
- Czy streszczenie okna (`summarize_range`) ma podawać zmienność w jednostkach ATR, czy
  surowym zakresem — do rozstrzygnięcia przy E1, gdy widać, o co model faktycznie pyta.
