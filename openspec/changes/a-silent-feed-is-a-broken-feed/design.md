## Context

Stan i pomiar są w `proposal.md` — „Why". Tu liczy się tylko to, co kształtuje rozwiązanie:

- **Biblioteka już pilnuje transportu, i to nie wystarcza.** `websockets` domyślnie pinguje
  co 20 s i zrywa połączenie, gdy pong nie wróci. Feralne połączenie żyło czternaście
  godzin, więc pongi wracały: transport był zdrowy, a subskrypcja po stronie providera
  martwa. Warstwa, która to wykryje, musi patrzeć na **dane**, nie na socket.
- **Ruch do providera jest liczony na konto**, 10 żądań na sekundę, jedną bramką dla
  całego gatewaya (`rategate.py`). Wszystko, co wznowienie kosztuje, wchodzi w ten sam
  budżet co odczyt historii, który operator właśnie zamówił.
- **Rynek zamknięty jest cichy z definicji.** Indeksy mają dobową przerwę i weekend;
  BTCUSD nie ma żadnej. Cisza sama w sobie nie odróżnia awarii od zamkniętej giełdy.
- **Gateway ma już pytanie „czy rynek handluje"** — `CapitalAdapter._market_open`, memo na
  5 sekund — ale to jest odczyt REST, a nie własność strumienia.
- **Dyscyplina modułu:** dla `DAY` i `WEEK` granica okresu nigdy nie jest liczona
  arytmetycznie. `BUCKET_SECONDS` w `stream/forming.py` nie ma tych dwóch rozdzielczości
  celowo i to musi tak zostać.

## Goals / Non-Goals

**Goals:**

- Strumień, który zamilkł, wraca sam — bez restartu procesu i bez udziału operatora.
- Czas do samonaprawy liczony w minutach, nie w godzinach, przy koszcie ruchu, który da się
  wypisać liczbą.
- Świeca w budowie nigdy nie niesie ceny z okresu, którego nie obejmuje — nawet gdy
  provider nie przysłał zamknięcia.

**Non-Goals:**

- Nie budujemy wykrywania „rynek stanął, ale jest otwarty" jako sygnału dla operatora. To
  jest monitoring i osobne pytanie (`STALE_AFTER_PERIODS`, poza zakresem — `proposal.md`).
- Nie ruszamy kształtu wiadomości na `/ws/stream`. Konsument nie dostaje nowego rodzaju
  wiadomości; dostaje ten sam `status`, który już umie czytać.
- Nie dokładamy ustawień do `.env`. Progi wynikają z zachowania providera, nie z gustu
  wdrażającego.

## Decisions

### 1. Watchdog siedzi w `Upstream`, jako termin na odbiór, a nie jako osobne zadanie

Pętla sesji czyta dziś `async for raw in ws`. Zmienia się w odczyt z terminem: brak
**danych** przez próg podnosi wyjątek, a wyjątek w `_session()` **już** oznacza dokładnie
to, co ma się stać — `_run()` publikuje status wznawiania, odczekuje i łączy się ponownie,
odtwarzając obie subskrypcje. Droga naprawy jest więc ta sama, którą moduł chodzi od
początku i którą pokrywają istniejące testy; nowa jest tylko przyczyna wejścia na nią.

Odrzucone: osobne zadanie-strażnik trzymające `last_message_at` i anulujące sesję. Daje to
samo, kosztem drugiego zadania na pokój (29 w produkcji) i drugiej drogi ubicia sesji,
która musi się nie pobić z `stop()`.

Odrzucone: watchdog w `Room`. Pokój nie ma socketu, więc musiałby prosić `Upstream`
o zerwanie — czyli ta sama decyzja, tylko przeniesiona przez granicę, której nie trzeba
przekraczać. Pokój traci przy tym jedyne, co naprawdę wie: czy wiadomości przychodzą.

**Termin liczony od danych, nie od ramki — i to jest różnica między poprawką, która działa,
a taką, która by nie zadziałała.** Utrzymanie połączenia przy życiu to wymiana z providerem,
na którą ten odpowiada niezależnie od tego, czy nadal obsługuje subskrypcję; feralne
połączenie z 24 sierpnia najpewniej odpowiadało na nie przez wszystkie czternaście godzin.
Watchdog karmiony dowolną ramką przespałby więc całą awarię. Dlatego termin jest **terminem
końcowym**, przesuwanym przez kwotowanie albo świecę i przez nic innego — a nie limitem na
pojedynczy odczyt, który każda ramka zerowałaby od nowa. Kosztem jest wznawianie na cichym
rynku, policzone niżej.

### 2. Próg 120 s, z eskalacją do 10 minut, zerowaną przez pierwszą wiadomość

