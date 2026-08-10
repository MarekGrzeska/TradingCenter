## Context

Zob. `proposal.md` — `## Why`. Diagnoza z `az monitor metrics list` na
`Microsoft.Web/serverfarms` (`MemoryPercentage`, plan `asp-tradingcenter`) i `Microsoft.Web/sites`
(`MemoryWorkingSet`, obie aplikacje) za ostatnie 30h:

- Piła dobowa: dołek ~01:00-06:00 UTC, szczyt wieczorem/rano — nie płaska linia.
- Drugi szczyt (poniedziałek) wyżej niż pierwszy (niedziela) w obu aplikacjach — gateway
  163→262 MB, market-data 261→327 MB working set. Za mało danych (jeden cykl), by odróżnić
  wolny wyciek od zwykłej różnicy dnia tygodnia.
- Working set obu aplikacji razem (~590 MB max) to ~31% z 1.75 GB planu B1 — resztę do 82-91%
  raportowanego przez `MemoryPercentage` zajmuje platforma (Easy Auth, Kestrel, OS), nie kod
  aplikacji.
- Activity Log bez żadnego restartu/recyklingu procesu od 08-09 — wzorca nie maskuje odzyskiwanie
  pamięci przez platformę.

## Goals / Non-Goals

**Goals:**
- Próg alertu przestaje łapać normalny stan planu, zostając czuły na realny problem.

**Non-Goals:**
- Rozstrzygnięcie wyciek-czy-nie. Ta zmiana nie diagnozuje dalej — tylko przestaje fałszywie
  alarmować, dopóki diagnoza się nie dokończy.
- Skalowanie planu. Odrzucone tutaj, zob. niżej.

## Decisions

### Próg 92, nie 90 i nie skalowanie do B2

Trzy opcje rozważone:

1. **Podnieść próg do 92.** Zostawia 8 pp zapasu ponad zaobserwowany dotychczasowy szczyt (91%),
   bez zmiany infrastruktury. Wybrane.
2. **Podnieść tylko do 90.** Zapas 1 pp ponad już zaobserwowany szczyt (91.0 z 08-10T13:27) —
   alert i tak by odpalił przy następnym szczycie tej samej piły. Odrzucone jako za ciasne.
3. **Skalować plan do B2.** Rozwiązuje objaw natychmiast, ale kosztuje ~2× rachunku za problem,
   którego natura (dobowy cykl vs wyciek) nie jest jeszcze znana — B2 tylko odsuwa próg w czasie,
   jeśli to wyciek. `worker_count = 1` musi w każdym razie zostać (`RateGate` capital.com,
   `app-service.tf`), więc B2 nie dałoby dodatkowej pojemności przez równoległość i tak.
   Odrzucone na teraz; zostaje opcją, jeśli kolejne cykle potwierdzą realny wzrost.

### Nic więcej się nie zmienia

`sku_name` i `worker_count` zostają bez zmian — to nie jest zmiana pojemności, tylko czułości
alertu.

## Risks / Trade-offs

- **[Ryzyko]** Jeśli piła rzeczywiście jest powolnym wyciekiem (nie potwierdzone), 92 kupuje
  kilka dni zanim znów odpali, kosztem późniejszego wykrycia. → **Mitygacja**: brak automatycznej
  — to świadomy kompromis do czasu kolejnej obserwacji dołka nocnego; jeśli dołek 08-11 wypadnie
  wyżej niż dołek 08-10, wraca się do tematu skalowania, nie do kolejnego podnoszenia progu.
- **[Ryzyko]** Podniesiony próg mógłby maskować przyszły, niezwiązany skok pamięci (np. po
  wdrożeniu nowego ingestu). → **Mitygacja**: 92 to nadal próg poniżej 100 — restart z powodu OOM
  i tak by nastąpił i byłby widoczny przez inne alerty (5xx) oraz w logach App Service.
