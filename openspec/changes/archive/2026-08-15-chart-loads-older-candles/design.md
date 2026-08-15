## Context

Snapshot subskrypcji niesie ostatnie 500 świec (`SNAPSHOT_CANDLES` w `market-data`) i to jest cała
historia, jaką wykres widzi. Archiwum ma więcej i umie ją oddać zakresem: `GET /candles/{symbol}?from&to`,
w terminalu `MarketDataSource.history`, dziś nieużywane przez wykres. Po co jest ta zmiana — proposal.md.

Dwie rzeczy z otoczenia wiążą ręce. Pierwsza: `data/types.ts` świadomie nie trzyma długości okresu dla
rozdzielczości („`DAY` i `WEEK` nie mają stałej długości okresu" — dzienna świeca zaczyna się od sesji
giełdy, nie od północy UTC). Druga: odczyt zakresu to dokładnie ten mechanizm, który usunięto z wykresu,
gdy powstał hub — bo sklejany z subskrypcją tworzył szew, w którym ginęła zamykająca się świeca.

## Goals / Non-Goals

**Goals:**
- Przewijanie w lewo dociąga starsze świece, bez ruszania kadru.
- Koniec historii, trwający odczyt i nieudany odczyt są na ekranie rozróżnialne.
- Slot wybiera instrument z listy, którą siatka i tak już czyta.

**Non-Goals:**
- Górny limit świec trzymanych w pamięci wykresu ani ich zwalnianie przy przewijaniu w prawo.
- Dociąganie w przód (prawa krawędź należy do snapshotu i strumienia).
- Zmiany w `market-data` — endpoint zakresu istnieje i wystarcza.

## Decisions

**Okno kolejnej strony mierzy się czasem, który zajmują już narysowane świece — nie tabelą długości
okresu.** Wykres bierze rozpiętość najstarszych `N` narysowanych świec i prosi o zakres o tej samej
rozpiętości, kończący się na najstarszej z nich. Alternatywą była tabela „sekundy na rozdzielczość";
odrzucona, bo `types.ts` odmawia jej trzymania z powodu, który tu obowiązuje tak samo, a dodatkowo taka
tabela byłaby ślepa na weekendy: 500 świec minutowych to 8 godzin zegara, a nie 8 godzin świec.
Rozpiętość liczona z danych ma luki wliczone w cenę.

**Puste okno nie kończy historii — kończy ją dopiero kilka pustych okien pod rząd.** Weekend, święto i
przerwa w zbieraniu wyglądają identycznie: zakres bez świec. Wykres cofa się dalej, podwajając okno, do
kilku prób, i dopiero wtedy mówi „to początek dostępnej historii". Rozważane było pytanie archiwum
wprost — `GET /coverage/{symbol}` niesie `earliest_reachable` — ale to metoda `ArchiveAdmin`, nie
`MarketDataSource`; wykres dostaje to drugie i celowo nie wie o administrowaniu archiwum. Cena: przy
faktycznym końcu historii robi się kilka odczytów, które nic nie zwracają, raz na parę.

**Doklejanie przerysowuje serię i przywraca kadr przesunięty o liczbę doklejonych świec.**
`series.update()` nie przyjmuje świecy starszej niż ostatnia, więc zostaje `setData` całości — a `setData`
zachowuje zakres logiczny, którego indeksy właśnie się przesunęły o `k` doklejonych świec. Bez korekty
kadr skacze o tyle świec, ile udało się dociągnąć.

**`fitContent()` tylko przy pierwszym rysunku danej pary.** Dziś każdy snapshot dopasowuje kadr; po
rekonekcie skasowałoby to wszystko, co operator sobie przewinął. Rekonekt zostaje przy tym, co widać.

**Lista instrumentów w slocie pochodzi z odczytu, który siatka już robi.** `GridView` czyta `/pairs`
raz dla wszystkich slotów (`useTrackedPairs`), a `SymbolField` dostaje z niego symbole, stan odczytu i
ponowienie — zamiast sam pytać archiwum przez `archivedInstrumentSource`. To źródło znika; `Autocomplete`
zostaje, bo używa go kreator instrumentów.

## Risks / Trade-offs

- **Odczyt zakresu wraca do wykresu, a to on kiedyś tworzył szew.** → Odczyt dotyczy wyłącznie okresów
  starszych niż najstarsza narysowana świeca; prawej krawędzi ani świecy w budowie nie dotyka, więc nie ma
  czego sklejać. Test pilnuje, że zamówiony zakres kończy się na tym, co narysowane.
- **Podwajane okno może na końcu historii zamówić bardzo szeroki zakres.** → Liczba prób jest ograniczona,
  a po niej para jest oznaczona jako wyczerpana i nie pyta ponownie, dopóki nie zmieni się symbol,
  rozdzielczość albo źródło.
- **Seria rośnie bez ograniczenia, gdy ktoś przewija długo.** → Świadomie poza zakresem; przy stronach
  rzędu setek świec i bibliotece, która rysuje dziesiątki tysięcy, to nie jest dziś problem operatora.
- **Select zamiast autocomplete przestanie się skalować, gdy par będzie dużo.** → Pułap `MAX_TRACKED_PAIRS`
  jest tym, co tę decyzję trzyma; gdyby wzrósł o rząd wielkości, wybór wraca do rozmowy.
