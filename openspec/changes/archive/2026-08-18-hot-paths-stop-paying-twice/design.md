## Context

Wszystkie liczby niżej zmierzone 18.08.2026 na `origin/main` (`153bdbf`): serwery zbudowane
w procesie, `list_tools()` zserializowany do JSON-a bez spacji, policzony `cl100k_base`.

| Moduł | znaki | tokeny |
|---|---:|---:|
| market-mcp (11 narzędzi) | 25 474 | 6 013 |
| teams-mcp (18 narzędzi) | 24 512 | 5 670 |
| trading-mcp (9 narzędzi) | 14 430 | 3 451 |
| **razem, co agent montuje w każdej turze** | **64 416** | **15 134** |

Stosunek znaków do tokenów jest w tym materiale stabilny: 4,18–4,32. Audyt mówił ~17,6 tys.
tokenów; różnica to koperta wywołania, której ten pomiar nie liczy, a nie inny wynik.

Z tego opisy narzędzi to 13 265 znaków (~3,1 tys. tokenów), reszta to schematy. Sufity
liczbowe odpowiedzi są już wymagane od opisu każdego narzędzia z osobna
(`market-mcp-tools`); nie ma nic, co pilnowałoby sumy.

## Goals / Non-Goals

**Goals:**

- Powierzchnia trzech serwerów poniżej 10 tys. tokenów na turę, bez utraty pola, typu ani
  wymagalności w schemacie. Samo odchudzenie schematu daje 11 718; resztę drogi robią opisy,
  dziś 13 265 znaków przy rozrzucie 68-676 znaków na narzędzie.
- Sufit, który wywraca się sam, w każdym z trzech modułów.
- Żaden upstream nie jest pytany dwa razy o to samo w jednym wywołaniu narzędzia.
- Demo-guard, który mierzy coś, co może wyjść inaczej.

**Non-Goals:**

- Usuwanie narzędzi z zestawu. Zestaw jest tym, czym jest; to jest zmiana o koszcie jego
  ogłaszania, nie o jego zakresie.
- Zmiana kształtu odpowiedzi narzędzi (pola, nazwy, jednostki). Model dostaje to samo.
- Zasoby `market://...` bez konsumenta, proxy `list_models`/`list_tools` w teams-mcp,
  `provider_params` - to balast z audytu, idzie osobną zmianą (iteracja 5).

## Decisions

### D1. Odchudzanie schematu żyje w `tc-mcp-kit`, a warunek nr 1 dostaje zdanie o kodzie nowym

Rozważone trzy miejsca:

- **trzy kopie, po jednej w module** - dokładnie ta klasa dryfu, którą iteracja 1 zamknęła:
  ~45 linii czystej transformacji słownika, poprawiane potem w dwóch kopiach z trzech;
- **własna generacja schematu zamiast pydanticowej** - kilkaset linii i drugie źródło
  prawdy o kształcie modelu, żeby oszczędzić kilka kluczy;
- **`packages/tc-mcp-kit`** - pakiet istnieje dokładnie dla rzeczy wspólnych trzem modułom
  MCP i żadnemu innemu. Wybrane.

Warunek nr 1 dzielenia kodu (`docs/architecture.md`) wymaga **zmierzonej** kopii >=70%
identycznej. Kod, który jeszcze nie istnieje, nie może tego spełnić - literalnie czytany
warunek mówi, że nowa wspólna rzecz MUSI najpierw zostać skopiowana trzy razy i poczekać,
aż ktoś zmierzy, że są takie same. Sens warunku jest inny: nie dzielić rzeczy, które są
tylko *podobne*. Trzy serwery MCP odchudzające publikowany schemat według tej samej reguły
to jedno zachowanie, nie trzy zbieżności.

