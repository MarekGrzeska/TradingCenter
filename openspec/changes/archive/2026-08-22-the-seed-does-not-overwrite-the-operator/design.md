## Context

Bug zreprodukowany, nie wywnioskowany: dwa wiersze pod jedną wersją wchodzą do
`prompt_revisions` bez sprzeciwu, a odczyt zwraca ten wstawiony później — czyli zasiew,
nie zapis operatora. Do tego wersja, którą operator dostaje, jest zawsze dokładnie tą,
której użyje następna migracja zasiewająca, bo obie strony robią `+1` od najnowszej.

Poniżej dwie decyzje. Druga dotyczy danych, których w razie pomyłki nie da się odzyskać.

## Decisions

### D1. Zasiew ustępuje operatorowi, zamiast ograniczenie mieć go pilnować

Trzy drogi były na stole.

**(a) Sam unikat na `version`.** Kolizja przestaje być cicha — i staje się głośna
w najgorszym możliwym miejscu. Migracje tego repozytorium biegą w `lifespan`
(`CLAUDE.md`, „Migrations are never the operator's job"), więc ograniczenie, które pada,
to nie czerwony deploy, tylko **moduł, który nie wstaje**. Zamiana cichej utraty danych na
zablokowaną produkcję nie jest poprawą, tylko przeniesieniem kosztu na gorszy moment.

**(b) Domyślny prompt wraca do kodu**, a tabela trzyma wyłącznie edycje operatora. Poję­ciowo
najczystsze i kasuje 803 linie prozy z historii migracji. Odrzucone tu, nie odrzucone
w ogóle: zmienia opublikowany scenariusz („odczyt zwraca treść zasianą przy migracji
i wersję v4"), wywraca 20 z 23 testów `test_prompt_store.py` i zostawia świeżą bazę
niezdolną obsłużyć tury, dopóki `latest_prompt_revision` nie nauczy się pustej tabeli.
To jest decyzja o tym, **czym prompt jest**, a nie naprawa tego, że ginie — i zasługuje na
własną zmianę, a nie na wjechanie przy okazji.

**(c) Zasiew wstawia się tylko wtedy, gdy najnowszy wiersz sam jest zasiewem.** Wybrane.
Jedno `WHERE` w `INSERT ... SELECT`, żadnego nowego trybu awarii przy starcie, i zachowuje
oba dzisiejsze zachowania, na których ktoś polega: świeża baza czyta zasiew, a operator,
który nic nie zapisał, dostaje ulepszony prompt z wdrożenia.

Unikat na `version` i tak wchodzi, ale **po deduplikacji w tej samej migracji** — jako
stwierdzenie niezmiennika, nie jako mechanizm, który go wymusza. Wymusza go (c): przy tej
regule kolizja przestaje być osiągalna, bo operator dostaje `+1` tylko wtedy, gdy jest
najnowszy, a wtedy następny zasiew się nie wstawi.

### D2. Backfill jest wyprowadzony z tego, co migracje naprawdę zasiały — nie zgadnięty

Kolumna `source` musi dostać wartość dla wierszy starszych od siebie, a te nie niosą po
sobie śladu. Dwie łatwe odpowiedzi są obie złe:

- **wszystko jako `seed`** — jeśli najnowszy wiersz jest w rzeczywistości zapisem
  operatora, następna migracja zasiewająca go przykryje. Czyli ten sam bug, raz jeszcze,
  dokładnie na tym wierszu, na którym boli.
- **wszystko jako `operator`** — nic już nigdy się nie zasieje, po cichu.

Wersje zasiane przez migracje są jednak **znane i policzalne**: `v4`–`v11`, po jednej na
migrację `0003`, `0005`–`0010`, `0012`. Stąd reguła, którą da się sprawdzić:

> wiersz jest zasiewem wtedy i tylko wtedy, gdy jego `version` należy do tego zbioru **i**
> ma najwyższe `id` spośród wierszy o tej wersji.

Drugi warunek jest tym, który obsługuje kolizję, jeśli już zaszła: przy dwóch wierszach
„v11" ten wstawiony później jest z migracji, a wcześniejszy jest operatora — bo dokładnie
tak ta kolizja powstaje. Wszystko poza zbiorem to zapis operatora, bo migracje nigdy takiej
wersji nie wstawiły.

Nazwy `v4`–`v11` są w tej migracji wpisane **literałem**, nie wyprowadzone z `_SEED_VERSION`
tamtych plików. Backfill opisuje stan bazy w chwili, w której biegnie, i musi znaczyć to
samo za rok, gdy tamte stałe będą już czymś innym albo nie będzie ich wcale.

### D3. Deduplikacja zachowuje wiersz operatora, a przenumerowuje go

Gdy kolizja już zaszła, unikat nie może wejść bez rozstrzygnięcia. Rozstrzygnięcie brzmi:
**żaden wiersz nie ginie.** Zasiew zostaje przy swojej wersji, a wcześniejszy wiersz
operatora dostaje wersję wolną — nie dlatego, że jest mniej ważny, tylko dlatego, że
`downgrade()` migracji zasiewającej celuje w tę wersję i skasowałby oba.

To odwraca dzisiejszą szkodę: przed tą zmianą kolizja znaczyła, że tekst operatora jest
niewidoczny i kasowalny; po niej jest widoczny w historii pod własną wersją.

## Risks / Trade-offs

**Poprawka działa dopiero od następnej migracji zasiewającej.** `0003`–`0012` zostają
nietknięte, bo są już zaaplikowane wszędzie, a przepisanie zaaplikowanej migracji jest
gorsze od błędu, który naprawia. Jeśli kolizja zaszła w produkcji, ta zmiana jej nie cofa —
odzyskuje tylko wiersz operatora spod unikatu i sprawia, że to się nie powtórzy.

**Helper zasiewu jest obroną, więc ma test swojego trybu awarii** (zasada nr 5): test
wstawia zasiew po zapisie operatora i sprawdza, że nie wszedł, oraz drugi — że przy samych
zasiewach wchodzi normalnie. Bez tej pary reguła jest `WHERE`, o którym następna migracja
zapomni.

## Open Questions

Czy `source` powinno wyjść na drut w `PromptOut`. Przyjęto, że nie: operator czyta treść
i wersję, a to, czy tekst przyszedł z wdrożenia czy z jego własnego zapisu, jest dziś
wnioskiem, nie pytaniem, które terminal zadaje. Kolumna jest po to, żeby moduł umiał
odmówić przykrycia — nie po to, żeby ktoś to oglądał.
