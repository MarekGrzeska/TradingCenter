## Context

Motywacja jest w `proposal.md` — „Why". Tu tylko to, co kształtuje podejście, i jedna rzecz
zmierzona w kodzie 22 sierpnia 2026, która zmienia charakter tej zmiany.

**Terminal bierze dziś jeden token i wozi go do wszystkich backendów.** `EntraConfig` ma
pojedyncze pole `scope`, a `acquire()` pyta zawsze o nie (`src/auth/entra.ts`). Ten token ma
publiczność `market-data`, a workbench i gateway zostały skonfigurowane tak, żeby ją
przyjmować — gateway jako trzecią publiczność obok własnych dwóch (`b087164`, „the gateway
accepts both spellings of market-data's audience"). Rozdział publiczności istnieje więc
w infrastrukturze, ale nie w terminalu.

**Infrastruktura już to przewidziała.** `azuread_application_pre_authorized` stoi dla
terminala przy **wszystkich trzech** rejestracjach, a komentarz przy tej dla gatewaya mówi
wprost, że jest „standing ready rather than in use today" i że proszenie o gateway po imieniu
jest zmianą po stronie terminala. Nie trzeba więc niczego odkręcać — trzeba skorzystać.

Reszta kontekstu jest dostępna bez pracy: kontrakt `polymarket-data` jest wdrożony
i sprawdzony na produkcji, a `contract.polymarket.generated.ts` istnieje i jest sprawdzany
przez `contract:check`. `terminal-shell` gwarantuje, że dołożenie zakładki nie rusza żadnej
innej. `lightweight-charts` 5.0.9 jest już zależnością.

## Goals / Non-Goals

**Goals:**

- Rozdzielić publiczności tokenu w terminalu na tyle, żeby zakładka mogła wołać
  `polymarket-data` własnym poświadczeniem, a nie cudzym.
- Postawić wykres serii prawdopodobieństwa, który mówi prawdę o pokryciu — dziura widoczna
  jako dziura, granica narysowana.
- Zrobić to bez zmiany jednej linii w `polymarket-data`.

**Non-Goals:**

- Przepisywanie warstwy wywołań. Zmienia się **czym** jest zakres, nie kto dokłada token.
- Ujednolicanie tego, co każdy backend robi z odmową. Cztery moduły mają cztery kształty
  odmowy i sprowadzanie ich do jednego jest osobną pracą, której nikt nie zmierzył.
- Nowy typ wykresu w bibliotece. Seria prawdopodobieństwa dostaje wykres liniowy, nie własny
  silnik rysujący.

## Decisions

### D1. Zakres na moduł, nie jeden na terminal

`EntraConfig.scope` przestaje być jednym napisem i staje się zakresem **na endpoint**;
`acquire()` przyjmuje zakres modułu, który jest właśnie wołany. Każdy klient HTTP dostaje
swój przy budowie, tak samo jak dostaje dziś adres bazowy.

Rozważono trzy warianty.

**(A) Wybrany.** Powyższy. Wybrany, bo alternatywa aktywnie psuje własność, którą ten system
gdzie indziej trzyma twardo: identyfikator jest tożsamością, nie etykietą. Jeden token
przyjmowany przez cztery bramy znaczy, że wyciek z dowolnej zakładki otwiera wszystkie cztery
moduły, a publiczność tokenu przestaje cokolwiek stwierdzać. Koszt jest realny i jest zapisany
w Risks: rusza warstwę, z której korzysta każda istniejąca zakładka.

**(B) Dopisać publiczność `market-data` do `allowed_audiences` polymarket-data.** Odrzucone.
Zerowa praca w terminalu i zamknięta w jednej zakładce — ale to czwarte ustępstwo tego samego
kształtu, a każde następne jest tańsze od poprzedniego i trudniejsze do cofnięcia. Jest też
szczególny powód, żeby nie robić go **tutaj**: ten moduł ma trasę kasującą historię, której
dostawca nie odda, więc jest najgorszym miejscem na poszerzanie zasięgu jednego poświadczenia.

**(C) Rozdział publiczności jako osobna zmiana, teraz (B).** Odrzucone. Dług już raz został
odłożony — pre-autoryzacje stoją nieużywane od sierpnia — a zmiana, która i tak musi ruszyć
rejestrację Entra tego modułu, jest najtańszym momentem, żeby go spłacić.

**Co z pozostałymi trzema.** Skoro zakres jest na endpoint, wszystkie cztery dostają swój od
razu: pre-autoryzacje istnieją, więc to jest wpisanie wartości, nie nowa zgoda. Wymaganie
`terminal-identity` po zmianie mówi „token wzięty dla jednego MUST NOT być wysłany do
drugiego", a terminal, w którym trzy moduły dalej dzielą jeden token, tego wymagania nie
spełnia.

### D2. Zakresy wchodzą do builda jako literały, nie jako zmienne repozytorium

`VITE_ENTRA_SCOPE` przychodzi dziś z `vars.TERMINAL_ENTRA_SCOPE`, ustawianej ręcznie
z outputu Terraforma. Cztery zakresy to byłyby cztery takie zmienne i cztery okazje, żeby
jedną zapomnieć — a błąd zobaczy się dopiero przy logowaniu, komunikatem o publiczności.

Adresy backendów są w `deploy-terminal.yml` **literałami** (`https://app-tradingcenter-market-data.azurewebsites.net`
i pozostałe trzy). Zakresy mają dokładnie ten sam charakter — są jawne, deterministyczne
(`api://tradingcenter-<moduł>/access_as_user`) i widoczne w każdym żądaniu autoryzacji
z przeglądarki — więc idą obok adresów, jako literały. `vars` zostają tylko dla client id
i tenant id, których terminal nie może wyprowadzić.

Odrzucone: cztery zmienne `vars`. Więcej kroków operatora bez jednej rzeczy w zamian.

### D3. Wykres liniowy na `lightweight-charts`, ale nie na `chart/Chart.tsx`

Biblioteka jest już zależnością i umie to, czego ta seria wymaga: stałą skalę osi wartości,
przerwy wyrażone jako brak punktu (nie jako zero), i linię poziomą do narysowania granicy.

Czego świadomie **nie** ma być: `chart/Chart.tsx` to wykres świecowy z obiektami rysowanymi
przez operatora, prymitywami, profilem czasu i sterowaniem przez agenta. Wspólne z tą serią
ma tylko oś czasu. Recykling tamtego komponentu wciągnąłby cały ten aparat do zakładki, która
go nie potrzebuje, i związałby dwie rzeczy, które zmieniają się z całkiem innych powodów —
`terminal-chart` i `agent-chart-control` nie mają tu nic do rzeczy.

Odrzucone: nowy silnik rysujący. Nie ma wymagania, którego biblioteka nie unosi.

**Dziura zostaje dziurą.** Seria idzie do wykresu z rzeczywistymi momentami, a odcinek między
dwoma punktami rozdzielonymi brakiem pokrycia MUST NOT powstać. To nie jest efekt uboczny
biblioteki, tylko rzecz do zrobienia i do przetestowania — bo domyślne zachowanie wykresu
liniowego jest odwrotne.

### D4. Kasowanie historii jest tutaj, bo nigdzie indziej nie może być

Decyzja jest w `proposal.md` — tu tylko odrzucona alternatywa. **Zostawić zdolność bez drzwi**
było rozważane i odrzucone: `polymarket-data` ma tę trasę, specyfikacja świadomie odebrała ją
narzędziom modelu jako jedyną nieodwracalną, a `REST_CALLER_APPLICATION_IDS` jest puste. Bez
tego ekranu jedyny sposób jej użycia to `psql` albo tymczasowy wpis w liście wołających —
czyli obejście, a obejście dla czynności nieodwracalnej jest gorsze niż przycisk
z potwierdzeniem.

### D5. Zmiana infrastruktury i wdrożenie terminala są dwoma krokami, w tej kolejności

Znany kształt, ale **pułapka jest tu odwrócona** i dlatego jest zapisana. Zwykle groźne jest
wdrożenie obrazu przed ustawieniami, bo obraz egzekwuje coś, czego nie ma. Tu obrazem, który
zaczyna wołać, jest **terminal**, i jego porażka wygląda inaczej: przy braku delegowanego
zakresu logowanie kończy się błędem o nieznanym zasobie, a przy braku terminala
w `allowed_applications` albo w `REST_CALLER_APPLICATION_IDS` zakładka dostaje odmowę, którą
łatwo przeczytać jako moduł nieosiągalny. Stąd osobne wymaganie o odróżnianiu odmowy od
niedostępności.

### D6. Ustępstwo gatewaya zdejmujemy, ale ostatnie

Gdy terminal prosi o gateway po imieniu, przyjmowanie przez ten moduł publiczności
`market-data` jest konfiguracją martwą — i dokładnie tym rozlaniem, którego D1 zabrania.
Zdjęcie jej jest ostatnim krokiem planu, po wdrożeniu terminala i po sprawdzeniu, że ekran
kont działa: usunięte wcześniej, odetnie terminal od gatewaya na czas między jednym
wdrożeniem a drugim.

## Risks / Trade-offs

- **Zmiana w warstwie tożsamości dotyka każdej istniejącej zakładki** → największe ryzyko tej
  zmiany i jedyny powód, dla którego rozważano wariant (B). Ograniczenie: kształt zostaje
  ten sam — token dokłada wspólna warstwa, zmienia się wyłącznie to, o który zakres pyta —
  a konfiguracja z jednym zakresem MUST dalej działać, żeby praca lokalna i `pnpm dev` nie
  zależały od czterech wartości.
- **Cztery zakresy to cztery ciche pomyłki** → literały w jednym pliku obok adresów, których
  dotyczą (D2), i test, że każdy klient dostaje zakres modułu, do którego mówi.
- **Kasowanie jest nieodwracalne mocniej niż gdziekolwiek indziej w tym systemie** → dostawca
  nie oddaje historii rynku rozstrzygniętego. Potwierdzenie MUST nazwać zakres i tę
  nieodwracalność; nie ma tu kosza ani cofnięcia i nie należy go udawać.
- **Migawka rośnie z listą obserwowanych** → jedno żądanie na całą listę, sufit 50 wydarzeń
  po stronie modułu. Gdyby to przestało wystarczać, odpowiedzią jest stronicowanie migawki
  w module, nie żądanie na wynik w terminalu — to ostatnie psuje spójność chwili (spec,
  „Ceny całej listy biorą się z jednego żądania").
- **Odmowa z powodu uprawnienia wygląda jak awaria** → ryzyko zmierzone w tym repozytorium
  wcześniej i dlatego jest wymaganiem, nie uwagą.

## Migration Plan

1. **Terminal i infrastruktura powstają razem**, ale wchodzą osobno. Nic w `polymarket-data`
   się nie zmienia.
2. **`apply` operatora** — delegowany zakres na rejestracji Easy Auth `polymarket-data`,
   pre-autoryzacja terminala, terminal w `allowed_applications` i w
   `REST_CALLER_APPLICATION_IDS`. Zmiana rusza `azuread_*`, więc `apply` jest operatora
   z konstrukcji. Do tego momentu terminal na produkcji nie ma zakładki i nic go to nie
   obchodzi.
3. **Wdrożenie terminala** z czterema zakresami i zakładką. Kolejność 2 → 3 jest wiążąca.
4. **Sprawdzenie** — logowanie przechodzi bez dodatkowej zgody (pre-autoryzacje stoją),
   zakładki kont, zespołów i wykresu działają dalej, zakładka Polymarket pokazuje listę
   i przebieg.
5. **Zdjęcie ustępstwa w gatewayu** (D6) — osobny `apply`, po 4.
6. **Rollback** — zdjąć zakładkę z rejestru i wdrożyć terminal ponownie; moduł zbiera dalej,
   nic w danych się nie dzieje. Rollback samego rozdziału zakresów to przywrócenie jednego
   zakresu w `deploy-terminal.yml`, dopóki krok 5 nie został wykonany.

## Open Questions

- Czy zakładka ma odświeżać się sama, jak `terminal-collection-history`, czy tylko na żądanie.
  Takt próbkowania to 60 s, więc automat ma sens, ale to nie zmienia ani specyfikacji, ani
  kształtu widoku — da się dołożyć po pierwszym dniu używania i wtedy będzie wiadomo, czy
  przeszkadza.
