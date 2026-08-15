## Context

Cztery aplikacje na jednym planie B1: `capital-gateway`, `market-data`, `market-mcp`,
`agent`. Terminal nie należy do tego rachunku — stoi na Static Web Apps. Pomiary, na
których stoi ta zmiana, są w `proposal.md`; tu liczy się to, co z nich wynika dla kształtu
planu, i jedna pułapka, która czyni tę zmianę czymś więcej niż podmianą jednego napisu.

**Pułapka: adresy wyjściowe planu zmieniają się razem z jego warstwą.** Zapisano to przy
projektowaniu platformy (`docs/azure-infrastructure-proposal.html`, „Pułapka z adresami
wyjściowymi"): „przejście z B1 na B2 potrafi je przestawić i wtedy aplikacja nagle nie
widzi bazy". Terraform czyta te adresy z zasobu, nie z ręki, więc konfiguracja jest
poprawna — ale trzy miejsca się o nie opierają i jedno z nich nie znosi wartości nieznanej
w chwili planowania:

| Gdzie | Kształt | Znosi „known after apply"? |
|---|---|---|
| `app-service.tf:119`, `ip_restriction` gatewaya | `dynamic` blok wewnątrz zasobu | tak |
| `database.tf:110`, `market_data_outbound` | `for_each` na poziomie zasobu | **nie** |
| `database.tf:121`, `agent_outbound` | `for_each` na poziomie zasobu | **nie** |

`database.tf` opisuje to zachowanie dla pierwszego wdrożenia i mówi, jak je obejść: raz
`terraform apply -target=...`, potem apply bez `-target`. Zmiana SKU stawia listę adresów
z powrotem w stanie „nieznana do czasu apply", więc ta sama dwufazowość wraca — tym razem
nie przy tworzeniu, tylko przy zmianie warstwy.

## Goals / Non-Goals

**Goals:**
- Plan ma zapas pamięci, którego nie ma dziś: dołek nocny schodzi z 83% do ~40%.
- Wdrożenie nie zostawia aplikacji odciętej od bazy przez regułę firewalla wskazującą
  nieaktualne adresy.
- Powód zmiany zostaje w kodzie, przy zasobie, wraz z liczbami — nie tylko w archiwum
  OpenSpec.

**Non-Goals:**
- `worker_count`. Zostaje 1 i jest to decyzja z innego porządku niż pojemność — patrz
  niżej.
- Autoskalowanie. Ten sam powód co wyżej, wzmocniony: skalowanie w poziomie mnoży
  `RateGate`.
- Przeniesienie którejkolwiek aplikacji poza plan. Rozważone, odrzucone niżej.
- Integracja z siecią wirtualną i prywatny endpoint bazy. Docelowe rozwiązanie pułapki
  z adresami wyjściowymi, wciąż za drogie i za złożone jak na cztery aplikacje jednego
  operatora.
- Obniżenie progu alertu. Rozważone, odrzucone na teraz — patrz niżej.

## Decisions

### B2, nie B3 i nie kolejne podniesienie progu

Cztery opcje rozważone:

1. **B2** — 3,5 GB i 2 rdzenie, dwukrotność dzisiejszej pamięci. Dołek 83% schodzi do ~40%,
   a szczyt 89% do ~45%. Zostawia miejsce na piątą aplikację, której dziś nie ma gdzie
   postawić. **Wybrane.**
2. **B3** — 7 GB, czterokrotność ceny za dwukrotność potrzeby. Zapas, którego nic w
   pomiarach nie uzasadnia: suma szczytów czterech aplikacji to 882 MB, a nie 3 GB.
   Odrzucone.
3. **Zostać na B1 i podnieść próg jeszcze raz.** To jest dokładnie ten ruch, przed którym
   `raise-memory-alert-threshold` sam się zabezpieczył w swojej mitygacji. Przy dołku 83%
   próg musiałby iść na 95, a wtedy alert przestaje ostrzegać, a zaczyna potwierdzać
   awarię, która już trwa. Odrzucone.
4. **Przenieść `market-mcp` poza plan** (Container Apps, rozliczenie za sekundę CPU). To
   najmniejsza aplikacja — 44 MB średnio — więc zdejmuje najmniej, a wprowadza drugą
   platformę do obsługi, drugi kształt wdrożenia i drugi sposób uwierzytelniania. Cały
   powód, dla którego plan jest jeden, brzmi: aplikacje chodzą non stop, więc płaci się za
   nie taniej ryczałtem niż za sekundy (`app-service.tf`, komentarz nad zasobem planu).
   Odrzucone.

### `worker_count` zostaje 1, i B2 tego nie zmienia

Drugi worker to drugi `RateGate` wydający ten sam budżet 10 żądań/s, który capital.com
liczy **na konto**, nie na proces. Przepełnienie dociera do wołającego wyglądając jak brak
danych, nie jak problem z ruchem. Komentarz przy `worker_count` mówi to wprost i zakazuje
podnoszenia tej liczby bez uprzedniej zmiany projektu limitowania — ta zmiana go nie
podważa i nie jest okazją, żeby to zrobić przy okazji. B2 kupuje pamięć i rdzeń dla
jednego workera, nie drugiego workera.

### Próg alertu zostaje na 92

Kuszące jest wrócić nim do 85, skoro dołek spadnie do 40%. Trzy powody, żeby tego teraz
nie robić:

- Baseline na B2 nie jest zmierzony. 92 nad przewidywanym dołkiem 40% to próg, który nie
  dzwoni bez powodu; 85 nad dołkiem, którego nikt jeszcze nie widział, to zgadywanie
  drugi raz z rzędu, po tym jak pierwsze zgadywanie kosztowało fałszywy alarm.
- Zmiana dwóch rzeczy naraz czyni następny pomiar nieczytelnym. Jeśli po skalowaniu coś
  będzie nie tak, chcemy wiedzieć, czy to plan, czy próg.
- 92 przy 3,5 GB oznacza 3,2 GB zajęte — to jest prawdziwa anomalia, a nie stan normalny,
  którym było 92 przy 1,75 GB. Próg nie zmienił wartości, ale zmienił znaczenie, i dopiero
  teraz znaczy to, co miał znaczyć.

Do rewizji po tygodniu danych z B2, osobną zmianą, z pomiarem — tą samą drogą, którą
przyszła ta.

### Dwa `apply`, w tej kolejności

```
terraform apply -target=azurerm_service_plan.main    # SKU; aplikacje restartują
terraform apply                                       # reguły firewalla na nowe adresy
```

Powód jest w `Context`: `for_each` na poziomie zasobu odmawia planowania wobec wartości
nieznanej do czasu apply, a lista adresów wyjściowych staje się taka w chwili, w której
zmienia się warstwa planu. Ta sama dwufazowość, którą `database.tf` opisuje dla pierwszego
wdrożenia, z tego samego powodu.

Między jednym a drugim `apply` `market-data` i `agent` mogą nie widzieć bazy. To jest
okno, nie usterka — ale jest to okno, o którym trzeba wiedzieć, że się otwiera, zamiast
odkrywać je z alertu.

## Risks / Trade-offs

- **[Ryzyko]** Adresy wyjściowe przestawiają się i reguły firewalla przez chwilę wskazują
  poprzednie. `market-data` traci bazę w środku ingestu, `agent` w środku tury.
  → **Mitygacja**: dwa `apply` w kolejności wyżej, wykonane pod ręką, nie w tle. `market-data`
  zapisuje zakresy pokrycia, więc przerwa w zbieraniu jest zapisana jako dziura, a nie jako
  cisza rynku — moduł sam z siebie nie skłamie o tym, czego nie zebrał.
- **[Ryzyko]** Wszystkie cztery aplikacje restartują się przy zmianie SKU. Sesja
  capital.com gatewaya zostaje zestawiona od nowa.
  → **Mitygacja**: żadna nie jest potrzebna. Sesje capital.com współistnieją — zmierzone
  10 sierpnia i zapisane w `CLAUDE.md` — więc ponowne logowanie nie unieważnia niczego,
  a `stream_tokens_for` odnawia strumień. Przerwa liczy się w minutach.
- **[Ryzyko]** Rachunek rośnie o tyle, o ile — a być może z zera. Komentarz w
  `app-service.tf` twierdzi, że B1 mieści się w darmowym rocznym limicie subskrypcji;
  `az consumption usage list` oddaje na niej `pretaxCost` jako `null`, więc twierdzenia nie
  potwierdzono ani nie obalono.
  → **Mitygacja**: operator sprawdza Cost Analysis **przed** pierwszym `apply`. Jeśli B1 jest
  darmowy, to jest decyzja „zacząć płacić", nie „zapłacić dwa razy tyle", i wtedy warto ją
  podjąć świadomie — na przykład godząc się na nią do końca darmowego roku, a nie na stałe.
- **[Kompromis]** B2 odsuwa próg w czasie, jeśli któraś aplikacja zacznie kiedyś naprawdę
  wyciekać. Dziś nic na to nie wskazuje — dwie starsze aplikacje między 08-10 a 08-14 zeszły
  z pamięci, nie urosły — ale alert przy 92 nad 3,5 GB odezwie się później niż przy 92 nad
  1,75 GB.
  → **Mitygacja**: świadoma. Wyciek widziany z zapasem 2 GB jest tańszy do zdiagnozowania
  niż wyciek widziany z zapasem 200 MB, bo w tym drugim przypadku diagnozę robi się na
  aplikacji, która już się restartuje.
