## Context

Motywacja: `proposal.md`, „Why". Wymagania: delty w `specs/`.

Co już stoi i co z tego wynika:

- `chart_drawings` ma cztery kolumny geometrii, `label`, `color`, `created_at`
  i `updated_at` — dokładanie jednej kolumny jest tu ruchem tanim, a tabela nie ma na sobie
  nic, co by na tym ucierpiało (`0007_chart_drawings.py`).
- `draw_on_chart` jest przyrostowe i bierze dziś `add` oraz `remove`, w jednej transakcji,
  z regułą „w całości albo wcale". Nieznany identyfikator w `remove` odrzuca **całe**
  wywołanie i cofa resztę — sprawdzone w
  `test_a_removal_that_names_one_missing_id_takes_back_the_others`. To jest wzorzec,
  którego `hide`/`show` mają się trzymać, a nie wymyślać drugi.
- `PATCH /drawings/{id}` przyjmuje `PatchDrawingIn`, gdzie `None` na polu znaczy „zostaw,
  jak jest", a walidator `_asks_for_something` odrzuca żądanie, które nic nie zmienia.
- `Chart.tsx` buduje prymitywy z `drawnObjects` i ma pętlę sprzątającą, która odczepia
  prymityw każdego identyfikatora, którego w tej tablicy nie ma.
- Kolor rysunku jest od `terminal-chart-object-selection` funkcją identyfikatora, nie
  pozycji w tablicy. To nie jest przypis: przy starym cyklu po pozycji **każde zgaszenie
  przemalowałoby wszystkie obiekty za nim**, i ta zmiana byłaby nie do zrobienia bez
  tamtej.
- Sufit `MAX_DRAWINGS_PER_SYMBOL` sprawdza `count_drawings` przed zapisem.

## Goals / Non-Goals

**Goals:**

- Zgaszenie odwracalne bez utraty czegokolwiek, co rysunek o sobie niesie.
- Jeden stan widoczności, ten sam dla agenta, dla obu slotów i po odświeżeniu.
- Zgaszony obiekt nieobecny na płótnie tak samo jak nieistniejący — bez trafiania,
  bez etykiety przy osi, bez zasłaniania świec.

**Non-Goals:**

- Hurtowe „ukryj wszystkie na tym wykresie". Świadomie: to drugi stan obok
  per-obiektowego i trzeba by rozstrzygać, który wygrywa.
- Gaszenie wskaźników. Wskaźnik zdejmuje się z wykresu wybierakiem i wraca kliknięciem;
  nie ma tam nic do stracenia, co uzasadniałoby trzeci stan.
