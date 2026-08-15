## Verdict

Wdrożone i potwierdzone na Azure: `alert-plan-memory-high` ma `threshold = 92`. Zmiana
jednej wartości w `infra/monitoring.tf` (`420fd18`), `apply` zrobiony przez operatora,
alert włączony.

Obserwacja z zadania 3.1 została przeprowadzona przy tym przeglądzie — i jej wynik jest
tym, którego `design.md` nie chciał zobaczyć: **dołek nocny 08-11 wypadł wyżej niż dołek
08-10**. To dokładnie ten warunek, przy którym mitygacja w `Risks / Trade-offs` mówi
„wraca się do tematu skalowania, nie do kolejnego podnoszenia progu". Zmiana jest
domknięta; temat, który miała odsunąć, nie jest.

## Verified

Odczytane z Azure 15 sierpnia 2026, tożsamością operatora:

- `az monitor metrics alert show --name alert-plan-memory-high` → `threshold: 92.0`,
  `enabled: true`, opis zaktualizowany. Zadania 2.1 i 2.2 zrobione, tylko nieodhaczone.
- `MemoryPercentage` planu `asp-tradingcenter`, średnie godzinowe w oknie 01:00–06:00 UTC,
  czyli w dołku, który `design.md` wskazał jako punkt porównania:

| Noc | Dołek (średnia godzinowa) | Δ wobec 08-10 |
|---|---|---|
| 08-10 | 73,5% | — |
| 08-11 | 76,5% | +3,0 pp |
| 08-12 | 80,8% | +7,3 pp |
| 08-13 | 83,1% | +9,7 pp |
| 08-14 | 82,4% | +8,9 pp |
| 08-15 | 77,3% | +3,8 pp |

Próg 92 nie został przekroczony ani razu w tym oknie; najbliżej było 08-14 o 01:00 —
89,2% średniej godzinowej. Zapas, który miał wynosić 8 pp ponad szczyt, wynosi dziś
niecałe 3 pp nad dołkiem sprzed doby.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **Medium** | plan `asp-tradingcenter` | Warunek z `design.md` — „jeśli dołek 08-11 wypadnie wyżej niż dołek 08-10" — jest spełniony i to na tej samej parze aplikacji, dla której go postawiono: trzeci i czwarty moduł (`market-mcp`, `agent`) weszły na plan dopiero 12–13 sierpnia. +3,0 pp między dwiema nocami przy niezmienionym zestawie aplikacji to nie różnica poniedziałek-vs-niedziela. | open — patrz Follow-ups |
| **Low** | `infra/monitoring.tf`, `description` alertu | „The B1 plan **both apps** share is over 92% memory." Plan dzieli dziś pięć aplikacji, nie dwie. Opis alertu jest jedyną rzeczą, którą operator czyta o trzeciej w nocy, i mówi nieprawdę o tym, co się dzieli tą pamięcią. | open — jedna linia, do dołożenia przy najbliższej zmianie w `monitoring.tf` |
| **Low** | pomiar | Spadek dołka 08-15 do 77,3% zbiega się z dzisiejszymi wdrożeniami (`agent` restartował się dwa razy), więc jest tak samo zgodny z „pamięć odzyskana przy restarcie" jak z „obciążenie zelżało". Sam z siebie niczego nie unieważnia i nie potwierdza. | observation |

## Gaps

- **Wyciek-czy-nie nadal nierozstrzygnięty**, i to było w `Non-Goals` od początku. Sześć
  dołków to więcej niż jeden cykl, na którym stawiano diagnozę, ale w połowie tego okna
  zmienił się skład planu — więc dane rozdzielają się na dwa reżimy po dwie i trzy noce,
  a nie na jeden szereg.
- **`MemoryWorkingSet` poszczególnych aplikacji nie został odczytany ponownie.** Pierwsza
  diagnoza rozbijała plan na aplikacje (gateway 163→262 MB, market-data 261→327 MB); to
  porównanie po dołożeniu trzech kolejnych modułów powiedziałoby, czy baseline urósł
  proporcjonalnie do liczby aplikacji, czy któraś rośnie sama.

## Follow-ups

- Wrócić do skalowania, zgodnie z mitygacją w `design.md` — nie do podnoszenia progu po
  raz drugi. Argument jest dziś mocniejszy, niż był przy pisaniu tamtego tekstu: plan B1
  hostuje pięć aplikacji zamiast dwóch, a `worker_count = 1` zostaje niezależnie od SKU
  (`RateGate` capital.com), więc B2 kupuje wyłącznie pamięć — co jest dokładnie tym, czego
  brakuje.
- Poprawić opis alertu: „both apps" → pięć aplikacji.
- Odczytać `MemoryWorkingSet` per aplikacja przed decyzją o SKU, żeby wiedzieć, czy płaci
  się za wzrost, czy za wyciek.
