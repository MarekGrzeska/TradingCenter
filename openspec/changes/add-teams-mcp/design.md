## Context

Powody są w `proposal.md`. Tu liczą się cztery fakty o stanie zastanym, bo one zawężają
rozwiązanie do kilku, a nie do wielu:

1. **`agent` ma dokładnie jeden serwer narzędzi.** `agent/tools/client.py` trzyma klasę
   `ToolServer` czytającą `settings.market_mcp_url`. `teams` przy fazie 2 dostał
   `ToolServerRegistry` — ten sam plik, o jedną warstwę bogatszy. Drugi serwer po stronie
   agenta to przeniesienie tamtego kształtu, kopiowane, bo biblioteki między modułami nie ma.
2. **`teams` ustala tożsamość operatora z nagłówka**, który wstawia mu warstwa
   uwierzytelniająca (`teams/auth.py`, `X-MS-CLIENT-PRINCIPAL-ID`), a wszystkie zapytania
   filtrują po niej w samym zdaniu SQL. Cudzy zespół jest nieodróżnialny od nieistniejącego.
3. **Easy Auth przed `teams` przyjmuje token, który terminal już ma.** `allowed_audiences`
   wymienia audiencję `market-data`, a `allowed_applications` — aplikację terminala
   (`infra/app-service.tf`). Token operatora z przeglądarki jest więc dla `teams` ważny; to
   nim terminal woła ten moduł dzisiaj.
4. **Plan App Service jest ciasny.** B2, jeden worker, sześć aplikacji, pamięć po wdrożeniu
   z 16 sierpnia **84%**, próg alertu **92%**. Zmiana `scale-app-service-plan-to-b2` policzyła
   koszt jednego lokatora na 150–310 MB i nazwała wzrost „nowymi lokatorami", nie wyciekiem.

## Goals / Non-Goals

**Goals:**

- Zespół założony z czatu jest **zwykłym zespołem operatora** — widocznym w terminalu,
  edytowalnym ręcznie, rozliczanym w jego granicach.
- Nowa droga do `teams` **nie jest nową polityką dostępu**: każda odmowa, którą `teams` zna,
  obowiązuje tak samo.
- Katalog narzędzi mówi językiem zadania, nie językiem tras.

**Non-Goals:**

