## Context

Motywacja jest w `proposal.md` — „Why". Tutaj tylko to, co kształtuje podejście.

Telegram ma **dwie** powierzchnie i one nie są dwoma wariantami tej samej rzeczy. Bot API
(`api.telegram.org/bot<token>`) jest bezstanowe, autoryzowane tokenem bota i potrafi wysłać
wiadomość. MTProto jest protokołem klienta i wymaga tożsamości **użytkownika**. BotFather —
jedyna droga do założenia bota — jest zwykłym botem na czacie, więc leży wyłącznie po tej
drugiej stronie. Żadne API nie zakłada bota.

Trzy ograniczenia platformy, których projekt nie może obejść: bot **nie może napisać pierwszy**
(adresat musi raz nacisnąć Start), BotFather pozwala jednemu kontu na **20 botów**, a Bot API
limituje wysyłkę do ~30 wiadomości na sekundę łącznie i **1 na sekundę na czat**.

Dwa ograniczenia tego repozytorium, oba zmierzone: serwer bazy to `B_Standard_B1ms` z
`max_connections = 35`, a sześć istniejących pul po `max_size = 10` to już 60 potencjalnych
połączeń (`polymarket-archive-reads-in-constant-time`, 31 sierpnia 2026). I każdy App Service w tej
grupie stoi za Easy Auth, które **odrzuca ruch bez tokenu Entra przed wejściem do modułu**.

## Goals / Non-Goals

**Goals:**

- Jedno miejsce, przez które ten system pisze do Telegrama, wołane tak samo przez model i przez kod.
- Zakładanie bota bez otwierania Telegrama, tam gdzie operator na to pozwolił — i uczciwa odmowa tam,
  gdzie nie pozwolił.
- Adresowanie, które przeżywa wymianę bota.
- Sekret, który nie wychodzi w odpowiedzi ani w logu, także ten, który moduł sam wytworzył.

**Non-Goals:**

- Kolejka, ponowienia i historia wiadomości — wybór operatora, i `Decisions` niżej nazywa, czym za
  niego płacimy i co zajmuje jego miejsce.
- Odbieranie czegokolwiek poza `/start`, które wiąże adresata.
- Drugi kanał (e-mail, Discord). Nazwa modułu tego nie obiecuje — `proposal.md`, „What Changes".

## Decisions

**Wysyłka przez Bot API, MTProto wyłącznie do BotFathera.** Alternatywą było robić wszystko przez
MTProto, skoro sesja i tak bywa skonfigurowana — jedna zależność zamiast dwóch. Odrzucone z dwóch
powodów: wtedy alert przychodzi **jako wiadomość od operatora**, nie od bota, więc nie da się go
odróżnić od tego, co operator sam napisał; i każda wysyłka obciąża limity prywatnego konta, czyli
awaria zbiórki staje się ryzykiem dla konta. Dwie powierzchnie zostają dwiema drogami, a ta
z sesją jest tą, którą można wyłączyć.

**Wiązanie przez `getUpdates`, nie przez webhook.** Webhook byłby tańszy w ruchu i naturalny dla
FastAPI. Odrzucony przez Easy Auth: Telegram nie ma tożsamości Entra, więc jego POST zostaje odbity
przez platformę, zanim moduł go zobaczy. Żeby webhook działał, trzeba by wyjąć jego ścieżkę z
`excluded_paths` — a to trzecia dziura obok `/` i `/ws/stream`, tym razem przyjmująca **treść**
z internetu. `getUpdates` w tle nie potrzebuje żadnej. Kosztuje jedno długie żądanie na bota; przy
sufcie 20 botów to jest cena, którą stać nas zapłacić.

**Adresat jest nazwany, a nie jest `chat_id`.** Wywołujący pisze do `operator-primary`, nie do
`123456789`. Alternatywą było przyjmować `chat_id` w żądaniu — prostsze o jedną tabelę. Odrzucone,
bo `chat_id` trzeba skądś mieć, więc każdy wywołujący dostałby własną kopię tej samej liczby w
`.env`, a wymiana bota unieważniałaby je wszystkie naraz. Nazwa przeżywa wymianę; liczba nie.

**Znacznik „już powiedziane" stoi u wywołującego, i to on jest mechanizmem ponowienia.** Skoro
brama nie pamięta wiadomości (wybór operatora), to deduplikacja musi być czyjaś. Alternatywą był
klucz idempotencji w bramie — odrzucony, bo klucz idempotencji z czasem życia **jest** historią
wiadomości pod inną nazwą, tylko gorzej nazwaną. Zamiast tego `social-data` i `strategy` zapisują
swój znacznik **dopiero po odpowiedzi 2xx**. To daje ponowienie za darmo: nieudana wysyłka nie
stawia znacznika, więc następny przebieg pętli próbuje jeszcze raz. Cena jest realna i nazwana w
obu zdolnościach: między próbami mija cały cykl pętli, a wysyłka, która **udała się** i nie
zdążyła zapisać znacznika, powtórzy powiadomienie.

