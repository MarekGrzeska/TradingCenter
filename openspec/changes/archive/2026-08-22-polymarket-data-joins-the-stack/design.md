## Context

Powód jest w `proposal.md` — "Why". Tu tylko to, co kształtuje rozwiązanie, i to, co zmierzono na
źródle 22 sierpnia 2026.

- Moduł źródłowy (`MarekGrzeska/MarketTools`, C#) ma ~4 715 linii, z czego 1 688 (36%) to warstwa
  alertowa: Telegram, RSS Truth Social, agregator newsów, ocena „impaktu" modelem, cache warmer.
  Rdzeń, który przenosimy, to wskazanie wydarzenia po adresie, minutowe próbkowanie ceny i liczenie
  zmian w siedmiu oknach.
- Źródło zapisuje próbkę **tylko** dla rynku o dokładnie dwóch wynikach nazwanych „Yes" i „No".
  Rynki wielowynikowe przepadają po cichu — nie ma po nich śladu ani w danych, ani w logu.
- Źródło zna wyłącznie chwile, w których jego worker akurat działał. Restart zostawia dziurę na
  zawsze; nie ma niczego, co by ją później domknęło.
- Druga pętla źródła (przesunięta o pół minuty), tabela upsertów zmian i tabela deduplikacji
  powiadomień istnieją po to, żeby Telegram nie spamował. Bez Telegrama nie mają odbiorcy.
- Źródło kasuje historię starszą niż 7 dni i 6 godzin. Zbierało ceny, żeby alarmować, nie żeby
  pamiętać.
- Źródło dławiło równoległość semaforem do 6 wywołań i to działało. Limity obu publicznych API
  Polymarketu nie są udokumentowane; ta liczba jest obserwacją, nie kontraktem.
- Skala docelowa: kilkadziesiąt obserwowanych rynków w takcie minutowym. Dla 20 rynków
  dwuwynikowych to ~29 tys. wierszy dziennie — obok archiwum świec jest to wielkość pomijalna.
- Oba API dostawcy są publiczne i nie wymagają klucza. To pierwszy upstream w tym repozytorium,
  wobec którego moduł nie ma się czym przedstawić.

### Pomiar dostawcy, 22 sierpnia 2026

Zadania 1.1–1.5, wykonane przed napisaniem klienta. Osiem rzeczy, z których **cztery zaprzeczyły
temu, co ta zmiana zakładała**, i jedna z nich zmieniła wymaganie w `polymarket-data-upstream-access`.

1. **`outcomePrices` z Gammy to co do cyfry midpoint z CLOB-a, dla każdego wyniku naraz.** Zmierzone
   na `epl-bre-tot-2026-08-22` (3 rynki, 6 wyników): Gamma `["0.465","0.535"]` wobec CLOB
   `midpoint=0.465` i `0.535`; tak samo dla dwóch pozostałych rynków. `lastTradePrice` z Gammy
   zgadza się z `last-trade-price` z CLOB-a dla tokenu „Yes". Skutek jest duży i opisany niżej jako
   decyzja: **jedno wywołanie Gammy na wydarzenie daje ceny wszystkich wyników**, zamiast dwóch
   wywołań CLOB-a na rynek. Dla wydarzenia o 128 rynkach to 1 żądanie zamiast 256.
2. **`prices-history` ma twardy sufit okna: 15 dni.** 15 dni przechodzi, 16 już nie
   (`400 invalid filters: 'startTs' and 'endTs' interval is too long`). Sufit jest na **przedziale
   czasu**, nie na liczbie punktów — nie da się go obejść zgrubniejszym `fidelity`.
3. **`endTs` nie jest respektowane.** Prośba o okno sześciu godzin kończące się dobę wcześniej
   wróciła z punktami aż do chwili bieżącej. Krawędź górna jest po naszej stronie: to, co ląduje
   w archiwum, musi być przycięte przy zapisie, a nie tylko w żądaniu.
4. **`fidelity` jest życzeniem, nie kontraktem, a takt jest nierówny.** Odstępy w jednym szeregu:
   57, 59, 60, 61, 63 sekundy, a przy szerszym oknie dostawca sam przechodzi na rzadszy takt. Punkt
   bazowy okna zmian MUST być dopasowywany z tolerancją — to jedyna rzecz, którą źródło robiło
   dobrze i której nie da się uprościć.
5. **Historia rozstrzygniętego rynku bywa pusta.** Na pięciu ostatnio zamkniętych wydarzeniach:
   jedno oddało 193 punkty, cztery oddały zero. Dostawca nie obiecuje, że pamięta — po
   rozstrzygnięciu **nasze archiwum jest jedynym zapisem**. To zamienia „nie kasujemy" z decyzji
   estetycznej w jedyną wersję, która ma sens, i zamyka drogę „dociągniemy sobie później".
6. **Brzeg dostawcy filtruje po `User-Agent`, i to dokładniej, niż wyglądało z pierwszego
   pomiaru.** Pierwsze sprawdzenie mówiło „żądanie bez `User-Agent` dostaje `403 error code:
   1010`" i było błędne — to, co dostało 403, było domyślną wartością `urllib`
   (`Python-urllib/3.12`), na obu powierzchniach. Sprawdzone potem osobno: **brak nagłówka,
   pusta wartość, `python-httpx/0.28.1` i `python-requests/2.32` przechodzą (200)**; blokowane
   jest `Python-urllib/*`. Skutek dla modułu jest mniejszy, niż zapowiadał pomiar, ale
   niezerowy: brzeg **wybiera po tym nagłówku**, więc domyślna wartość biblioteki jest
   wartością, o której decyduje ktoś inny. Moduł wysyła własną, stałą — i to jest jedyny
   powód, dla którego `PROVIDER_USER_AGENT` istnieje. Objaw, gdyby lista się zmieniła, czyta
   się jak blokada adresu i prowadzi śledztwo w złą stronę.
7. **Limity tempa: 30 kolejnych wywołań w 2,5 s (~12/s) bez jednej odmowy.** Semafor 6 ze źródła
   jest ostrożny i zostaje jako wartość początkowa, ale nie jest krawędzią, o którą ktoś się obił.
8. **Listing Gammy jest ciężki: ~19 KiB na wydarzenie**, 100 wydarzeń to 10 MiB, i nie ma parametru
   ograniczającego pola. Odchudzanie jest po naszej stronie — narzędzie `browse_events` MUST
   projektować pola, zanim cokolwiek odda modelowi.

Dwie rzeczy potwierdzone bez niespodzianek: `events/slug/{slug}` oddaje pojedyncze wydarzenie
z rynkami i tokenami, a `outcomes`, `outcomePrices` i `clobTokenIds` przyjeżdżają jako **stringi
z JSON-em w środku**, do sparsowania przy zapisie. Filtrowanie po `tag_id` działa i wystarcza za
przeglądanie kategoriami.

Jedna liczba dla porządku: dla wydarzenia `epl-bre-tot-2026-08-22` suma cen „Yes" trzech rynków
wyniosła 1,005. Reguła wzajemnego wykluczania nie daje jedności i nie wolno na niej opierać
dopełnienia.

## Goals / Non-Goals

**Goals:**

- Prawdopodobieństwo z rynku predykcyjnego jest szeregiem czasowym, który agent i zespół czytają
  tak samo jak świecę — z archiwum, nie z cudzej aplikacji.
- Pętla agentowa domknięta: model przegląda publiczną bazę, wybiera, obejmuje obserwacją, a godzinę
  później inny agent czyta już zebraną historię.
- Jedna lista obserwacji i jedna baza dla operatora i dla modelu. Nie dwa światy.
- Nowy moduł jest powtórzeniem wzorów, które w tym repozytorium już działają, a nie czwartym
  sposobem robienia tego samego.

**Non-Goals:**

- Handel na Polymarkecie. Ten system tam niczego nie kupuje i nie sprzedaje; gdyby kiedyś miał,
  granica bramka/narzędzia byłaby wtedy do postawienia od nowa.
- Alerty, powiadomienia, tłumaczenia i ocena wagi zdarzenia modelem. To robi workbench, i robi to
  na danych z tego modułu.
- Podstrona terminala. Konsumuje wygenerowany kontrakt, nie dodaje wymagania, jedzie zwykłą
  ścieżką po zarchiwizowaniu tej zmiany.
- Zgadywanie limitów dostawcy. Konfigurowalne, zmierzone, nie wpisane na stałe.

## Decisions

### Jeden moduł z dwiema powierzchniami, a nie bramka i moduł narzędzi

Rozważono trzy kształty.

**(A) Wybrany.** Jeden moduł `polymarket-data` z własną bazą, kontraktem REST i trasą `/mcp`
w jednym procesie — wprost wzór `market-data`. Powód jest ten sam, dla którego `market-mcp`
przestał istnieć: osobny proces MCP nad cudzym archiwum nie dokłada nic poza hopem sieciowym
i drugą kopią schematu do rozjechania.

**(B) Bramka + moduł narzędzi**, wzór `capital-gateway` + `trading-mcp`. Odrzucone: tamta granica
biegnie tam, gdzie kończy się odczyt, a zaczyna pieniądz — `trading-mcp` istnieje, żeby zapis do
rachunku miał własny proces, własną tożsamość i własne sprawdzenie demo. Na Polymarkecie nie ma
pieniądza, więc nie ma czego odgraniczać, a druga aplikacja kosztowałaby App Service, tożsamość
i deploy bez jednego argumentu za.

**(C) Rozszerzenie `market-data`.** Odrzucone: rynek predykcyjny nie jest instrumentem, jego cena
nie jest świecą, jego dostawca nie jest capital.com, a integralność archiwum świec jest w tym
repozytorium nietykalna. Doklejenie drugiego dostawcy do modułu, którego jedynymi drzwiami jest
gateway, kosztowałoby dokładnie tę własność.

### Zapis przez narzędzie ograniczony do listy obserwacji

`market-data-tools` trzyma wprost regułę „zestaw wyłącznie czyta" i mówi, że nie SHALL istnieć
przełącznik, który to zmienia. Ten moduł tej reguły nie dziedziczy i to jest decyzja, nie
przeoczenie — dlatego jest nazwana w specyfikacji, a nie przemycona w kodzie.

Rozstrzyga, co zapisem naprawdę jest. Tam zapisem byłoby mutowanie archiwum świec: dane, których
nikt nie odtworzy, i moduł, w którym cicha zmiana jest korupcją. Tu zapisem jest **lista
obserwacji** — dokładnie to, co operator i tak klika w terminalu, w pełni odwracalne, bez skutku
poza tym, że moduł zaczyna albo przestaje odpytywać dostawcę.

Granica przebiega gdzie indziej i jest równie twarda: żadne narzędzie nie kasuje historii cen,
żadne nie zmienia konfiguracji modułu i żadne nie dotyka rachunku. Kasowanie zostaje czynnością
kontraktu REST, świadomie, bo to jedyna operacja w tym module, której nie da się cofnąć.

Alternatywa — wszystkie dziewięć narzędzi tylko do odczytu, a obserwacje wyłącznie z terminala —
została odrzucona po nazwaniu tego, co zostaje: operator prosi „poszukaj rynków o cłach", model
znajduje sześć kandydatów i **nie może nic z nimi zrobić** poza wypisaniem adresów do ręcznego
przeklikania. Odczyt bez zapisu zostawia pętlę agentową rozciętą dokładnie w środku.

### Zmiany w oknach liczone przy odczycie, bez tabeli i bez drugiej pętli

Źródło ma osobny worker, tabelę upsertów, marginesy dopasowania punktu bazowego i tabelę
deduplikacji powiadomień — wszystko po to, żeby bot telegramowy nie powtarzał alertu. Bez
Telegrama te cztery rzeczy nie mają odbiorcy.

Zmiana 5m…7d to zapytanie z oknem po posiadanej historii. Przy kilkudziesięciu rynkach w takcie
minutowym jest to grosze, a w zamian znika stan do pielęgnowania, znika rozjazd między tabelą
a historią i znika pytanie „dlaczego zmiana pokazuje coś innego niż wykres". Tolerancja na nierówny
takt zostaje, bo próbki nie padają co do sekundy — ale jest częścią zapytania, nie osobnej tabeli.

Wracamy do materializacji, gdy pomiar pokaże, że kosztuje za dużo. Nie wcześniej.

### Cena jest zapisywana per wynik, a rodzaj wyceny jest polem

Model danych trzyma cenę na **wynik** (`outcome`), nie na parę Yes/No, i nie wylicza drugiej
wartości jako dopełnienia pierwszej. Powód jest mierzalny: wydarzenia typu „kto wygra" składają się
z rynków powiązanych regułą wzajemnego wykluczania, w których suma cen „Yes" nie musi być
jednością. Dopełnienie byłoby liczbą wyglądającą jak dana.

Cena ostatniej transakcji i wycena z księgi odpowiadają na różne pytania, a na płytkim rynku
różnią się o wiele — zmierzone na cienkim rynku tego samego dnia: `last_trade` 0,003 przy
`bid/ask` 0,002/0,004, czyli spread wielkości dwóch trzecich ceny. Rodzaj wyceny jest więc polem
przy próbce, nie założeniem.

**Domyślną wyceną jest midpoint** i rozstrzygnął to pomiar 1.1, nie preferencja: midpoint jest
jedyną wyceną, którą dostawca podaje **dla każdego wyniku naraz** (`outcomePrices`), więc jest
jedyną, którą da się zebrać kompletnie w jednym wywołaniu na wydarzenie. `last_trade` przyjeżdża
w tym samym wywołaniu, ale tylko dla strony „Yes" rynku, więc jest zapisywany tam, gdzie jest,
i nie jest domyślną serią odczytu.

### Próbkowanie idzie przez metadane, nie przez token

Dopisane po pomiarze 1.1, bo pierwotny plan powtarzał tu źródło. Źródło odpytuje CLOB-a **osobno
dla każdego tokenu** — dwa wywołania na rynek, w takcie minutowym. Zmierzone: `outcomePrices`
z Gammy to ta sama liczba co `midpoint` z CLOB-a, dla wszystkich wyników wydarzenia, w jednym
żądaniu.

Moduł próbkuje więc **wywołaniem na wydarzenie**, nie na token. Dla dwudziestu obserwowanych
wydarzeń to 20 żądań na minutę zamiast setek, a dla jednego wydarzenia typu „kto wygra" (128
rynków) — jedno zamiast 256. Bez tego sufit obserwacji musiałby być liczony w rynkach i byłby
niski; z tym jest liczony w wydarzeniach i jest hojny.