Zdrowy strumień otwartego rynku niesie około pięciu kwotowań na sekundę — zmierzone
w `upstream.py` (296 kwotowań na 60 s na US100) i potwierdzone 24 sierpnia (47–265 na 25 s
na 28 pokojach). Dwie minuty ciszy są więc o dwa rzędy wielkości poza tym, co zdrowy feed
robi, a jednocześnie kosztują awarię tylko dwie minuty zamiast czternastu godzin.

Cisza po wznowieniu jest jednak zwykle ciszą rynku, nie awarią. Dlatego próg **rośnie**:
każde wznowienie, po którym znowu nic nie przyszło, podwaja tolerancję aż do **10 minut**;
pierwsza wiadomość zeruje ją do 120 s. Weekend kosztuje wtedy 29 pokoi na 10 minut, czyli
**174 wznowienia na godzinę — około 0,05 żądania na sekundę**, pół procenta budżetu konta.
Bez eskalacji byłoby 870 na godzinę i to przez dwie doby.

Odrzucone: **bramkowanie wznowień przez `_market_open`.** Kusi, bo memo już istnieje, ale
wprowadza do ścieżki życia strumienia zależność od REST-a i — co gorsza — buduje drogę do
tego, żeby zostać martwym: „rynek zamknięty" wzięte za dobrą monetę wstrzymuje wznowienia,
a to jest dokładnie ten rodzaj odpowiedzi, którego ta zmiana ma nie potrzebować. Eskalacja
ogranicza koszt bez pytania kogokolwiek o zdanie.

Odrzucone: stały, duży próg (np. 15 minut) bez eskalacji. Prostsze, ale każe zdrowej awarii
czekać kwadrans, żeby weekend był tani. Eskalacja daje jedno i drugie.

### 3. Granica `DAY`/`WEEK` ma własny zegar, też z eskalacją

`place_boundary()` przestaje wisieć na kwotowaniu — **obok** niego, nie zamiast. Pokój,
który granicy nie ma, sprawdza to na własnym tyknięciu i pyta providera, gdy okno na
kolejną próbę minęło; kwotowanie nadal jest najszybszym powodem, żeby zapytać, i dzięki
temu świeca nowego okresu pojawia się natychmiast po zamknięciu poprzedniego, a nie po
tyknięciu. Zegar odpowiada za jedyny przypadek, którego kwotowanie obsłużyć nie może: pokój
po ciszy, czyli bez granicy i bez kwotowań.

Dwa wejścia do jednego odczytu wymagają zamka: bez niego kwotowanie i tyknięcie wydają dwa
żądania na to samo pytanie i seedują pokój dwoma odpowiedziami z różnych chwil. Zamek jest
w pokoju, a pod nim `needs_boundary` jest sprawdzane jeszcze raz — kto wszedł drugi, ma już
swoją odpowiedź.

Zegar dostają tylko pokoje, które mogą go potrzebować: rozdzielczość, której początek okresu
zna wyłącznie provider. Pozostałe 21 pokoi w tym koncie nie budzi się po nic.

Ten sam próg co dziś (30 s) rośnie do 10 minut, gdy provider odpowiada „jeszcze nie ma
okresu, na którym można budować". Ta odpowiedź nie zmienia się z minuty na minutę —
w weekend nie zmieni się przez dwie doby — a osiem pokoi `DAY`/`WEEK` pytających co 30 s to
960 żądań na godzinę, prawie trzy procent budżetu, wydane na pytanie, którego odpowiedź
jest znana.

### 4. Okres, który na pewno minął, poznajemy po nominalnej długości — i to nie jest granica

`FormingCandle` dostaje drugą mapę: nominalną długość okresu, tym razem **z** `DAY` i
`WEEK`. Służy wyłącznie jako **górne ograniczenie upływu czasu**: jeżeli kwotowanie jest
późniejsze niż początek trzymanej świecy o całą tę długość, okres na pewno się skończył,
choćby sesja giełdy była krótsza. To dokładnie ten sam chwyt, którego używa już
`history.mark_forming` po stronie REST i `periods.PERIOD_SECONDS` w market-data.

Rozdzielenie map jest tu całą ostrożnością i musi być widoczne w nazwie: `BUCKET_SECONDS`
to lista rozdzielczości, które **wolno podłogować**, i `DAY`/`WEEK` nadal do niej nie
należą. Nowa mapa nie jest używana do wyliczenia początku okresu ani razu — tylko do
odpowiedzi „czy tamten na pewno minął".

Świeca po przekroczeniu tej granicy trafia w stan „okres zamknięty", ten sam co po
zamknięciu od providera, a nie w „granica nieaktualna" po zerwaniu. Różnica jest
zamierzona: tu wiemy, że okres się skończył, więc provider oddający ten sam początek okresu
to brak postępu, a nie potwierdzenie.

