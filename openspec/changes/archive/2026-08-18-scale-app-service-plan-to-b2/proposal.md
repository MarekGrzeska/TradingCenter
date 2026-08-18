## Why

`raise-memory-alert-threshold` podniósł próg alertu z 85 na 92 i zostawił warunek: „jeśli
dołek 08-11 wypadnie wyżej niż dołek 08-10, wraca się do tematu skalowania, nie do
kolejnego podnoszenia progu". Dołek wypadł wyżej. Pomiar z 15 sierpnia 2026 zamyka też
pytanie, którego tamta zmiana świadomie nie rozstrzygała — wyciek czy wzrost:

| Noc (01:00–06:00 UTC) | Dołek `MemoryPercentage` |
|---|---|
| 08-10 | 73,5% |
| 08-11 | 76,5% |
| 08-12 | 80,8% |
| 08-13 | 83,1% |
| 08-14 | 82,4% (szczyt 89,2% o 01:00) |
| 08-15 | 77,3% (po restartach dzisiejszych wdrożeń) |

`MemoryWorkingSet` per aplikacja, szczyt 08-14: `market-data` 311 MB, `agent` 221 MB,
`gateway` 193 MB, `market-mcp` 157 MB. Wobec pierwszej diagnozy z 08-10 obie starsze
aplikacje **zeszły** (gateway 262→193, market-data 327→311). Wzrost przyniosły `market-mcp`
i `agent`, które weszły na plan 12–13 sierpnia. To nie jest wyciek — to są nowi lokatorzy.

Suma szczytów czterech aplikacji to ~882 MB z 1792 MB planu, czyli 49%, a plan raportuje
83–89%. Różnicę zjada platforma: cztery kontenery, cztery Kestrele, Easy Auth i system —
narzut, który rośnie z liczbą aplikacji, nie z ich pracą. Piątej aplikacji na B1 nie ma
gdzie postawić, a próg 92 nad dołkiem 83% znów zaczyna łapać stan normalny, tylko tym
razem przy pełnym planie zamiast pustego.

## What Changes

- `sku_name` planu `asp-tradingcenter` w `infra/app-service.tf`: `B1` → `B2`. Pamięć
  1,75 GB → 3,5 GB, procesor 1 → 2 rdzenie.
- `worker_count` **zostaje 1** i nie jest przedmiotem tej zmiany. Limit 10 żądań/s
  capital.com liczy się na konto, nie na proces (`app-service.tf`, komentarz przy
  `worker_count`), więc drugi worker to drugi `RateGate` wydający ten sam budżet. B2 kupuje
  pamięć i rdzeń, nie równoległość.
- Komentarz przy zasobie planu przestaje mówić o B1 i o darmowym limicie; zamiast tego
  niesie pomiar, który uzasadnił zmianę.
- `infra/monitoring.tf`: opis alertu `alert-plan-memory-high` mówi dziś „The B1 plan
  **both apps** share" — plan dzieli cztery aplikacje i przestaje być B1. Próg 92 zostaje
  bez zmian, mimo że po skalowaniu dołek spadnie do ~40% — patrz `design.md`, gdzie
  obniżenie progu jest rozważone i odrzucone na teraz.

## Capabilities

Brak. To zmiana pojemności infrastruktury: żadne wymaganie, żaden kontrakt między
modułami i żadne obserwowalne zachowanie systemu się nie zmienia — te same aplikacje
odpowiadają tak samo, tylko mają więcej pamięci pod sobą. `skip_specs: true`
w `.openspec.yaml`, tak samo jak w `raise-memory-alert-threshold`, który zmieniał
sąsiednią wartość w sąsiednim pliku.

## Impact

**Infrastruktura**: `infra/app-service.tf` (jedna wartość i komentarz nad nią),
`infra/monitoring.tf` (opis alertu). Nic poza tymi dwoma plikami.

**Kod aplikacji**: żaden. Cztery aplikacje nie wiedzą, na jakim SKU stoją.

**Wdrożenie**: `terraform apply` przestawia SKU planu w miejscu — bez tworzenia nowego
zasobu i bez zmiany nazw hostów. Aplikacje na planie restartują się w trakcie, więc jest to
przerwa liczona w minutach, nie zmiana adresu. `apply` robi operator, nie CI, jak każdą
zmianę infrastruktury w tym repozytorium.

**Koszt bieżący**: cennikowo ~13 USD/mies. za B1 wobec ~26 USD za B2 w tym regionie.
Komentarz w `app-service.tf` twierdzi jednak, że „B1 fits the free-tier grant this
subscription is on" — jeśli to prawda, zmiana nie podwaja rachunku, tylko wyprowadza plan
poza darmowy limit. `az consumption usage list` na tej subskrypcji oddaje `pretaxCost` jako
`null`, więc twierdzenia nie dało się sprawdzić z wiersza poleceń. **Do potwierdzenia przez
operatora w Cost Analysis przed `apply`** — to jedyna rzecz w tej zmianie, której nie
zmierzono, a która może zmienić decyzję.

## Zamknięcie

Zarchiwizowana 18 sierpnia 2026 jako **wykonana i wyprzedzona**. B2 wszedł; plan stoi dziś
na **B3** (`infra/app-service.tf`), przestawiony przez `add-teams-mcp` 16 sierpnia, gdy
doszły kolejne aplikacje. Sześć niezaznaczonych pól rozpada się na trzy grupy i żadna nie
jest zaległą pracą:

- **3.3** — ręczne sprawdzenie żywych notowań po restarcie planu. Odbyło się przy okazji
  kolejnych wdrożeń, tylko nie z tą listą w ręku.
- **4.1–4.3** — „po tygodniu odczytać dołek nocny i dopiero wtedy zdecydować o progu
  alertu". Pytanie zostało zamknięte przez rzeczywistość wcześniej niż przez ten tydzień:
  plan poszedł na B3 razem z dwiema nowymi aplikacjami, więc pomiar dotyczyłby maszyny,
  której już nie ma. Próg alertu jest osobną zmianą, tak jak 4.3 zakładało.
- **5.1–5.2** — walidacja i `review.md`. `openspec validate --strict` przechodzi (wbrew
  temu, czego 5.1 się spodziewało), a `review.md` przestał być wymagany 18 sierpnia 2026
  (`openspec/config.yaml`, `rules.review`).

Zmiana nie ma delty specyfikacji — to zmiana infrastruktury — więc archiwizowana z
`--skip-specs`.