Cena jest w tej decyzji jedna: równoważność obu powierzchni jest **zmierzona, nie obiecana**.
Dlatego moduł zapisuje przy próbce, z której powierzchni ją wziął, a test sprawdza równoważność
wobec CLOB-a na próbie — rozjazd ma się objawić czerwonym testem, a nie serią, która po cichu
zmieniła znaczenie. Ścieżka przez CLOB-a zostaje w kliencie jako droga sprawdzająca i awaryjna.

### Historia nie ma terminu ważności

Źródło kasowało po 7 dniach, bo alarmowanie starszych danych nie potrzebuje. Archiwum ich
potrzebuje: historia rozstrzygniętego rynku jest jedynym materiałem, na którym da się sprawdzić,
czy rynek predykcyjny cokolwiek zapowiadał. Przy ~29 tys. wierszy dziennie nie ma po co kasować.

Zagęszczanie starszych próbek jest w specyfikacji jako MAY, żeby dało się je włączyć bez zmiany
wymagań — ale nie wchodzi w tę zmianę i nie ma go w zadaniach.

### Nazwa wymagania w `teams-tool-access` zostaje, mimo że mówi „z dwóch serwerów"

Delta uogólnia treść wymagania „Ta sama nazwa narzędzia z dwóch serwerów jest odmową" do dowolnej
liczby serwerów, ale **nie zmienia jego nazwy ani nazw dwóch istniejących scenariuszy**. OpenSpec
dopasowuje `MODIFIED` po nagłówku; przemianowanie jest osobną operacją (`RENAMED`, „name changes
only"), której to repozytorium nie użyło ani razu, a złożenie jej z `MODIFIED` w jednej delcie
zablokowałoby archiwizację. Trzeci scenariusz jest dołożony, bo dokładanie jest bezpieczne.

Nazwa zostaje do naprawienia osobno, gdy będzie po co użyć `RENAMED` — koszt jest jedną linią
niespójności między tytułem a treścią, a alternatywą było ryzyko przy zamykaniu zmiany.

## Risks / Trade-offs

- **Uzupełnianie przeszłości jest oknami po 15 dni i nie ma od tego ucieczki** → sufit jest na
  przedziale czasu, nie na liczbie punktów, więc zgrubniejszy `fidelity` nic nie daje. Rok wstecz
  to 25 okien na wynik. Przy głębokim uzupełnianiu to ono, a nie takt, jest głównym ruchem do
  dostawcy.
- **Górna krawędź okna jest po naszej stronie** → `endTs` nie jest respektowane, odpowiedź biegnie
  do chwili bieżącej. Przycięcie MUST być sprawdzone przy zapisie, nie tylko wysłane w żądaniu;
  inaczej okna zachodzą na siebie i „zebrany zakres" mówi więcej, niż zweryfikowano.
- **Rozstrzygnięcie kasuje historię u dostawcy** → cztery z pięciu ostatnio zamkniętych rynków
  oddały zero punktów. Nie ma drogi „dociągniemy po fakcie": czego nie zebraliśmy przed
  rozstrzygnięciem, tego nie będzie. To podnosi cenę każdej przerwy w zbieraniu i jest powodem,
  dla którego domknięcie luki przy starcie jest zadaniem, a nie usprawnieniem.
- **Limity tempa są nieudokumentowane** → zmierzone ~12 żądań/s bez odmowy, ale to obserwacja
  z jednej minuty, nie kontrakt. Własny throttle i backoff, obie wartości konfigurowalne, wartość
  początkowa wzięta z tego, co u źródła działało (6 równolegle). Ryzykiem jest odcięcie modułu
  przy głębokim uzupełnianiu, nie utrata danych.
- **Równoważność Gammy i CLOB-a jest zmierzona, nie obiecana** → cała oszczędność próbkowania stoi
  na tym, że `outcomePrices` to midpoint. Gdyby dostawca to rozłączył, seria zmieniłaby znaczenie
  bez jednego błędu. Stąd zapisany rodzaj wyceny przy próbce i test sprawdzający równoważność na
  próbie, zamiast założenia w komentarzu.
- **Rynki wielowynikowe i reguła wzajemnego wykluczania** → model danych to udźwignie, ale
  narzędzia i podstrona MUST prezentować wydarzenie, nie udawać, że każdy rynek jest niezależną
  monetą. Podstrona jest poza tą zmianą, więc pierwszym miejscem, gdzie to widać, są narzędzia.
- **Trzeci serwer narzędzi w workbenchu** → koszt jest w każdej turze rozmowy: opisy trzech
  zestawów czyta model za każdym razem. Stąd sufit powierzchni w specyfikacji narzędzi i dziewięć
  narzędzi, a nie piętnaście.
- **Zapis jako zdolność modelu** → „dodaj co ciekawe" może skończyć się setką obserwacji. Sufit
  jest w specyfikacji, sprawdzany przy obu powierzchniach, z odmową mówiącą wprost, co zrobić
  najpierw. Odmowa jest tania; niewidzialny wzrost obciążenia nie jest.
- **Port 8070 jest dziś udokumentowany jako niczyj** → `.env` wskazujący 8070 czyta się w tym
  repozytorium jako serwer wyłączony. Zajęcie portu bez edycji tej linii w `CLAUDE.md` i wiersza
  w `dev.py` tworzy dokumentację zaprzeczającą rzeczywistości. Jest to zadanie, nie uwaga.
- **Kolejność produkcyjna** → ustawienia (`POLYMARKET_MCP_URL`, listy wołających) MUST dotrzeć do
  workbencha **przed** obrazem, który ich wymaga. Apply po deployu to przerwa w działaniu między
  jednym a drugim. Cofnięcie tą samą dźwignią: wyczyść URL, restart.
- **Zmiana rusza `azuread_*`** → `terraform-apply.yml` odmówi, `apply` jest lokalny, operatora.
  Znany kształt, opisany w `CLAUDE.md`.

## Migration Plan

1. **Moduł powstaje i jedzie lokalnie** — baza `polymarket` w kontenerze `compose.yaml`, migracje
   pod własnym kluczem blokady, wiersz w tabeli startowej `dev.py`. Nic w produkcji się nie zmienia.
2. **Wdrożenie modułu** — App Service z własną tożsamością, Easy Auth, `deploy_probe.py`. Moduł
   stoi i odpowiada; nikt go jeszcze nie woła.
3. **`apply` operatora** — `POLYMARKET_MCP_URL` i zakres w ustawieniach workbencha, tożsamość
   workbencha w `allowed_applications` i `TOOL_CALLER_APPLICATION_IDS` nowego modułu.
4. **Wdrożenie workbencha** z trzecią parą ustawień. Kolejność 3 → 4 jest wiążąca.
5. **Sprawdzenie** — rozmowa widzi dziewięć nowych narzędzi; zespół z przypisanym narzędziem
   Polymarketu rusza; zespół bez nich rusza tak samo, gdy URL jest pusty.
6. **Rollback** — wyczyścić `POLYMARKET_MCP_URL`, restart workbencha. Moduł zbiera dalej,
   narzędzia znikają.

## Open Questions

- ~~Który rodzaj wyceny jest domyślny w odczycie.~~ Rozstrzygnięte pomiarem 1.1 i 1.3: midpoint,
  bo jest jedyną wyceną kompletną dla wszystkich wyników w jednym wywołaniu.
- Jak głęboko uzupełniać wstecz przy nowej obserwacji. Okno kosztuje 15 dni, więc głębokość jest
  wprost liczbą żądań; wartość początkowa jest ustawieniem, a nie decyzją tej zmiany.
- Czy takt próbkowania ma być jeden dla wszystkich obserwacji, czy per grupa. Na tej skali jeden
  wystarcza; per grupa byłoby ustawieniem bez zmierzonej potrzeby.
- Czy zagęszczanie starszych próbek kiedykolwiek się włączy. Specyfikacja na to pozwala, ta
  zmiana tego nie robi i nie ma po temu pomiaru.
