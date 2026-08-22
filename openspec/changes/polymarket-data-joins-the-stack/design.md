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
różnią się o wiele. Zamiast wybierać teraz, na wiarę, zapisujemy rodzaj wyceny przy próbce — dwa
tanie pola zamiast jednej decyzji podjętej bez pomiaru. Który rodzaj jest domyślny dla odczytu,
rozstrzyga pomiar z zadania 1.3, przed zamrożeniem kontraktu.

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

- **Kształty API dostawcy przyjęte na wiarę** → potwierdzone działającym źródłem są tylko dwie
  drogi: metadane wydarzenia po jego adresie i cena ostatniej transakcji. Szereg czasowy (jego
  parametry, maksymalne okno na żądanie, rozdzielczość dla starych zakresów) i wycena z księgi
  wymagają godziny pomiarów — zadanie 1.2, przed pisaniem klienta. Specyfikacja mówi „szereg
  czasowy dostawcy", nie obiecuje jego kształtu.
- **Limity tempa są nieudokumentowane** → własny throttle i backoff, obie wartości
  konfigurowalne, wartość początkowa wzięta z tego, co u źródła działało (6 równolegle), i do
  zmierzenia. Ryzykiem jest odcięcie modułu przy głębokim uzupełnianiu, nie utrata danych.
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

- Który rodzaj wyceny jest domyślny w odczycie: cena ostatniej transakcji czy wycena z księgi.
  Zapisujemy oba; domyślny wybiera pomiar z zadania 1.3. Nie zmienia to wymagań.
- Czy takt próbkowania ma być jeden dla wszystkich obserwacji, czy per grupa. Na tej skali jeden
  wystarcza; per grupa byłoby ustawieniem bez zmierzonej potrzeby.
- Czy zagęszczanie starszych próbek kiedykolwiek się włączy. Specyfikacja na to pozwala, ta
  zmiana tego nie robi i nie ma po temu pomiaru.