Warunek dostaje więc drugą drogę spełnienia: kod **nowy**, identyczny u każdego konsumenta
od pierwszego dnia i mający więcej niż jednego konsumenta od pierwszego dnia. Warunki 2
(każda różnica jest argumentem) i 3 (każdy konsument testowany przy każdej zmianie) zostają
bez zmian i to one niosą ciężar. `tc-mcp-kit` zyskuje zależność od `mcp` - wszyscy trzej
konsumenci i tak pinują `mcp==1.27.0`.

### D2. Zdejmujemy rusztowanie, zostawiamy treść - i **nie** zdejmujemy `outputSchema`

Zmierzone warianty, na sumie trzech modułów:

| Wariant | znaki | tokeny |
|---|---:|---:|
| dziś | 64 416 | 15 134 |
| bez `title` | 53 683 | - |
| + `anyOf` samych typów -> lista typów | 51 631 | - |
| + bez `default` w schematach wyjścia | **50 172** | **11 718** (-22,6%) |
| dodatkowo: bez `outputSchema` w ogóle | 27 671 | 6 512 (-57,0%) |

Kroki pośrednie liczone w znakach, bo o kolejność cięć rozstrzyga tylko rachunek; tokenizer
puszczony na trzy stany, które są decyzjami: dziś, po odchudzeniu i bez schematów wyjścia.

Ostatni wiersz jest kuszący i odrzucony. `outputSchema` nie jest tu dokumentacją - serwer
lowlevel waliduje nim **każdą** strukturalną odpowiedź, i to ta walidacja złapała błąd,
przez który wszystkie cztery narzędzia niosące okno odmawiały własnej odpowiedzi
(`WindowedOut`, `serialization_alias` kontra schemat walidacyjny). Testy tego nie łapały i
nie łapią; jedyna obrona przed tą klasą jest w opublikowanym schemacie. 5,2 tys. tokenów za
utratę jedynego mechanizmu, który wykrył realną awarię, to zła cena.

`description` z modeli i parametrów zostaje - to jest treść. `default` w schemacie
**wejścia** zostaje: mówi modelowi, co się stanie, gdy pola nie poda.

### D3. `compute_indicators` **nie** zostaje rozbity - plan zakładał oszczędność, której nie ma

Plan (iteracja 4) i audyt proponują wydzielenie trybu `series` do osobnego narzędzia, bo
model wyjściowy niesie sześć wzajemnie wykluczających się grup pól. Policzone na schemacie
po odchudzeniu z D2:

- `compute_indicators` dziś: 4 465 znaków (samo wyjście 3 092);
- po wydzieleniu, policzone przez wycięcie ze schematu pól i definicji, które w danym trybie
  nie występują: `compute_indicators` (samo `latest`) ~3 700 + nowe `indicator_series`
  ~1 850 = **~5 550**.

Rozbicie **dokłada** ~1 100 znaków, bo każde narzędzie niesie własną kopię wspólnej części
schematu, a `markers`/`zones`/`levels` muszą zostać w obu (wskaźnik o takim wyjściu
odpowiada tak samo w obu trybach). Sześć grup pól kosztuje raz; dwa narzędzia kosztują
dwa razy.

Wymaganie `market-mcp-tools` "Pełna seria MUST być rzeczą, o którą prosi się osobno" jest
już spełnione przez `mode="series"` - osobna prośba, nie osobne narzędzie.

### D4. Demo-guard: wyliczone środowisko **i** tylko check startowy - obie połówki audytu naraz

Audyt dawał do wyboru (a) uczciwe wyliczanie `environment` w bramie albo (b) zostawienie
samego checku startowego w trading-mcp, i ostrzegał, żeby nie utrzymywać obu połówek w
obecnej formie. Plan wybiera obie zmiany naraz i to jest tańsze niż każda z osobna:

- brama liczy `environment` z `capital_base_url` (jedna linia) - pole zaczyna móc wyjść
  inaczej, więc pytanie o nie zaczyna coś znaczyć;
- `trading-mcp` traci `_demo_verified`, inwalidację w trzech miejscach `_send` i re-check w
  `_write`; zostaje `ensure_demo_environment()` w `__main__` przed otwarciem portu.