**Token bota mieszka w bazie, nie w Key Vault.** Bot założony przez moduł powstaje po wdrożeniu,
więc jego token nie istnieje w chwili `apply` — zapis do Key Vault wymagałby dania modułowi prawa
zapisu do skarbca, żeby uniknąć trzymania sekretu w bazie, którą i tak szyfruje ta sama platforma.
Odrzucone: to zamienia jeden sekret w dwie tożsamości z uprawnieniem. Token zostaje w bazie, a
zamiast tego jest twarda granica — **żadna trasa i żadne narzędzie nie zwraca tokenu**, a log go
nie widzi. To jest ta klasa reguły, gdzie pudło jest ciche, więc ma własny test.

**Odpowiedź BotFathera czytana po kształcie, nie po zdaniu.** BotFather odpowiada zdaniem w języku
naturalnym, które Telegram może zmienić bez uprzedzenia. Moduł szuka w odpowiedzi **tokenu**
(`\d+:[A-Za-z0-9_-]{35}`), a nie frazy „Done!". Odpowiedź, w której tokenu nie ma, jest odmową
oddającą pełną treść BotFathera — nigdy zgadywaniem, że pewnie się udało.

**Pula czterech połączeń, nie dziesięciu.** `min_size=1, max_size=4`. Siedem baz na serwerze z
`max_connections = 35` nie mieści siedmiu pul po dziesięć, a ten moduł jest z nich najlżejszy:
jego praca to jedno żądanie HTTP na wiadomość, a nie zapytanie na wiersz ekranu.

**MTProto za protokołem, jedna implementacja.** Klient BotFathera jest interfejsem z jedną
implementacją na Telethonie i jednym fake'iem w testach — tak jak `social-data` trzyma źródło za
protokołem. Powód nie jest estetyczny: bez tego CI potrzebowałoby konta Telegrama, a nie dostanie go.

## Risks / Trade-offs

- **Automatyzacja konta użytkownika może kosztować to konto.** Telegram ogranicza i blokuje konta
  za wzorce automatu, a tu automatem jest prywatne konto operatora → sesja jest opcjonalna i
  domyślnie nieobecna; moduł **nigdy** nie zakłada bota z własnej inicjatywy, tylko na wyraźne
  żądanie; próby są ograniczone i rozłożone w czasie, a sufit 20 botów jest sprawdzany, zanim
  moduł zagada, nie po odmowie.
- **Alert może przepaść i nikt tego nie zauważy** — bezpośredni koszt braku kolejki → wywołujący
  nie stawia znacznika po nieudanej wysyłce, więc następny przebieg ponawia; a odpowiedź bramy
  niesie odpowiedź Telegrama w całości, żeby wywołujący miał co zalogować.
- **Ten sam alert dwa razy**, gdy wysyłka się udała, a zapis znacznika nie → akceptowane świadomie:
  powtórzone powiadomienie jest tańsze niż zgubione, a odwrotny wybór wymagałby historii w bramie.
- **Adresat blokuje bota i wysyłka zaczyna zwracać 403 w nieskończoność** → adresat, którego
  Telegram odrzucił jako zablokowany, jest oznaczany i przestaje być próbowany, a jego stan mówi
  wprost, że czeka na ponowne `/start`.
- **Token bota w bazie** → nie wychodzi żadną trasą ani narzędziem, nie trafia do logu, a odczyt
  bazy wymaga tożsamości Entra tak samo jak każdy inny w tej grupie.
- **Siódma pula na jednym rdzeniu** → cztery połączenia zamiast dziesięciu, i to jest jedyne, co ta
  zmiana robi z sufitem; sam sufit zostaje na osobną zmianę w `infra/**`.

## Migration Plan

Kolejność jest ta, którą `CLAUDE.md` nazywa niepodlegającą negocjacji: `apply` operatora **MUST**
dojechać przed obrazem, który egzekwuje ustawienia, bo między jednym a drugim jest przerwa w
działaniu. Dla tej zmiany znaczy to: baza `telegram` i `scripts/grant-schema-ownership.sql` na
niej, potem tożsamości wywołujących w `allowed_applications` bramy oraz w jej
`TOOL_CALLER_APPLICATION_IDS` i `REST_CALLER_APPLICATION_IDS`, potem adresy u wywołujących, a
dopiero na końcu obrazy `social-data` i `strategy`, które te adresy czytają. Migracje moduł
stosuje sam, we własnym `lifespan`, pod swoim kluczem blokady — jak każdy inny.

Wycofanie jest tą samą dźwignią, co przy narzędziach workbencha: **wyczyścić adres u wywołującego
i zrestartować go**. `social-data` i `strategy` bez adresu bramy zbierają i decydują dalej, tylko
milczą — i to jest stan wspierany, nie awaria, więc ich testy przez niego przechodzą.

## Open Questions

- Czy adresatem bywa **kanał lub grupa**, czy tylko czat prywatny. Schemat jest ten sam (`chat_id`
  jest ujemny dla grupy), różnica jest w wiązaniu: do grupy bota się dodaje zamiast naciskać Start,
  a do kanału musi być administratorem. Da się odpowiedzieć po pierwszym użyciu, bez ruszania
  wymagań ani podziału na zadania.
