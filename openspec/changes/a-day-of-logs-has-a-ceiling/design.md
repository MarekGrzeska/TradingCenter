## Context

Jeden workspace, `log-tradingcenter`, PerGB2018, retencja 30 dni, bez limitu. Osiem aplikacji
pisze do jednego App Insights na nim. Pomiar z 4 września 2026 (tabela `Usage`, 27 dni):
0,4–1,4 GB dziennie, z czego 97% z dwóch źródeł, które zamyka PR #242. Po nim spodziewany
ingest to dziesiątki MB dziennie: `AppMetrics` ~45 MB, `AppTraces` i `AppRequests` po kilka,
sondy `GET http send` z czterech pętli ~4 MB. Cena: 2,567 EUR za GB ponad 5 GB w miesiącu.
Alerty metryczne (`candle_age`, `loop_stopped`) stoją na metrykach niestandardowych
eksportowanych przez ten sam SDK. Subskrypcja jest PAYG od upgrade'u z trialu i nie ma
żadnego budżetu. Motywacja: proposal.md, „Why".

## Goals / Non-Goals

**Goals:**

- Górna granica kosztu jednej doby telemetrii, wyrażona w Terraformie, z liczbą i powodem.
- Osiągnięcie tej granicy jest alertem, nie ciszą.
- Miesięczny koszt ma próg, po którym operator dostaje list.

**Non-Goals:**

- Zmniejszanie ingestu — to #242, i tylko dlatego ten sufit może być niski.
- Retencja, archiwizacja do tańszej tabeli, sampling w SDK. Po #242 nie ma czego
  optymalizować; wrócić, gdy `Usage` pokaże, że jest.
- Budżety per zasób. Jeden budżet na subskrypcję wystarcza jednemu operatorowi.

## Decisions

### Sufit 1 GB na dobę, nie 0,5 i nie 5

Wymaganie mówi „dziesięciokrotny zapas nad zdrowym dniem"; zdrowy dzień po #242 to rzędu
50 MB, więc 0,5 GB by wystarczyło. 1 GB wybrany z dwóch powodów. Pierwszy: dzień wdrożenia
ośmiu modułów i dzień z `LOG_LEVEL=DEBUG` włączonym na jednym z nich przez godzinę to nie
incydenty, a oba mieszczą się w 1 GB i niekoniecznie w 0,5. Drugi: najgorszy miesiąc
z sufitem 1 GB to 31 × 2,567 = **80 EUR**, czyli tyle, ile kosztowała sierpniowa pętla bez
sufitu — granica, poniżej której cięcie sufitu daje coraz mniej, a ryzyko odcięcia zdrowego
dnia rośnie. 5 GB nie ogranicza niczego, co nie ograniczyłoby się samo.

Alternatywa odrzucona: brak sufitu, sam budżet. Dane kosztowe spływają z 8–24 h opóźnieniem,
a prognoza liczy się raz dziennie; budżet powiedziałby o pętli po trzech dniach, sufit
zatrzymuje ją tego samego dnia. Oba są potrzebne, bo widzą co innego.

### Alert na osiągnięcie sufitu: zapytanie do `_LogOperation`, nie cisza pozostałych alertów

Platforma zapisuje osiągnięcie limitu jako wpis w tabeli `_LogOperation` (kategoria
`Ingestion`, operacja o zatrzymaniu zbierania) — ta tabela nie podlega sufitowi, więc alert na
niej działa dokładnie wtedy, gdy wszystko inne stoi. Jedna reguła `scheduled_query_rules_alert_v2`,
co 15 minut nad oknem godziny, severity 2, do `ag-tradingcenter-operator`. Koszt rzędu
0,13 EUR miesięcznie: ta sama pozycja, którą do 2 września zajmował `alert-app-exceptions-high`.

Alternatywa odrzucona: uznać, że milknące `candle_age` i `loop_stopped` wystarczą. Nie
wystarczą z powodu, który ten projekt już raz zapisał w `a-stopped-loop-wakes-somebody`: zero
i „nic nie wiadomo" to z metryki jedno i to samo. Czy metryki niestandardowe w ogóle
przestają docierać po osiągnięciu sufitu, **nie jest zmierzone** — i właśnie dlatego alert
stoi na zdarzeniu, a nie na skutku: operator dowiaduje się tak samo w obu przypadkach.

### Budżet 75 EUR, prognoza 80%, rzeczywisty 100%

Tempo po #242: plan B3 45,2 + monitor ~1,5 = **47 EUR**. Od sierpnia 2027 dochodzi baza,
~17 EUR, razem ~64. Próg prognozy 80% z 75 to 60 EUR: zdrowy miesiąc dziś ma 13 EUR zapasu,
a pierwszy miesiąc płatnej bazy przekroczy próg i przyśle list — to jest zamierzone, bo ten
list to przypomnienie o decyzji, którą `database.tf` odkłada do tamtej daty. Kwota to
liczba w Terraformie z tym akapitem obok; zmiana SKU zmienia ją świadomie.

Alternatywa: 60 EUR z progiem 80% = 48, o jeden EUR nad tempem — budziłby co miesiąc bez powodu.

### Budżet w Terraformie, mimo że nie jest zasobem w grupie

`azurerm_consumption_budget_subscription` potrzebuje `data "azurerm_subscription"` i prawa
Cost Management Contributor przy `apply` — operator je ma, CI robi tylko `plan` i potrzebuje
odczytu. Alternatywa `az consumption budget create` ręcznie byłaby czwartym zasobem spoza
Terraforma w tej subskrypcji, obok dwunastu w Sweden Central, i nikt by jej nie znalazł przy
następnym przeglądzie.

`start_date` to pierwszy dzień bieżącego miesiąca w chwili pisania (2026-09-01); Azure przyjmuje
daty wsteczne, więc późniejszy `apply` nie wymaga edycji.

## Risks / Trade-offs

- **Sufit nałożony przed wdrożeniem #242 odcina zdrowe dane co drugi dzień** (dziś 0,8 GB/dobę,
  szczyty 1,4) → kolejność jest twarda: merge #242, dzień odczytu `Usage` poniżej 100 MB,
  dopiero `apply`. tasks.md ma to jako osobny krok z warunkiem, nie jako notatkę.
- **Po osiągnięciu sufitu alerty metryczne mogą oślepnąć do północy UTC** (niezmierzone, patrz
  wyżej) → alert na `_LogOperation` mówi o tym w ciągu godziny; runbook mówi, co wtedy
  zrobić: podnieść sufit ręcznie na resztę dnia, jeśli trwa incydent, w którym telemetria jest
  potrzebna.
- **Budżet widzi koszt z opóźnieniem doby** → nie jest bezpiecznikiem i tak jest opisany; od
  zatrzymania jest sufit.
- **Reset sufitu następuje o stałej godzinie, którą Azure przypisuje przy włączeniu** (nie o
  północy lokalnej) → runbook podaje, gdzie ją odczytać; nic w tej zmianie od niej nie zależy.
