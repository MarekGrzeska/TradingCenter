## Context

Iteracja 5 planu refactoru weszła z gotowym testem na „martwe pole": pole jest martwe,
gdy żaden konsument go nie czyta. Test jest tani — grep po `archive.ts`, `types.ts`
i modelach `market-mcp` — i dał sześć trafień. Pięć z nich było fałszywe, a wykryła to
dopiero druga kwerenda, po `openspec/specs/`.

To jest decyzja o tym, którym testem się posługujemy, bo pierwszy z nich właśnie o mało
nie skasował czterech opublikowanych wymagań.

## Goals / Non-Goals

**Cel.** Zdjąć z kontraktu to, czego nikt nie żąda i nikt nie czyta, i zostawić na nim
wszystko, czego żąda wymaganie — niezależnie od tego, czy dzisiejszy konsument to czyta.

**Nie-cel.** Rozstrzyganie, czy któreś z tych czterech wymagań jest za szerokie. Może
być; to jest pytanie o wymaganie i idzie deltą specyfikacji, nie sprzątaniem `contract.py`.

## Decisions

### D1. Martwe jest to, czego nie żąda wymaganie **i** czego nie czyta konsument

Alternatywa, którą plan przyjmował milcząco: martwe jest to, czego nie czyta konsument.
Odrzucona, bo dała pięć fałszywych trafień na sześć — zmierzone polami:

| pole | konsument czyta? | wymaganie żąda? | werdykt |
|---|---|---|---|
| `CandlesOut.price_side` | nie | **tak** — `market-data-store` | zostaje |
| `FormingCandleOut.price_side` | nie | **tak** — to samo | zostaje |
| `IndicatorsOut.price_side` | nie | w duchu tego samego wymagania | zostaje |
| `IndicatorsOut.warmup_from` | nie | **tak** — `market-data-indicators` | zostaje |
| `StreamTicketOut.expires_in_seconds` | nie | **tak** — `market-data-browser-access` | zostaje |
| `TrackedPairOut.last_fill` | nie | nie | **usuwane** |

Kierunek zależności jest tu całą sprawą. Kontrakt jest publikowany dla konsumentów, których
jeszcze nie ma, a nie tylko dla tego jednego, który jest — `market-data-store` mówi to
wprost, uzasadniając `price_side` tym, że *kiedyś* może dojść druga strona ceny. Test
oparty na konsumpcji odwraca tę zależność: pozwala dzisiejszemu terminalowi decydować, co
archiwum ma publikować, i kasuje wymaganie przez przeoczenie w konsumencie.

Praktyczna konsekwencja: **kwerenda po `openspec/specs/` idzie przed grepem po konsumentach,
nie po nim.** Odwrotna kolejność podpowiada odpowiedź, zanim padnie właściwe pytanie.

### D2. Stan, którego producent nie umie osiągnąć, schodzi z drutu — zamiast zostać zaimplementowany

`warmup_kind` deklaruje `"anchored"`, katalog produkuje `fixed` i `decay`. Dwie drogi:

**(a) dopisać rozgrzewkę kotwiczoną** — wskaźnik liczony od ustalonego momentu, nie od
okna. Jest to sensowna rzecz i pewnie kiedyś powstanie (VWAP od otwarcia sesji jest jej
naturalnym kandydatem). Odrzucona teraz, bo żadne wymaganie tego nie żąda i żaden wpis
katalogu tego nie potrzebuje: byłaby to funkcja napisana po to, żeby uzasadnić pole.

**(b) zdjąć wariant.** Wybrane. Kontrakt ma opisywać to, co moduł robi, a nie to, co ktoś
przewidywał. Gdy rozgrzewka kotwiczona powstanie, wróci razem z nią — jako wymaganie,
katalog i wariant naraz, co jest zresztą tańsze niż utrzymywanie ich w rozjeździe.

Różnica wobec D1 jest istotna i warto ją nazwać: `price_side` też opisuje przyszłość,
a zostaje. Nie dlatego, że jest przyszłością, tylko dlatego, że **jest wymaganiem** —
ktoś tę decyzję podjął i zapisał. `"anchored"` nie jest niczyją decyzją, jest wariantem,
który wszedł do `Literal` i nigdy się nie zmaterializował.

### D3. Obrona: drut nie deklaruje rodzaju rozgrzewki, którego katalog nie umie wyprodukować

Bez tego ta sama rozbieżność wraca sama — wystarczy, że katalog straci ostatni wpis
jakiegoś rodzaju, a `Literal` zostanie. Test porównuje zbiór wariantów `warmup_kind`
ze zbiorem `warmup.kind` faktycznie występującym w katalogu i czerwienieje przy różnicy
w którąkolwiek stronę.

Kierunek „katalog produkuje coś, czego drut nie deklaruje" jest tym drugim, i on też ma
znaczenie: to jest awaria walidacji odpowiedzi, czyli dokładnie ten tryb, który
`outputSchema` w modułach MCP wykrył naprawdę (iteracja 4).

Zasada nr 5 planu żąda, żeby obrona miała test *swojego* trybu awarii. Tym trybem jest
tutaj rozejście się dwóch list, a nie „czy wskaźniki się liczą" — więc test dotyka obu
list i niczego więcej.

## Risks / Trade-offs

**Kontrakt zmienia się bez zmiany wymagania, więc nic w `openspec/specs/` nie zaczerwieni
się, jeśli usunięto za dużo.** Obroną są dwie kopie schematu, które muszą zostać
zregenerowane, i testy dwóch konsumentów — `checks.yml` uruchamia przy tym diffie job
terminala i job market-mcp. To jest słabsza obrona niż delta specyfikacji i warto to
wiedzieć, zamiast zakładać, że skoro CI jest zielone, to zakres był dobry.

**Usunięcie `last_fill` zabiera stan, którego operator mógłby kiedyś chcieć.** Ten stan
i tak nie przeżywał restartu — opis pola mówił to wprost — a od `market-data-jobs` jest
trwała ewidencja dociągnięć, którą terminal faktycznie pokazuje
(`terminal-collection-history`). Usuwane jest gorsze, nietrwałe źródło tej samej wiedzy.

## Open Questions

Czy `IndicatorsOut.price_side` naprawdę mieści się w wymaganiu `market-data-store`, którego
scenariusz mówi o *odczycie świec*, a nie o serii policzonej z tych świec. Przyjęto, że tak,
bo uzasadnienie wymagania — nie mieszać dwóch stron ceny w jednej serii — stosuje się do
serii policzonej tak samo. Rozstrzygnięcie inaczej znaczyłoby usunięcie pola, więc próg jest
tu celowo po stronie zachowawczej.
