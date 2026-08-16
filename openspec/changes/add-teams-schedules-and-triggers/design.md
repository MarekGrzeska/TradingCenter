## Context

Motywacja jest w `proposal.md` — „Why". Tu tylko to, co ogranicza rozwiązanie.

Faza 1 zostawia moduł, w którym przebieg powstaje wyłącznie z żądania HTTP: `POST
/teams/{id}/runs` sprawdza rewizję, sprawdza granicę dobową, tworzy wiersz i puszcza
`asyncio.Task`, a `RunRegistry` trzyma go w pamięci procesu. Przebieg jest własnością
procesu — `lifespan` zamyka przy starcie wszystko, co poprzedni proces zostawił otwarte.
Aplikacja stoi na jednym workerze (`infra/app-service.tf`) z `always_on = true`, więc proces
nie zasypia, ale bywa dwa razy w powietrzu naraz: przy wdrożeniu stary kontener jeszcze
odpowiada, gdy nowy wstaje.

Wszystko, co przebieg kosztuje i czym jest ograniczony, już istnieje: granica dobowa liczona
od północy UTC, granica czasu przebiegu, granica rund w agencie, ślad w `runs`, `run_steps`,
`tool_calls` i `usage`. Ta zmiana nie dokłada do tego ani jednej reguły — dokłada tylko drugi
sposób, w jaki przebieg może się zacząć.

Dwa ograniczenia architektury wchodzą w decyzje niżej: `teams` ma krawędź do `market-mcp`
i do niczego więcej po stronie rynku, a wskaźniki są własnością `market-data`. Trzecie
ograniczenie jest organizacyjne: faza 2 powstaje **równolegle**, w innym worktree, na tym
samym przodku.

## Goals / Non-Goals

**Goals.** Powtarzalność: ten sam zespół, ta sama rewizja, ta sama pora, przez tydzień, bez
człowieka. Czytelność po fakcie: z historii ma dać się odczytać nie tylko to, co się stało,
ale i to, co się nie stało i dlaczego. Przemienność z fazą 2: kolejność scalania obu gałęzi
MUST NOT mieć znaczenia.

**Non-Goals na poziomie projektu** (poza tym, co wyłącza `proposal.md`): nie budujemy
własnego rozwijania wyrażeń czasowych; nie budujemy kolejki przebiegów — nakładający się
przebieg jest pomijany, a nie odkładany; nie budujemy powiadomień poza terminalem; nie
zmieniamy niczego w tym, jak przebieg pracuje po starcie.

## Decisions

### Zegar w procesie modułu, nie w Azure

Jedno zadanie `asyncio` startujące i gasnące w `lifespan`, obok istniejącego `RunRegistry`.
Budzi się co kilkanaście sekund, przejmuje należne wyzwolenia i puszcza przebieg tą samą
drogą, którą puszcza go dziś router.

Rozważone: **Logic App albo Function z zegarem**, wołająca `POST /teams/{id}/runs` — odrzucone,
bo moduł stoi za Easy Auth, więc wołający potrzebuje własnej rejestracji Entra, wpisu
w `allowed_audiences` i tożsamości, którą trzeba komuś przypisać; do tego harmonogram żyłby
w Terraformie, czyli u operatora, a nie w bazie modułu, i operator wracałby między merge'em
a działającym harmonogramem — dokładnie ten kształt, który reguła „migracje nie są robotą
operatora" wyklucza w sąsiedniej sprawie. **WebJob** — ten sam problem, plus drugi artefakt
wdrożeniowy dla tego samego obrazu. Precedens za zegarem w procesie jest w repozytorium:
`market-data` trzyma swój `Ingest` i runner zadań we własnym `lifespan`.

Koszt tej decyzji jest jeden i jest przyjęty: zegar umiera razem z procesem. Odpowiedzią jest
zwijanie pominiętych wyzwoleń do jednego (`specs/teams-schedules`), a nie druga instancja.

### Wyzwolenie przejmowane w bazie, nie posiadane przez proces

Przejęcie to jedno zdanie: `UPDATE schedules SET next_fire_at = <następne>, last_fired_at =
now() WHERE id = $1 AND next_fire_at <= now() RETURNING …`. Kto dostał wiersz, ten wyzwala.