- Gaszenie czasowe („pokaż znowu za godzinę"), grupy i tagi rysunków.
- Zmiana tego, jak rysunki powstają, i jak są kasowane.

## Decisions

### Widoczność to kolumna na rysunku, nie stan ekranu i nie tabela obok

`hidden boolean not null default false` w `chart_drawings`. Domyślnie zapalone, więc każdy
rysunek stojący dziś w bazie po migracji wygląda tak samo jak przed nią.

Rozważane: stan ekranu w `Chart`, tak jak zaznaczenie. Odrzucone — wtedy agent nie ma
czego ustawiać, więc narzędzie odpada, a operator gaszący obiekt w jednym slocie widzi go
dalej w drugim. Zaznaczenie należy do ekranu, bo wskazuje **kto na co patrzy**; widoczność
mówi, **co jest naniesione**, a to jest stan instrumentu (`agent-chart-drawings`, „Rysunek
należy do instrumentu, nie do widoku").

Rozważane: osobna tabela `hidden_drawings` z identyfikatorami. Odrzucone — join po to, żeby
przenieść jeden bit, plus druga rzecz do sprzątania przy kasowaniu rysunku.

`hidden` siada na `ChartDrawing`, obok `created_at`, a **nie** w geometrii — inaczej niż
`label` i `color`, które w modelu domenowym mieszkają w kształcie. To nie jest
niekonsekwencja: tamte dwa opisują, jak rysunek wygląda, a to opisuje, czy w ogóle jest
rysowany, i przy zmianie kształtu nie miałoby dokąd pójść.

### `hide`/`show` w `draw_on_chart`, nie czwarte narzędzie do wykresu

To narzędzie już bierze dwie listy identyfikatorów i już jest przyrostowe — `hide` i `show`
to te same listy, ta sama transakcja i ta sama reguła „w całości albo wcale".

Rozważane: `set_drawing_visibility` obok. Odrzucone z dwóch powodów. Model wybiera
narzędzie z opisów, więc czwarte narzędzie do wykresu to czwarty opis do przeczytania przed
każdym wyborem — a różnica między „skasuj" a „zgaś" i tak musi być powiedziana w opisie
`draw_on_chart`, bo to tam stoi kasowanie. I: „zgaś stary opór i postaw nowy" jest jednym
posunięciem, a rozbite na dwa narzędzia daje stan pośredni, w którym operator widzi wykres
bez żadnego oporu.

### Sprzeczne polecenie jest odmową, nie rozstrzygnięciem

Identyfikator w `hide` i w `show` naraz odrzuca wywołanie i nazywa ten identyfikator.

Rozważane: „`show` wygrywa" albo „`hide` wygrywa". Odrzucone — którakolwiek reguła jest
regułą, której model nie odczyta ze schematu, więc raz na jakiś czas dostanie wynik
odwrotny do zamierzonego i nie będzie miał z czego się dowiedzieć, dlaczego. Odmowa jest
jedyną odpowiedzią, która uczy.

### Zgaszony obiekt nie dostaje prymitywu

`Chart.tsx` odfiltrowuje zgaszone **przed** efektem synchronizującym, więc istniejąca pętla
sprzątająca odczepia ich prymitywy sama — z punktu widzenia płótna zgaszenie wygląda
dokładnie jak skasowanie, i to jest poprawne.

Rozważane: rysowanie zgaszonych bladziej. Odrzucone — blady obiekt dalej zasłania świece,
dalej trafia w `hitTest` i dalej stawia etykietę przy osi cen, a operator gasi go po to,
żeby go tam nie było. Do tego terminal ma już przygaszanie w innym znaczeniu:
„niewskazany, bo wskazany jest inny" (`terminal-chart-objects`). Dwa różne stany w jednym
wyglądzie to stan, którego nie da się odczytać.

Lista dostaje **całą** tablicę, wykres tylko zapalone. To są dwa różne pytania — „co jest
naniesione" i „co jest narysowane" — i lista, która pokazywałaby tylko zapalone, gasiłaby
obiekty bezpowrotnie.

### Zaznaczenie wskazuje obiekt z zapisu, nie z płótna

Wskazany może być każdy obiekt instrumentu, także zgaszony; wykres podświetla go, jeśli go
rysuje. Zgaszenie wskazanego obiektu zostawia kartę otwartą, z przyciskiem zamienionym na
„zapal".

Rozważane: zdejmowanie wskazania przy zgaszeniu — symetrycznie do usunięcia. Odrzucone:
karta znikająca razem z obiektem odsyła operatora do listy po cofnięcie tego, co przed
sekundą zrobił jednym kliknięciem, a odwracalność jest całym powodem, dla którego gaszenie
istnieje. Usunięcie zdejmuje wskazanie dalej — tam nie ma czego wskazywać.

To jest też jedyna widoczna różnica w zachowaniu między dwoma przyciskami, które stoją obok
siebie i robią pozornie to samo. Zamierzona.

### Operator gasi przez `PATCH /drawings/{id}`, nie przez nową trasę

`PatchDrawingIn` dostaje `hidden: bool | None`, gdzie `None` znaczy „zostaw" — ta sama
konwencja, którą to żądanie już ma dla cen i etykiety, i ten sam walidator „to żądanie nic
nie zmienia" po dołożeniu nowego pola do jego listy.

Rozważane: `POST /drawings/{id}/hide`. Odrzucone — druga trasa robiąca to, co pierwsza
robi jednym polem, i drugie miejsce, w którym trzeba pilnować 404 dla nieistniejącego
identyfikatora.

### Sufit liczy zgaszone

`count_drawings` zostaje bez zmian, czyli liczy wszystko. Sufit jest o zapisie i o odczycie
bez kresu, nie o gęstości ekranu; taki, który da się obejść gaszeniem, nie jest sufitem.

Konsekwencja przyjęta: operator, który dobił do stu i pogasił połowę, nadal nie postawi
setnego pierwszego. Odpowiedź na to jest kasowanie, i to jest właściwa odpowiedź — sufit
mówi, że zapis urósł ponad to, co ktokolwiek przeczyta.

## Risks / Trade-offs

- **Zgaszony rysunek nadal liczy się do sufitu** → operator może dobić do niego, mając na
  ekranie dwa obiekty. Komunikat odmowy mówi o suficie na instrumencie, nie o tym, co
  widać, więc nie jest mylący; gdyby okazało się to uwierać w praktyce, właściwą odpowiedzią
  jest podniesienie sufitu, nie przestanie liczyć części rysunków.
- **Model dostaje czwarte i piąte pole w jednym narzędziu** → opis `draw_on_chart` rośnie,
  a to jest tekst, który model czyta przy każdym wyborze narzędzia. Przyjęte, bo
  alternatywą był czwarty opis obok, czyli ten sam koszt plus jeden wybór więcej.
- **Agent wdrożony przed terminalem** → model gasi rysunek, a stary terminal nie zna pola
  `hidden` i rysuje go dalej. Nic nie znika i nic nie kłamie w zapisie; operator widzi
  obiekt, o którym agent powie, że go zgasił. Rozjazd na jedno wdrożenie, bez utraty
  danych.
- **Terminal wdrożony przed agentem** → terminal czyta pole, którego nie ma na drucie.
  Musi to znieść jako „zapalony", a nie jako brak obiektu — inaczej pusty wykres na czas
  jednego wdrożenia. To jest ta strona, na którą trzeba uważać przy pisaniu mapowania.
- **Dwa przyciski obok siebie, jeden odwracalny i jeden nie** → „Zgaś" i „Usuń" w jednym
  rzędzie na karcie i w wierszu listy. Rozdzielone słowem, nie samą pozycją; usunięcie
  zdejmuje kartę, zgaszenie ją zostawia, więc skutek też je rozdziela.

## Migration Plan

1. Migracja dokłada `hidden boolean not null default false`. Wszystkie stojące rysunki są
   po niej zapalone, czyli wyglądają dokładnie tak, jak wyglądały.
2. Rewizja promptu w tej samej migracji, przepisana w całości, tak jak `0005` do `0008`.
   Akapit o rysunkach mówi, że gaszenie jest odwracalne, a kasowanie nie — bez tego model
   dalej kasuje, żeby coś schować, i to jest właśnie ta strata, której zmiana ma zapobiec.
3. Terminal i agent wdrażają się niezależnie — patrz obie strony w „Risks" powyżej.
4. Wycofanie: `downgrade` zdejmuje kolumnę, czyli traci to, co było zgaszone; rysunki
   wracają wszystkie zapalone. To jest utrata stanu widoczności, nie rysunków, i jest
   odwrotnością tego, przed czym ta zmiana chroni — świadomie, bo alternatywą byłoby
   trzymanie kolumny, której nikt już nie czyta.