- Interaktywne potwierdzenia w czacie („czy na pewno uruchomić?"). Decyzja operatora, świadoma
  — patrz „Decisions", D3, razem z tym, czego ta decyzja nie chroni.
- Zmiana czegokolwiek w tym, jak `teams` liczy koszty i granice. Ten moduł ich nie powtarza.
- Wystawianie tych narzędzi komukolwiek poza `agent`.
- Zmiana terminala. Zakładka Teams pokazuje zespoły z czatu bez jednej linii nowego kodu, bo
  są zwykłymi wierszami tego samego operatora — i to jest test tego projektu, nie jego brak.

## Decisions

### D1: Siódmy moduł `teams-mcp`, nie narzędzia wewnątrz `agent`

Wybrane przez operatora, z dwiema realnymi alternatywami na stole.

**Alternatywa A — narzędzia lokalne w `agent`** (jak `agent/tools/chart.py`, które nie mają
serwera MCP): zero nowych aplikacji, zero pamięci, zero infrastruktury. Odrzucona, bo granica
między modułami przestałaby być serwerem MCP i stałaby się prywatnym klientem HTTP jednego
modułu — a wtedy drugi konsument tych samych narzędzi (choćby `teams` sam, przy zespole
budującym zespoły) musiałby je napisać od nowa.

**Alternatywa B — dołożyć narzędzia do `market-mcp`**: odrzucona wprost przez jego własną
specyfikację, która mówi, że nie publikuje narzędzia zapisującego. Ta granica została raz
postawiona świadomie i nie jest do przesuwania po cichu.

**Konsekwencja, którą trzeba znieść:** siódma aplikacja na planie, który ma 8 punktów procentowych
zapasu. Patrz D5.

### D2: Tożsamość operatora jedzie tokenem, którym terminal już się posługuje

To jest decyzja tej zmiany. Łańcuch jest długi — terminal → `agent` → `teams-mcp` → `teams` —
a `teams` musi na końcu zobaczyć operatora, nie usługę.

**Wybrane: przeniesienie tokenu operatora.** `agent` czyta token wołającego z żądania, które
właśnie obsługuje, i przekazuje go do `teams-mcp` **osobnym nagłówkiem** — nie w `Authorization`,
bo tam musi zostać własny token `agenta`, którym uwierzytelnia się wobec Easy Auth przed
`teams-mcp`. `teams-mcp` przedstawia przeniesiony token jako `Authorization` w wywołaniu do
`teams`, a Easy Auth przed `teams` sam wstawia nagłówek z tożsamością operatora — dokładnie
tak, jak robi to dla terminala.

Co za tym przemawia: **`teams` nie zmienia się w ogóle**, ani o linię. Audiencja i lista
wołających już to przepuszczają (fakt 3 wyżej). Nie powstaje żadna nowa reguła zaufania, którą
trzeba by testować i pilnować.

**Alternatywa A — nagłówek delegacji, któremu `teams` ufa od nazwanych wołających.**
`teams-mcp` woła `teams` własną tożsamością i dokłada nagłówek „w imieniu X". Odrzucona: wymaga
zmiany w `teams/auth.py`, czyli wymagania w jego specyfikacji, a pomyłka w liście zaufanych
wołających jest dziurą podszycia. Platforma rozwiązuje to samo bez wymyślania reguły.

**Alternatywa B — On-Behalf-Of.** Kanoniczna droga Entra: `agent` wymienia token operatora na
token do `teams`. Odrzucona jako nieproporcjonalna: OBO wymaga klienta poufnego, czyli sekretu
albo certyfikatu, których `agent` dziś nie ma (chodzi na tożsamości zarządzanej) — nowy sekret
w Key Vault, jego rotacja i jedna rzecz więcej do zepsucia, w zamian za własność, którą
alternatywa wybrana ma za darmo.

**Alternatywa C — moduł zakłada na siebie, potem przepisuje właściciela.** Odrzucona: dwa
zapisy zamiast jednego, okno, w którym wiersz należy do nikogo widocznego, a `team_revisions`
jest append-only i nie ma czym przepisać rewizji.

**Do sprawdzenia jako pierwsze zadanie, przed resztą pracy:** czy Easy Auth przed `agent`
przepuszcza oryginalny nagłówek `Authorization` do procesu. Jeśli nie przepuszcza, wybrana
droga odpada w całości i wraca alternatywa A — dlatego to jest zadanie 1, a nie szczegół
odkryty w połowie implementacji.

**Cena, którą ta droga ma:** token operatora przechodzi przez dwa procesy. Żaden nie ma prawa
go zapisać — ani do logu, ani do bazy, ani do śladu narzędzia. To jest wymaganie, nie zalecenie,
i ląduje w zadaniach jako osobny test.

### D3: Model działa bez potwierdzeń — i czego to nie chroni

Wybrane przez operatora: model zakłada, edytuje i uruchamia sam, a chronią granice, które
`teams` już ma. Zapisuję konsekwencje, bo są policzalne i nie są oczywiste.

**Co chroni.** Dobowa granica kosztu zespołu i granice handlowe są sprawdzane **przed**
utworzeniem przebiegu, w `runner/starter.py`, tą samą drogą dla kliknięcia w terminalu, dla
zegara i dla tego zestawu narzędzi. Rewizje są append-only, więc żadna poprawka modelu nie
kasuje poprzedniej wersji. Zespół da się wycofać z katalogu, a jego przebiegi zostają czytelne.

**Czego nie chroni, wprost.** Dobowa granica jest liczona **na zespół**. Model, który zakłada
nowy zespół, zaczyna z czystym budżetem — więc granica ogranicza jeden eksperyment, a nie sumę
eksperymentów jednego popołudnia. Nie jest to powód, żeby zmieniać decyzję, jest to powód, żeby
ją znać. Trzy tanie sposoby domknięcia, gdyby okazało się to potrzebne, wymienione w kolejności
rosnącego kosztu: twardy limit wydatków na kluczu OpenAI po stronie dostawcy; dobowa granica
liczona na operatora zamiast na zespół (zmiana w `teams`, nie tutaj); ograniczenie liczby
zespołów zakładanych z czatu na dobę. Żaden nie wchodzi do tej zmiany.

### D4: `unattended_ack` zostaje poza zasięgiem modelu

Narzędzie zakładające harmonogram albo wyzwalacz **MUST NOT** przyjmować potwierdzenia pracy
bez nadzoru jako argumentu, który model wypełnia. Harmonogram nad rewizją niosącą narzędzie,
którego `teams` nie potwierdzi jako odczyt, jest odmawiany, a operator odklikuje to w terminalu.

Powód: ten bezpiecznik był raz ślepy przez całą fazę 2 i został naprawiony tydzień temu —
`teams` czyta dziś `readOnlyHint` z ogłoszeń serwerów i odmawia wszystkiego, czego nie
potwierdzi jako odczyt. Potwierdzenie wystawione modelowi jako pole do wypełnienia znaczy, że
model je wypełni, kiedy odmowa mu przeszkodzi — i bezpiecznik znowu przestaje istnieć, tym razem
bez śladu w kodzie. To nie jest potwierdzenie interaktywne w rozumieniu D3; to jest granica,
która już istnieje i której ten moduł nie rozmontowuje.

### D5: SKU planu rośnie razem z modułem

Siódma aplikacja wchodzi na plan mający 8 punktów procentowych do progu alertu, a zmierzony
koszt lokatora to 150–310 MB, czyli 4–9 punktów. Podniesienie planu do B3 wchodzi **do tej
zmiany**, nie po niej, i jest zadaniem wykonywanym **przed** pierwszym wdrożeniem modułu.

**Alternatywa — wdrożyć i patrzeć:** odrzucona. Wariant, w którym alert odzywa się w nocy po
wdrożeniu, jest dokładnie tym, przed czym `raise-memory-alert-threshold` i
`scale-app-service-plan-to-b2` już raz ostrzegały; drugi raz nie jest to niespodzianka, tylko
zaniedbanie.

**Alternatywa — nie wdrażać do Azure, zostawić lokalnie:** odrzucona, bo `agent` na produkcji
nie dostałby narzędzi, czyli zmiana nie robiłaby tego, po co powstaje.

### D6: Kształt katalogu — dziewięć narzędzi, nie trzydzieści sześć tras

Redukcja jest wymaganiem (`teams-mcp-tools`), więc jej kształt jest decyzją, a nie szczegółem
implementacji. Punkt wyjścia, do dopracowania przy pisaniu opisów:

| Narzędzie | Odpowiada na |
|---|---|
| `list_teams` | co już mam |
| `read_team` | jak wygląda ten zespół i jego bieżąca rewizja |
| `create_team` | załóż zespół wraz z pierwszą rewizją, jednym wywołaniem |
| `revise_team` | popraw role, krawędzie, granice — nowa rewizja, poprzednia nietknięta |
| `run_team` | uruchom i oddaj identyfikator przebiegu |
| `read_run` | ślad, koszt, stan; działa też dla przebiegu, który jeszcze pracuje |
| `list_runs` | co ten zespół już robił |
| `schedule_team` | harmonogram albo wyzwalacz nad wskazaną rewizją |
| `list_schedules` | co jest ustawione, co wyzwoliło, co pominięte i dlaczego |

Katalog modeli i katalog narzędzi `teams` **nie** dostają własnych narzędzi: ich zawartość
jedzie w opisie `create_team` i `revise_team` jako to, co wolno wpisać, bo model i tak musi je
znać w chwili pisania definicji, a osobne wywołanie byłoby rundą w tę i z powrotem przed każdym
zapisem.

## Risks / Trade-offs

**Token operatora w dwóch dodatkowych procesach** → Żaden go nie utrwala: nie trafia do logu, do
bazy, do śladu narzędzia ani do treści oddawanej modelowi. Osobny test na to, że nie ma go w
logach przy włączonym `DEBUG`.

**Model widzi w opisie narzędzi, jak zbudować zespół z narzędziami handlowymi** → Nie jest to
nowa możliwość: operator ma ją w terminalu. Kontrolą jest to samo co tam — `trading-mcp` chodzi
wyłącznie na koncie demo i odmawia startu na innym, a granice handlowe są sprawdzane przed
przebiegiem. D4 pilnuje, żeby taki zespół nie dostał harmonogramu bez wiedzy operatora.

**Wydatek bez potwierdzenia** → D3 nazywa to wprost i wskazuje trzy drogi domknięcia; żadna nie
wchodzi do tej zmiany, bo decyzja operatora była świadoma i po przedstawieniu ryzyka.

**Rozjazd kontraktu `teams`** → Migawka i `scripts/contract.py check`, wzorem obu istniejących
serwerów MCP; `checks.yml` wciąga job tego modułu przy każdej zmianie `teams/contract.py`.

**Siódma aplikacja na ciasnym planie** → D5, podniesienie SKU przed pierwszym wdrożeniem.

**Token operatora wygasa w połowie długiej tury** → Wywołanie kończy się niedostępnością
nazywającą wygasłe poświadczenie, a nie cichym 401 czytanym jako brak zespołu. Rozmowa trwa
minuty, token godzinę, więc jest to przypadek brzegowy — ale taki, który przy złym komunikacie
kosztowałby wieczór szukania w Azure.

## Migration Plan

Wdrożenie jest addytywne — nic istniejącego nie zmienia zachowania. Kolejność, w której każdy
krok jest odwracalny osobno:

1. **SKU planu na B3** (D5), sprawdzone odczytem pamięci po zmianie.
2. **Moduł, lokalnie** — `teams-mcp` w `dev.sh`/`dev.ps1`, `agent` z `TEAMS_MCP_URL`
   wskazującym pętlę zwrotną. Cała ścieżka daje się przejść, zanim cokolwiek pójdzie do Azure.
3. **Infrastruktura** — App Service, tożsamość, Easy Auth z jednym wołającym, wpis w
   `allowed_applications` po stronie `teams`. `apply` operatora, nigdy CI.
4. **Wdrożenie modułu**, ze smoke checkiem sięgającym procesu.
5. **`TEAMS_MCP_URL` w ustawieniach `agent`** — dopiero teraz, i to jest moment, w którym
   narzędzia się pojawiają. Wycofanie to wyczyszczenie tej jednej zmiennej i restart: agent
   wraca do tego, czym był, a zespoły założone po drodze zostają, bo są zwykłymi zespołami
   operatora.
