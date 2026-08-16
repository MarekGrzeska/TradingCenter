## Context

Motywacja: `proposal.md`, „Why". Wymagania: delty w `specs/`.

Co już stoi i co z tego wynika:

- Rysunki rysują `RayPrimitive`, `ZonePrimitive` i `TrendlinePrimitive` — własne instancje
  w mapie po identyfikatorze rysunku, odrębnej od wskaźnikowej (`agent-chart-drawings`
  design.md, „Rysunki i wskaźniki dzielą prymitywy, ale nie cykl życia"). Mapa po
  identyfikatorze jest już tym, czego potrzebuje trafianie.
- Kolor rysunku bierze dziś `indicatorColorFromToken(colors, drawing.color) ??
  indicatorLineColor(colors, index)` — token wskaźnikowy albo cykl po **pozycji w tablicy**.
- `DrawingList.tsx` ma już edytor: pola cen po roli kształtu, podpis, i dwie operacje
  (`remove`, `patch`) zwracające `null` albo zdanie o niepowodzeniu.
- lightweight-charts 5.0.9 niesie `hitTest(x, y): PrimitiveHoveredItem | null` na
  prymitywie, `hoveredObjectId` w `MouseEventParams` z `subscribeClick`, `priceAxisViews()`
  oraz `zOrder()`. Sprawdzone w typings tej wersji, nie w dokumentacji innej.
- `CHART_COLORS` w `agent/tools/chart.py` jest listą, wobec której `draw_on_chart`
  odmawia koloru — i jest świadomym duplikatem `INDICATOR_LINE_TOKENS` terminala.

## Goals / Non-Goals

**Goals:**

- Trafianie w obiekt liczone tam, gdzie liczona jest jego geometria — jeden opis kształtu,
  nie dwa.
- Kolor obiektu trwały przez cały jego żywot, bez stanu, który trzeba by pilnować.
- Opis i poprawianie jedną logiką z listą, nie drugą.

**Non-Goals:**

- Rysowanie i przeciąganie myszą — poza zakresem, tak jak w `agent-chart-drawings`.
  Zaznaczenie jest do obejrzenia i poprawienia, nie do manipulacji na płótnie.
- Zaznaczanie wielu obiektów naraz, zaznaczanie wskaźników, menu kontekstowe.
- Zmiana tego, jak rysunki powstają i skąd się biorą.

## Decisions

### Trafianie natywnym `hitTest`, nie własną warstwą nad canvasem

Prymitywy dostają `hitTest(x, y)` zwracające `externalId` — identyfikator rysunku jako
tekst — a `subscribeClick` oddaje go z powrotem w `hoveredObjectId`. Biblioteka woła
`hitTest` sama, na tych samych współrzędnych, w których rysuje.

Rozważane: przezroczysta warstwa DOM z polami trafień pozycjonowanymi absolutnie.
Odrzucone — musiałaby być przeliczana przy każdym przewinięciu i zoomie, i rozjeżdżałaby
się z canvasem dokładnie wtedy, gdy nikt nie patrzy.

Rozważane: własna matematyka w obsłudze kliknięcia, z `timeToX`/`priceToCoordinate`.
Odrzucone — to jest drugi opis tej samej geometrii, obok tego, którym prymityw rysuje.
Dwa opisy jednego kształtu rozjeżdżają się przy pierwszej zmianie jednego z nich, a różnica
objawia się jako „czasem nie da się kliknąć".

Tolerancja trafienia mieszka w `hitTest` każdego prymitywu, bo każdy kształt ma swoją:
poziom i linia trendu to pasmo wokół odcinka, strefa to jej własny prostokąt.

### Kolor: linia z palety rysunków, etykieta przy osi kolorowana rolą

Dwie rzeczy, które kolor mógłby powiedzieć — „który to obiekt" i „czym on jest" — nie
mieszczą się w jednym kanale. Więc dostają dwa: **linia** niesie tożsamość (paleta
rysunków), **etykieta przy osi cen** niesie rolę (wsparcie pod bieżącą ceną, opór nad nią).

Rozważane: kolorowanie rolą w całości — zielone wsparcia, czerwone opory. Odrzucone: dwa
wsparcia wyglądają wtedy identycznie, czyli mniej rozróżnialnie niż dziś, a operator prosił
o odwrotność.

Rozważane: sama paleta, bez sygnału roli. Odrzucone: rola i tak jest liczona z położenia
względem ceny, a jej pokazanie kosztuje jeden kolor etykiety, którą i tak rysujemy.

Rola przelicza się z ostatniej świecy, więc **zmienia się sama**, gdy cena przebija poziom.
To jest zamierzone: poziom przebity przestaje być oporem i staje się wsparciem, i wykres,
który dalej mówi „opór", myli.

Rola używa tych samych tokenów, co świece rosnąca i spadająca. To nie jest oszczędzanie na
tokenach — „pod ceną" i „nad ceną" to dokładnie to znaczenie, które te dwa kolory już
niosą w tym terminalu.

### Kolor przypisywany po identyfikatorze, nie po pozycji

Dziś kolor idzie z indeksu w tablicy rysunków, więc skasowanie jednego przemalowuje
wszystkie po nim. Nowe przypisanie liczy się z identyfikatora rysunku — funkcja, nie stan,
więc nie ma czego trzymać ani z czym synchronizować, a ten sam rysunek ma ten sam kolor
w każdym slocie i po każdym odświeżeniu.

Konsekwencja przyjęta: dwa rysunki mogą wylosować ten sam kolor. Przy suficie stu obiektów
na instrument jest to nieuniknione dla każdej skończonej palety, a alternatywa —
przydzielanie „następnego wolnego" — jest stanem, który znów zależy od tego, co stoi obok.

### Paleta rysunków dokłada tokeny, nie odbiera starych

Narzędzie zaczyna przyjmować tokeny rysunków **zamiast** wskaźnikowych: rysunek nie jest
wskaźnikiem i nie ma powodu nosić jego koloru. Ale w bazie stoją już rysunki z tokenami
wskaźnikowymi, postawione zanim ta zmiana istniała.

Więc rozdzielone: **narzędzie** przyjmuje odtąd wyłącznie tokeny rysunków, a **terminal**
rozwiązuje jedne i drugie. Rysunek sprzed zmiany rysuje się tak, jak się rysował; nowego
w starym kolorze nie da się już postawić. Odwrotna kolejność — terminal przestający znać
stare tokeny — zamieniłaby istniejące rysunki w bezbarwne, a to jest utrata czegoś, czego
operator nie kasował.

### Karta obiektu jest DOM-em nad canvasem, a nie rysunkiem na nim

Karta ma przyciski i pola do wpisania ceny. Rysowanie formularza na canvasie oznaczałoby
własne trafianie w przyciski, własne zaznaczanie tekstu i własną obsługę klawiatury —
wszystko to, co przeglądarka już ma.

Karta bierze zawartość i obie operacje z tego samego miejsca, co lista (`ChartDrawings`:
`items`, `remove`, `patch`), więc „popraw" znaczy dokładnie to samo w obu. Edytor pól jest
tym samym komponentem — jedna logika poprawiania, nie druga, która rozjedzie się przy
pierwszej zmianie reguł.

### Zaznaczenie mieszka w `Chart`, nie w `drawingsStore`

`drawingsStore` trzyma to, co jest naniesione — stan instrumentu, wspólny dla slotów.
Zaznaczenie jest stanem *ekranu* i należy do jednego slotu: dwa sloty pokazujące US100
pokazują te same obiekty, ale operator wskazuje obiekt w jednym z nich.

Rozważane: wrzucenie zaznaczenia do `drawingsStore`. Odrzucone — wskazanie obiektu
w jednym slocie podświetlałoby go w drugim, a przy zmianie symbolu trzeba by je sprzątać
w miejscu, które o slotach nic nie wie.

Lista jest renderowana przez `Chart` (nagłówek), więc stan w `Chart` wystarcza obu i nie
wymaga żadnego kanału między nimi.

### Rysunek cięższy od wskaźnika, i to waga niesie różnicę

2 px ciągłe wobec 1 px kreskowanego. Rozważane: różnicowanie samym kolorem (odrębna
paleta). Odrzucone jako *jedyny* nośnik — kolor już niesie tożsamość obiektu, a operator
patrzący na ośmiokolorowy wykres nie ma jak pamiętać, które osiem barw należy do której
grupy. Kształt linii widać bez pamiętania czegokolwiek.

## Risks / Trade-offs

- **`hitTest` wołany przy każdym ruchu myszy, dla każdego prymitywu** → geometria jest
  kilkoma odejmowaniami, a sufit stu obiektów na instrument jest z tej samej strony
  granicą. Gdyby to kiedyś zaczęło ciążyć, filtr po widocznym zakresie jest tam, gdzie
  `ZonePrimitive` już go ma.
- **Karta potrafi zasłonić obiekt, który opisuje** → stawiana po tej stronie kliknięcia,
  gdzie jest więcej miejsca, i zamykana `Escape` oraz kliknięciem w puste miejsce.
- **Rola liczona z ostatniej świecy** → obiekt na instrumencie, którego wykres jeszcze nie
  narysował ani jednej świecy, nie ma względem czego mieć roli. Etykieta bierze wtedy kolor
  linii, zamiast zgadywać stronę.
- **Kolory roli są kolorami świec** → na wykresie z gęstymi świecami etykieta przy osi jest
  w tej samej rodzinie barw co seria. Osobne miejsce (oś, nie płótno) jest tym, co je
  rozdziela; gdyby to nie wystarczyło, etykieta może dostać obramowanie.
- **Agent wdrożony przed terminalem** → model dostaje nowe tokeny w schemacie i stawia
  rysunek w kolorze, którego stary terminal nie zna. `indicatorColorFromToken` odpowiada
  wtedy `null`, a wykres nadaje własny kolor — czyli dokładnie ta ścieżka, którą rysunek
  bez koloru chodzi od początku. Nic nie znika.
- **Kolejność archiwizacji** → ta zmiana modyfikuje wymagania, które leżą jeszcze w delcie
  `agent-chart-drawings`, nie w `openspec/specs/`. Zarchiwizowanie jej pierwszej zostawi
  `MODIFIED` bez czego modyfikować. Zapisane też w `proposal.md`, „Impact".

## Migration Plan

1. Terminal i agent wdrażają się niezależnie i w dowolnej kolejności — patrz „Agent
   wdrożony przed terminalem" powyżej dla ścieżki, która wymaga uwagi. Odwrotna (terminal
   przed agentem) nie wymaga żadnej: nowe tokeny po prostu jeszcze nie przychodzą.
2. Nie ma migracji bazy. Rysunki stojące dziś w `chart_drawings` zachowują swoje tokeny
   i rysują się dalej, bo terminal rozwiązuje jedne i drugie.
3. Wycofanie: zdjęcie zmiany z terminala przywraca poprzedni wygląd i zabiera zaznaczanie;
   rysunki postawione w międzyczasie w tokenach rysunków przestaną mieć rozpoznawalny
   kolor i dostaną kolor od wykresu. To jest utrata koloru, nie rysunku.