Co naprawdę chroni po tej zmianie: brama **nie umie** wstać na hoście innym niż demo
(`Settings._demo_only`, walidator pola), a `trading-mcp` nie umie otworzyć portu bez
świeżej odpowiedzi z bramy. Żeby zapisy poszły na rachunek rzeczywisty, musiałaby powstać
brama, która przeszła własny walidator hosta - a wtedy re-check też by ją przepuścił,
bo pytał tę samą bramę o to samo pole.

Co przestaje być chronione, uczciwie: gateway **podmieniony pod działającym**
`trading-mcp` na taki, który zgłasza inne środowisko. Kosztem tej ochrony była druga runda
do bramy przy każdym zapisie po dowolnym błędzie - a `False` po każdym 503 znaczyło, że
zwykły restart bramy kupował sobie tę cenę na stałe.

### D5. Memo z TTL, nie kontekst wywołania

`/pairs` (market-mcp) i `_market_open` (brama) są pytane po kilka razy w jednym wywołaniu
narzędzia. Rozważone przekazanie memo przez `contextvars` na czas wywołania: poprawne co do
sekundy, ale wymaga opakowania `call_tool` w każdym module - czyli podpięcia się pod prywatne
wnętrze FastMCP w kodzie produkcyjnym, żeby oszczędzić jeden request.

Wybrane: memo z krótkim TTL w kliencie. Jedno wywołanie narzędzia trwa milisekundy, więc
TTL rzędu sekund zbiera wszystkie powtórzenia w jednym wywołaniu i prawie nigdy nie łączy
dwóch. TTL zapisany jako stała z komentarzem, co jest najstarszą odpowiedzią, jaką moduł
gotów jest podać.

### D6. Sufit liczony w znakach, nie w tokenach

Test nie ciągnie tokenizera (kolejna zależność, wersjonowana, wolna). Zserializowany
`list_tools()` w znakach jest deterministyczny i przelicza się na tokeny stałym
współczynnikiem 4,2 zmierzonym wyżej - sufit zapisany w znakach niesie w komentarzu
odpowiadającą mu liczbę tokenów.

Sufity ustawiane po wykonaniu, na zmierzonej wartości plus zapas rzędu 5%: sufit z dużym
zapasem to sufit, który nic nie mówi przez rok.

## Risks / Trade-offs

- **`title` bywa czytany przez klienty MCP** jako etykieta pola w interfejsie. Konsumenci
  tych trzech serwerów to agent, teams i klient MCP na biurku operatora - żaden nie rysuje
  formularza z pól narzędzia. Ryzyko: klient desktopowy pokaże nazwę pola zamiast ładniejszej
  etykiety, która i tak była nazwą pola z wielkiej litery.
- **`anyOf` -> lista typów** jest równoważne w JSON Schema 2020-12, ale to dwa różne teksty
  dla modelu. Nie zmienia, co jest dopuszczalne; walidacja odpowiedzi przechodzi tak samo.
  Ryzyko jest po stronie czytelności dla modelu, nie poprawności.
- **Ramki `quote`**: `read_message` przestaje je parsować, więc model `Quote` przestaje
  mieć wywołującego w produkcji. Zostaje z testem, bo opisuje kształt, który brama nadal
  wysyła - a `market-data` przestaje tylko za niego płacić.
- **TTL na `_market_open`** może o kilka sekund spóźnić się z "rynek się właśnie zamknął"
  i oznaczyć świecę DAY jako formującą się tuż po zamknięciu sesji. Świeca formująca się
  nie jest zapisywana jako zamknięta, więc błąd w tę stronę jest odwracalny następnym
  odczytem; w drugą stronę (świeca zamknięta uznana za trwającą) TTL nie prowadzi.
- **Utrata re-checku demo** - opisana w D4 wraz z tym, co zostaje.
- **Sufit ustawiony za ciasno** wywróci CI przy pierwszym uzasadnionym nowym polu. To jest
  zamierzone: podniesienie sufitu ma być edycją, nie efektem ubocznym.