**Za to „zamknięty" przestaje wystarczać na pytanie, które zadaje dołączający subskrybent** —
i to wyszło dopiero przy pisaniu kodu. Pokój podaje mu świecę, którą trzyma, i oznacza ją
jako ostateczną wtedy, gdy okres minął. Dotąd okres mógł minąć wyłącznie przez zamknięcie od
providera, więc „ostateczna" znaczyło „świeca providera". Po tej zmianie okres mija także
przez upływ czasu, a świeca w ręku jest wtedy własnym złożeniem modułu — a konsument
**zapisuje to, co ostateczne** (`market_data/app.py`, `candle_sink`). Podanie jej jako
ostatecznej wpisałoby do archiwum świecę, której nikt nie zamknął. Stąd trzeci stan świecy:
czy pochodzi z zamknięcia. Dołączający dostaje ostateczną tylko wtedy.

### 5. Termin odbioru w market-data jest wolniejszy od gatewaya, i leży w warstwie socketu

Druga linia obrony ma sens tylko wtedy, gdy strzela po pierwszej. Gdyby market-data zrywał
subskrypcję szybciej, niż gateway zdąży się naprawić, naprawiałby ją zawsze niewłaściwy
moduł — a zerwanie subskrypcji jest droższe, bo ciągnie za sobą domykanie luki. Stąd
**20 minut**: dwa razy tyle, ile wynosi sufit eskalacji gatewaya, plus zapas na wznowienie.

Termin ląduje w `gateway/stream.py`, nie w `ingest/live.py`. Ten moduł ma socket i jego
zadeklarowana rola brzmi: „hands up a clean stream and lets it end" — cisza kończy iterację
tak samo jak zamknięcie połączenia. `ingest/live.py` nie zyskuje wtedy ani jednej gałęzi:
koniec strumienia już wie, co znaczy.

Próg liczy się od **dowolnej** wiadomości — inaczej niż w gatewayu, i celowo. Tam pytaniem
jest „czy provider nadal obsługuje subskrypcję", więc liczą się tylko dane; tu pytaniem jest
„czy moduł przede mną w ogóle żyje", a na to odpowiada każda ramka, status wznawiania
włącznie. Dzięki temu gateway walczący z ciszą własną eskalacją nie jest jednocześnie
zrywany od dołu.

Nie od zamkniętej świecy natomiast w żadnym z tych dwóch miejsc. Na `DAY` świeca
zamknięta pada raz na dobę, więc próg liczony od niej mierzyłby rozdzielczość zamiast
połączenia — i albo nie strzeliłby nigdy, albo strzelał codziennie bez powodu.

## Risks / Trade-offs

**Wznowienie gubi to, co pokój zdążył zobaczyć** → świeca w budowie po wznowieniu jest
przeseedowana z odpowiedzi providera, więc maksimum i minimum liczą się od tamtej wartości,
a nie od kwotowań widzianych wcześniej. To jest już dziś zachowanie każdego świeżego pokoju
i wymaganie mówi o tym wprost („odzwierciedla wyłącznie kwotowania widziane od podłączenia
modułu"). Cena tego jest mniejsza niż cena słupka, który stoi.

**Próg za niski zamienia rynek zamknięty w pętlę wznowień** → eskalacja z sufitem 10 minut,
policzona wyżej na 0,05 żądania na sekundę przy 29 pokojach. Sufit jest tym parametrem,
którego wartość trzeba obronić liczbą, jeśli kiedyś ma się zmienić.

**Próg za wysoki przedłuża awarię** → 120 s na starcie, więc typowa awaria kosztuje dwie
minuty. Najgorszy przypadek — cisza po serii cichych wznowień — to 10 minut, wobec
zmierzonych czternastu godzin.

**Nominalna długość okresu wpuszczona do `forming.py` może zostać kiedyś użyta do
podłogowania** → osobna mapa, nazwa mówiąca, do czego służy, i test, który pilnuje, że
`DAY` i `WEEK` nadal nie mają arytmetycznej granicy. To jest jedyna rzecz w tej zmianie,
która przy nieuwadze cofa wcześniejszą decyzję modułu.

**Fałszywe zerwanie na instrumencie o rzadkim handlu** → 120 s bez ani jednego kwotowania
na otwartym rynku jest możliwe dla czegoś bardzo płytkiego. Kosztuje wtedy jedno wznowienie
i przeseedowanie granicy; przy eskalacji taki instrument sam wychodzi na wyższy próg.

## Migration Plan

Nie ma migracji: żadnej bazy, żadnego ustawienia, żadnego pliku w `infra/`, żaden kontrakt
nie rusza. Wdrożenie jest zwykłym wdrożeniem obu modułów, w dowolnej kolejności — działają
niezależnie, a market-data z terminem odbioru wobec starego gatewaya zachowuje się tak jak
dziś, tylko z górnym ograniczeniem ciszy.

Wycofanie: poprzedni obraz. Stan produkcji został już odblokowany ręcznie — restart
`app-tradingcenter-gateway` 24 sierpnia 2026 o 14:05 UTC — więc to wdrożenie nie jest
lekarstwem na trwającą awarię, tylko na następną.