Rozważone: **advisory lock na cały zegar** — czyli jeden proces „liderem" — odrzucone, bo
lider trzyma lock do końca sesji i wdrożenie daje kilkadziesiąt sekund, w których nowy proces
nie robi nic, a stary zaraz zniknie; przejęcie per wiersz nie ma tego stanu pośredniego.
Rozważone: **nic**, bo plan i tak ma jednego workera — odrzucone, bo jeden worker nie znaczy
jeden proces: wdrożenie jest momentem, w którym są dwa, i dokładnie wtedy podwójny przebieg
kosztuje podwójnie.

### Trzy nowe tabele i zero zmian w tabelach fazy 1

`schedules`, `triggers`, `schedule_fires`. `runs` nie dostaje ani kolumny `origin`, ani
`schedule_id`.

Powód pierwszy jest merytoryczny: wyzwolenie, które przebiegu **nie** uruchomiło, nie ma gdzie
zamieszkać w `runs` — nie ma wiersza, na którym miałoby usiąść. A to jest połowa tego, co
operator ma zobaczyć (`specs/teams-schedules`, „Wyzwolenie bez przebiegu zostawia zapisany
powód"). `schedule_fires` z `run_id` dopuszczalnie pustym mieści oba przypadki jednym
kształtem.

Powód drugi jest organizacyjny i wynika wprost z równoległości: migracja składająca się
wyłącznie z `CREATE TABLE` jest przemienna z migracją fazy 2. Dwie gałęzie zmieniające tę samą
tabelę `runs` musiałyby się umówić, w jakiej kolejności wchodzą; dwie gałęzie dokładające
rozłączne tabele muszą tylko przenumerować rewizję Alembica.

Rozważone: **kolumna `origin` w `runs`** — odrzucona z obu powodów naraz.

### Wyrażenie cron w UTC, rozwijane przez `croniter`

Pięciopolowe wyrażenie na wierszu harmonogramu, `next_fire_at` policzone przy zapisie i przy
każdym przejęciu.

Rozważone: **sam interwał** („co 30 minut") — odrzucony, bo nie wyraża „w dni robocze pół
godziny po otwarciu", a to jest pierwszy harmonogram, jaki tu powstanie. Rozważone: **strefy
czasowe operatora** — odrzucone w tej fazie, bo moduł ma jeden zegar: dobowa granica kosztu
resetuje się o północy UTC i harmonogram w czasie lokalnym oznaczałby budżet i wyzwolenia
przesuwające się względem siebie dwa razy w roku, przy zmianie czasu. Terminal pokazuje obie
godziny obok siebie, więc cena tej decyzji jest zapłacona po stronie wyświetlania.
Rozważone: **własny parser** — odrzucony; `croniter` to jedna mała zależność bez tranzytywnych,
a rozwijanie cron jest problemem rozwiązanym dawno i źle rozwiązywanym samodzielnie.

### Warunek wyzwalacza czytany przez `market-mcp`, nie przez `market-data`

Wyzwalacz opisuje instrument, interwał, wielkość ogłoszoną przez serwer narzędzi, porównanie
i próg. Sprawdzenie to wywołanie narzędzia z tej samej sesji MCP, której używa przebieg.

Rozważone: **subskrypcja strumienia `market-data`** — odrzucona, bo to nowa krawędź
w architekturze (`teams` → `market-data`), nowy zakres w Entra i drugie źródło prawdy o rynku
w module, który już jedno ma. Rozważone: **własne liczenie wskaźnika w `teams`** — odrzucone
wprost: katalog wskaźników jest własnością `market-data`, a wyzwalacz reagujący na inną wartość
niż ta, którą zobaczy uruchomiony zespół, byłby gorszy niż brak wyzwalacza.

Efekt uboczny wart odnotowania: narzędzia czytają **archiwum**, nie dostawcę, więc odpytywanie
warunku co minutę nie zjada budżetu 10 żądań/s liczonego przez capital.com na konto. Kosztem
jest świeżość — warunek widzi rynek tak świeży, jak świeże jest archiwum, i to jest właściwy
kompromis, bo zespół po uruchomieniu zobaczy dokładnie to samo.

### Zbocze zapisane na wierszu, nie wyprowadzone z historii

`triggers` niesie wynik ostatniego sprawdzenia i moment ostatniego wyzwolenia. Wyzwolenie
następuje przy przejściu `false → true`, a `cooldown_seconds` odmierza czas martwy.

Rozważone: **wyprowadzanie zbocza z `schedule_fires`** — odrzucone, bo historia zapisuje
wyzwolenia, a nie każde sprawdzenie; zapisywanie każdego sprawdzenia dałoby tabelę rosnącą
o wiersz na minutę na wyzwalacz po to, żeby odpowiedzieć na pytanie mieszczące się w jednej
kolumnie. Stan „nieznany" (niedostępny serwer narzędzi) jest trzecią wartością obok prawdy
i fałszu, i nie jest zboczem w żadną stronę — bez tego harmonogram po cichu nie działa, a
operator widzi spokojny rynek (`specs/teams-triggers`).

### Właściciel skopiowany na wiersz; moduł niczyjej tożsamości nie używa

`schedules.owner_principal` jest kopiowany z tożsamości, która harmonogram zapisała, a przebieg
dostaje ją z harmonogramu. Wszystkie zapytania fazy 1 filtrują po właścicielu w samym zdaniu
SQL, więc przebieg bez właściciela byłby przebiegiem niewidocznym.

Rozważone: **przechowywanie tokena operatora** i wołanie w jego imieniu — odrzucone i nie jest
to bliska decyzja: token wygasa, a moduł i tak niczego cudzą tożsamością nie woła — klucz
OpenAI i tożsamość zarządzana do serwera narzędzi są jego własne. To etykieta na wierszach,
i tak jest opisana w wymaganiu.

### Podgląd najbliższych wyzwoleń liczy moduł

Osobna odpowiedź kontraktu z listą najbliższych momentów. Terminal ich nie liczy.

Rozważone: **rozwijanie cron w terminalu** — odrzucone tą samą zasadą, którą faza 1 zastosowała
do katalogu modeli i katalogu narzędzi: druga implementacja tej samej reguły po stronie
odbiorcy rozjeżdża się z pierwszą, tyle że tutaj rozjazd znaczy „operator widzi inną godzinę
niż tę, o której moduł ruszy".

### Punkty styku z fazą 2

Obie gałęzie wychodzą z tego samego przodka i żadna nie zależy od kodu drugiej. Znane punkty
styku, wypisane po to, żeby nie były odkryciem przy merge'u:

| Miejsce | Styk | Zasada |
|---|---|---|
| `migrations/versions/` | obie dokładają rewizję po `0003` | Ta scalona jako druga przenumerowuje swoją rewizję i przestawia `down_revision`. Bezpieczne, bo obie są wyłącznie `CREATE TABLE` — semantyka nie zależy od kolejności. |
| `teams/contract.py` | obie dopisują modele | Dopisywać **na końcu pliku**, w osobnej sekcji; nie przestawiać istniejących. Konflikt tekstowy sprowadza się wtedy do sklejenia dwóch bloków. |
| `teams/config.py` | obie dokładają ustawienia | Rozłączne prefiksy (`SCHEDULER_*` tutaj), dopisywane na końcu klasy. |
| `teams/app.py` | obie dokładają wpis na `app.state` i `include_router` | Najostrzejszy styk i najkrótszy: dwie–trzy linie. Dopisywać po istniejących, nie wplatać. |
| `src/data/contract.teams.generated.ts` | plik generowany | Konflikt jest **oczekiwany** i rozwiązuje się przez `pnpm contract:generate` po scaleniu, nigdy ręcznym sklejaniem. |
| `src/teams/TeamsView.tsx` | obie montują swój panel | Każda w swoich plikach; w `TeamsView.tsx` jedna linia montująca na fazę. |
| granice kosztu | faza 2 może dołożyć własne granice | Ta zmiana nie rusza `runner/cost.py` ani granicy dobowej — czyta je tylko przed wyzwoleniem. |

Styk merytoryczny jest jeden i jest ostrzejszy niż wszystkie powyższe: **iloczyn obu faz to
zespół bez nadzoru, który potrafi złożyć zlecenie.** Ta zmiana go nie włącza i nie pozwala mu
się włączyć po cichu — wymaganie „Harmonogram nad rewizją z narzędziami zapisującymi wymaga
jawnego potwierdzenia" jest napisane w kategoriach „narzędzie zmieniające stan poza modułem",
których dziś nie ma ani jednego. Dziś jest spełnione w próżni i kosztuje jeden test. W dniu,
w którym faza 2 doda pierwsze takie narzędzie, jest już na miejscu — zamiast być odkrywane
wtedy, gdy zadziała.

## Risks / Trade-offs

- **Zegar umiera z procesem** → zwijanie pominiętych wyzwoleń do jednego, licznik pominięć
  w historii i `always_on` już włączone. Druga instancja nie jest odpowiedzią: plan ma jednego
  workera świadomie.
- **Podwójne wyzwolenie przy wdrożeniu** → przejęcie wiersza warunkowym `UPDATE`; test
  odpalający dwa równoległe przejęcia tego samego wiersza.
- **Praca bez nadzoru kosztuje po cichu** → granica dobowa sprawdzana **przed** utworzeniem
  przebiegu, samoczynne wyłączenie po serii niepowodzeń, i historia, w której widać wyzwolenia
  bez przebiegu. Ocena warunku nie woła modelu, więc obserwowanie jest darmowe w tokenach.
- **Wyzwalacz reagujący na stare dane** → warunek czyta archiwum, a nie dostawcę; przyjęte
  świadomie, bo zespół po uruchomieniu czyta dokładnie to samo źródło. Instrument bez świeżego
  archiwum jest problemem po stronie `market-data` i tam jest widoczny.
- **`croniter` to nowa zależność w module** → mała, bez tranzytywnych, użyta w jednym miejscu
  i schowana za własną funkcją, więc wymiana jest lokalna.
- **Równoległość z fazą 2** → tabela styków wyżej; najostrzejszy punkt (`app.py`) to trzy
  linie, a migracje są przemienne z założenia, nie przez umowę o kolejności.

## Migration Plan

Migracja jest wyłącznie dokładająca: trzy nowe tabele, żadnego `ALTER` na tabelach fazy 1,
żadnych danych do przeniesienia. Wchodzi tą samą drogą co wszystkie — moduł doprowadza własną
bazę do rewizji obrazu we własnym `lifespan`, pod advisory lockiem, własną tożsamością, więc
tabele od razu należą do roli aplikacji i nie ma po nich nic do nadawania.

Kolejność wobec fazy 2: bez znaczenia. Gałąź scalona jako druga przenumerowuje swoją rewizję
Alembica i przestawia `down_revision` — jedna linia, bez konsekwencji semantycznych, bo obie
migracje tylko tworzą rozłączne tabele.

**Rollback.** `SCHEDULER_ENABLED=false` w ustawieniach aplikacji zatrzymuje budzenie się modułu
bez wdrażania czegokolwiek; harmonogramy zostają w bazie, przebiegi ręczne działają dalej. To
jest pierwszy lever i wystarcza na wszystko poza błędem w samym zapisie. Wycofanie obrazu cofa
kod, ale nie schemat — znana asymetria, którą `schema_version` ma wykrywać; nowe tabele są
wtedy tabelami, których nikt nie czyta.

## Open Questions

- Czy operator będzie chciał harmonogramu ograniczonego godzinami pracy rynku („tylko gdy
  instrument jest w handlu"). Odpowiedź wymaga zobaczenia kilku tygodni wyzwoleń i nie zmienia
  niczego tutaj: doszłaby jako warunek na wierszu harmonogramu, bez ruszania zegara, przejęcia
  ani historii.
- Ile wynosi rozsądna seria niepowodzeń przed samoczynnym wyłączeniem i rozsądny domyślny czas
  martwy wyzwalacza. Wymaganie mówi, że granica istnieje; liczba jest ustawieniem i pierwsza
  wartość będzie zgadnięta.
