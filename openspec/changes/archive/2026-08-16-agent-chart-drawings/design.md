## Context

Motywacja: `proposal.md`, „Why". Wymagania: delta w `specs/`.

Co już stoi i co z tego wynika:

- `agent/tools/chart.py` jest jedynym narzędziem własnym modułu. Sprawdza żądanie przed
  zapisem, przez `market-mcp` (`list_tracked_pairs`, `list_indicators`), odmawia zdaniem,
  które wraca do modelu, i pisze do własnej bazy. Ten wzorzec powtarzamy, nie wymyślamy
  na nowo.
- `agent/routers/chart.py` jest globalny, nie po właścicielu: jest jeden wykres i jeden
  operator, a `current_principal` służy tylko do odrzucenia nieuwierzytelnionego żądania.
  Rysunki mają dokładnie ten sam status.
- Terminal ma `RayPrimitive` (poziom jako odcinek od momentu) i `ZonePrimitive` (strefa
  jako prostokąt), oba karmione dziś wyłącznie wynikami wskaźników. Linii trendu nie ma.
- `Chart.tsx` czyści wskaźniki przy zmianie symbolu, rozdzielczości albo źródła
  (`terminal-chart`, „Wskaźniki znikają razem z serią, której dotyczą"). Rysunki mają
  przetrwać zmianę rozdzielczości — to nie jest ten sam cykl życia.
- Panel pokazuje wywołania narzędzi wraz z ich wynikiem (`ToolCallOut`, `ToolCallEntry`),
  więc „agent coś zrobił" jest już częściowo widoczne.

Rzecz do rozróżnienia, bo nazywa się prawie tak samo: `levels_near_price` w `market-mcp`
zwraca **poziomy policzone z archiwum** — nie ma nic wspólnego z rysunkiem, który operator
i agent uzgodnili i zostawili. Prompt musi to powiedzieć wprost, inaczej model będzie
odczytywał jedno, gdy pytano o drugie.

## Goals / Non-Goals

**Goals:**

- Rysunek jako stan instrumentu: czytany w całości, zastępowany w całości, bez kursora.
- Trzy kształty w jednym zapisie, z niezmiennikami pilnowanymi przez bazę, nie tylko przez
  Pythona.
- Zapis agenta odwracalny bez agenta.

**Non-Goals:**

- Rysowanie myszą: stawianie i przeciąganie obiektów na płótnie. Osobna zmiana, znacznie
  większa (tryb narzędzia, trafianie w obiekt, uchwyty).
- Rysunek dzielony między operatorów, prawa dostępu, historia zmian rysunku.
- Alerty na przecięciu poziomu. To jest kolejna rzecz, nie ta.
- Rysunki liczone automatycznie z danych. Katalog wskaźników już to robi i ma do tego
  własną drogę.

## Decisions

### Rysunek jest stanem, nie logiem — inaczej niż polecenie wykresu

`chart_commands` jest logiem z kursorem, bo polecenie opisuje chwilę i terminal musi
wiedzieć, czego jeszcze nie zastosował. Rysunek jest stanem instrumentu: terminal czyta
**wszystkie** rysunki symbolu i zastępuje nimi to, co rysuje. Kursor, składanie i „nowsze
niż" nie mają tu sensu i ich nie będzie.

Konsekwencja przyjęta: żeby zobaczyć rysunek postawiony przez agenta, terminal musi
przeczytać ponownie. Robi to po każdej zakończonej turze i przy zmianie symbolu. Jeden
odczyt na turę jest tani, a strumień dla stanu, który zmienia się kilka razy dziennie,
byłby maszynerią bez odbiorcy.

### Zapis: cztery kolumny geometrii i CHECK per kształt; druty: unia po `kind`

W bazie wszystkie trzy kształty leżą w jednym zestawie kolumn — `time_a`, `price_a`,
`time_b`, `price_b` — a `kind` mówi, co znaczą:

| `kind` | `time_a` | `price_a` | `time_b` | `price_b` |
|---|---|---|---|---|
| `level` | opcjonalny początek | cena | — | — |
| `zone` | opcjonalny początek | dolna cena | opcjonalny koniec | górna cena, `> price_a` |
| `trendline` | wymagany | cena punktu A | wymagany, `> time_a` | cena punktu B |

Każdy z tych warunków MUST być `CHECK`-iem w migracji, nie tylko sprawdzeniem w Pythonie:
niezmiennik, który zna wyłącznie jedna warstwa, jest niezmiennikiem do czasu pierwszego
zapisu z drugiej strony.

Na drucie i w schemacie narzędzia — **odwrotnie**: trzy modele dyskryminowane przez `kind`,
z polami nazwanymi po ludzku (`price`; `top`/`bottom`; `from`/`to` z czasem i ceną). Model
językowy, który dostaje `price_a` i `price_b`, myli je; model, który dostaje `top`
i `bottom`, nie ma jak. Jedna funkcja tam i jedna z powrotem, obie w `store.py`.

Rozważane: jedna kolumna `JSONB geometry`. Odrzucone — cała walidacja kształtu wróciłaby
do Pythona, a `top > bottom` jest dokładnie tym, co baza umie sprawdzić raz na zawsze.

### Ceny jako `double precision`, czas jako `timestamptz`

Cena rysunku jest liczbą na wykresie, a wykres w terminalu operuje na `number`. Nie ma tu
pieniędzy do zsumowania, więc nie ma powodu na `numeric` i ciąg znaków na drucie —
inaczej niż stawki modeli w `ModelOut`, gdzie ten powód jest.

Czas ISO 8601 z offsetem, tak jak wszędzie w tym module; terminal zamienia go na
epoch-sekundy w swoim mapperze i poza mapperem nie widzi pola drutu.

### Dwa narzędzia: jedno pisze, drugie czyta

- `draw_on_chart(symbol, add[], remove[])` — dokłada i kasuje w jednym wywołaniu, w jednej
  transakcji.
- `list_chart_drawings(symbol)` — odczyt z identyfikatorami.

Rozważane: trzy narzędzia (dołóż / skasuj / wypisz). Odrzucone — „przesuń opór o dziesięć
punktów" to skasowanie i dołożenie, i powinno być jedną transakcją, a nie dwoma
wywołaniami, między którymi wykres pokazuje instrument bez oporu.

Rozważane: jedno narzędzie z trybem odczytu. Odrzucone — odczyt jest bezpieczny do
powtórzenia, zapis nie, a narzędzie, którego opis miesza jedno z drugim, jest wołane do
odczytu przez zapis.

**Przyrostowo, nie deklaratywnie** — i to jest jedyne miejsce, w którym ta zmiana świadomie
odwraca zasadę z `agent-chart-control`. Tam pominięcie kosztuje jeden wskaźnik i wraca
jednym kliknięciem. Tutaj kosztowałoby wsparcia zbierane tygodniami. Uzasadnienie stoi
w specyfikacji, żeby następny czytelnik nie „naprawił" tej niespójności.

### Sprawdzenie i odmowa tam, gdzie już jest

Symbol sprawdzany przez `list_tracked_pairs` w `market-mcp` — ta sama droga, ten sam
komunikat co w `set_chart`, ta sama odmowa, gdy serwera narzędzi nie ma. Kolory brane
z `CHART_COLORS` przez import z `tools/chart.py`, nie przepisane: jedna lista, jedno
miejsce, w którym widać jej rozjazd z paletą terminala.

Sufit **100 rysunków na instrument**. Odczyt jest bez stronicowania i taki zostanie; sto
obiektów to wykres, na którym już nic nie widać, więc granica jest tam, gdzie i tak leży
granica użyteczności.

### Publikacja: odczyt, poprawka, usunięcie — bez POST

`GET /drawings?symbol=`, `PATCH /drawings/{id}`, `DELETE /drawings/{id}`. Globalne, nie po
właścicielu, z tego samego powodu co `/chart`.

**Nie ma POST-a**, bo nikt go nie potrzebuje: agent pisze przez `store`, tak jak
`ChartTool`, a operator w tej zmianie rysunków nie stawia — stawia je rysowanie myszą,
którego tu nie ma. Endpoint dokładany „na przyszłość" jest powierzchnią, którą trzeba
utrzymywać i testować, zanim ktokolwiek jej użyje.

Terminal zaczyna przez to **pisać** do modułu `agent`. To nie narusza „terminal niczego nie
publikuje": publikowanie to bycie tym, od czego zależą inni, a nie wysyłanie żądań do
modułu, który się konsumuje.

### Rysunki i wskaźniki dzielą prymitywy, ale nie cykl życia

`RayPrimitive` i `ZonePrimitive` rysują jedno i drugie, ale rysunki dostają **własne**
instancje i własną mapę, bo czyszczenie wskaźników przy zmianie rozdzielczości nie może
zdejmować rysunków (`terminal-chart`, „Wskaźniki znikają razem z serią, której dotyczą"
kontra nowe „Wykres rysuje obiekty naniesione na instrument"). Wspólna mapa to jedna linia
kodu i jeden błąd, który wygląda jak znikające wsparcia.

`TrendlinePrimitive.ts` powstaje na wzór `RayPrimitive` — ten sam `timeToX`, ten sam
kształt klasy — z odcinkiem między dwoma punktami zamiast promienia do prawej krawędzi.

### Panel mówi o rysunkach porównaniem, nie drugim kanałem

Po turze terminal odczytuje rysunki symbolu i porównuje z tym, co miał: różnica daje zdanie
tego samego rodzaju co `describeChartControl` dla polecenia wykresu. Nowego kanału
zdarzeń nie ma — wywołanie narzędzia i tak jest widoczne w panelu (`ToolCallEntry`),
a odczyt po turze jest potrzebny niezależnie, żeby wykres się zgadzał.

### Prompt dostaje rewizję i jedno zdanie o rozróżnieniu

Nowa rewizja seeduje akapit o obu narzędziach oraz zdanie odróżniające rysunek operatora od
`levels_near_price`. Tekst poprzedniej rewizji przepisany w całości, nie łatany w locie —
tak jak w `0005`.

## Risks / Trade-offs

- **Rysunki nie mają właściciela** → jeden operator, dokładnie tak jak prompt i wykres.
  Gdy pojawi się drugi, będzie to ta sama zmiana dla wszystkich trzech, a nie trzy zmiany.
- **Model może zasypać wykres obiektami** → sufit na instrument i odmowa, która go nazywa;
  operator kasuje z listy pojedynczo.
- **Kasowanie po identyfikatorze wyścigujące się z ręką operatora** → odmowa mówiąca, że
  takiego rysunku nie ma, zamiast cichego sukcesu; model dowiaduje się, że stan się zmienił.
- **Odczyt po turze zamiast strumienia opóźnia rysunek do końca tury** → tak, i to jest
  akceptowane: rysunek jest ustaleniem, nie tickiem, a tura kończy się sekundy po tym, jak
  narzędzie zapisało.
- **Dwie zmiany dotykają `Chart.tsx`, `agent/contract.py` i `agent/tools/`** →
  `agent-chart-navigation` i ta zmiana robione po kolei, nie równolegle; numer migracji tej
  zmiany zależy od tego, która wyląduje pierwsza.
- **`double precision` na cenie** → strata precyzji poniżej tego, co wykres umie narysować
  i co instrument kwotuje; gdyby kiedyś rysunek miał wchodzić do rachunku pieniędzy, to jest
  moment na `numeric`, ale wtedy zmienia się też to, po co on jest.

## Migration Plan

1. Migracja dokładająca `chart_drawings` wraz z `CHECK`-ami per kształt i indeksem po
   `symbol` — to jedyny odczyt, jaki ta tabela obsługuje. Numer zależy od kolejności
   z `agent-chart-navigation`.
2. Ta sama albo kolejna migracja seeduje rewizję promptu z akapitem o rysunkach.
3. `agent` przed terminalem albo po nim, bez znaczenia: starszy terminal nie woła
   `/drawings` i nic nie rysuje, nowszy terminal przed wdrożonym modułem dostaje 404
   i mówi, że obiektów nie udało się odczytać — czyli dokładnie to, co przewiduje
   wymaganie o nieudanym odczycie.
4. Wycofanie: `alembic downgrade` zdejmuje tabelę wraz z rysunkami. To jest utrata danych,
   nie ich schowanie — jeśli rysunki mają przeżyć wycofanie, trzeba je wyeksportować
   wcześniej, i to jest świadomie ręczna czynność operatora, a nie coś, co robi migracja.
