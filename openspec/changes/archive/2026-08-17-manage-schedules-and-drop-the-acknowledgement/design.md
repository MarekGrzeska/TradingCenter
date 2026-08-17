## Context

Motywacja jest w `proposal.md`; wymagania w deltach. Trzy fakty z kodu, na których stoją
decyzje poniżej, wszystkie odczytane, nie założone:

- `check_unattended` jest wołane **wyłącznie** z `routers/schedules.py` (cztery miejsca:
  zapis i poprawka harmonogramu oraz wyzwalacza). W `runner/` i `scheduler/` słowo
  „unattended" nie występuje ani razu.
- `schedule_fires.schedule_id` i `trigger_id` to klucze obce **bez `ON DELETE`**, a
  `CHECK` w migracji `0005` żąda, żeby dokładnie jeden z nich był niepusty. Historii nie
  da się osierocić — próba usunięcia harmonogramu, który się wyzwalał, dziś by się nie
  powiodła.
- `runs` nie ma kolumny wskazującej harmonogram; to `schedule_fires.run_id` wskazuje
  przebieg. Kierunek jest więc już taki, jakiego wymaga „przebiegi zostają".

## Goals / Non-Goals

**Goals.** Usunięcie pola i sprawdzenia w całości; usuwanie i zarządzanie z obu dróg —
czatu i terminala — nad jednym zestawem tras.

**Non-Goals.** Domykanie dziury, przez którą tryb „najnowsza rewizja" omija sprawdzenie:
usuwamy sprawdzenie, więc nie ma czego domykać. Zmiana granic handlowych ani dobowej
granicy kosztu — to są hamulce, które zostają i nie są przedmiotem tej zmiany. Kasowanie
przebiegów: nie tą drogą i nie w tej zmianie.

## Decisions

**D1. Kolumna znika, a nie zostaje jako martwe pole.**
Zostawienie `unattended_ack` w bazie „na wszelki wypadek" daje kolumnę, którą następny
czytelnik uzna za obowiązującą, i wiersze mówiące o zgodzie, której nikt nigdy nie
sprawdzi. Migracja `drop_column` dla obu tabel, `downgrade` odtwarza kolumnę z domyślnym
`false` — czyli w stanie, w którym każdy istniejący harmonogram byłby po cofnięciu
odmawiany przy najbliższej **poprawce**, ale nie przy wyzwoleniu. Zapisane wprost w
migracji, bo to jest cena cofnięcia, a nie jego usterka.

**D2. Usunięcie kasuje historię wyzwoleń kaskadą w bazie, nie pętlą w kodzie.**
`ON DELETE CASCADE` na obu kluczach `schedule_fires`, dołożone tą samą migracją.
Alternatywa — `DELETE FROM schedule_fires` przed `DELETE FROM schedules` w kodzie trasy —
jest tą samą kaskadą napisaną ręcznie, w dwóch miejscach zamiast jednego, i rozjeżdża się
przy pierwszej trasie, która o niej zapomni. Osierocenia (`schedule_id = NULL`) nie ma jako
wariantu: `CHECK` z `0005` go zabrania, a poluzowanie go znaczyłoby historię, której nie da
się przypisać do niczego i której nikt nie przeczyta, bo trasa odczytu pyta po
identyfikatorze wpisu.

**D3. `DELETE` odpowiada `204`, a cudzy i nieistniejący wpis dostają `404`.**
Tak samo jak istniejące trasy odczytu w tym module: właściciel jest filtrem zapytania, nie
warunkiem po nim, więc „nie twoje" i „nie ma" są jednym zapytaniem i jedną odpowiedzią.
Cudzy wpis odróżniony od nieistniejącego byłby wyciekiem faktu, że taki wpis istnieje.

**D4. Poprawka z czatu idzie przez `PUT`, nie przez „usuń i załóż".**
Trasa już jest i zachowuje wiersz razem z jego historią. Model, któremu damy tylko
zakładanie i usuwanie, poprawi harmonogram przez skasowanie go i założenie drugiego —
co gubi historię i zmienia identyfikator, o którym operator właśnie rozmawiał.

**D5. Narzędzie usuwające jest jedno na rodzaj, bez „usuń wszystkie".**
`delete_schedule(schedule_id)` i `delete_trigger(trigger_id)`. Narzędzie kasujące hurtem
jest jednym wywołaniem modelu między „posprzątaj to" a pustym katalogiem; operator, który
chce usunąć sześć wpisów, mówi to sześć razy albo robi to w terminalu, gdzie widzi listę.

**D6. Terminal pyta o potwierdzenie, czat nie.**
W terminalu usunięcie jest jednym kliknięciem w liście i sąsiaduje z „Disable", więc pomyłka
jest o jeden piksel; potwierdzenie nazywa to, co zniknie. W czacie potwierdzeniem jest samo
zdanie operatora — model, który pyta „czy na pewno", po czym woła narzędzie w tej samej
turze, dokłada rundę i niczego nie sprawdza.

## Risks / Trade-offs

**Nic nie stoi między rozmową a harmonogramem, który składa zlecenia** → to jest świadomy
skutek, nie ryzyko uboczne. Zostają: konto demonstracyjne wymuszone u gatewaya (moduł
`trading-mcp` nie otwiera portu bez potwierdzenia), granice handlowe rewizji, dobowa granica
kosztu i ślad przed każdym zleceniem. Czego nie ma i nie było: hamulca zależnego od tego,
kto o harmonogram poprosił.

**Usunięcie jest nieodwracalne i zabiera historię** → dlatego wyłączenie zostaje osobną,
równorzędną czynnością w obu drogach, a potwierdzenie w terminalu nazywa stratę. Przebiegi
i ich koszt zostają, więc „ile mnie to kosztowało" ma odpowiedź po usunięciu harmonogramu.

**Terminal i moduł wdrażają się osobno** → moduł pierwszy. Terminal sprzed zmiany wysyła
`unattended_ack` w ciele zapisu; moduł po zmianie musi to **zignorować**, a nie odrzucić —
inaczej okno między dwoma wdrożeniami jest oknem, w którym nie da się zapisać harmonogramu.
Pydantic domyślnie ignoruje nadmiarowe pola i tak ma zostać; zadanie na to jest w
`tasks.md`.

## Migration Plan

Jedna migracja: `drop_column` na `schedules` i `triggers`, plus wymiana obu kluczy obcych
`schedule_fires` na wersje z `ON DELETE CASCADE`. Kolejność wdrożeń: `teams` (migracja idzie
w jego `lifespan`), potem `teams-mcp` i terminal. Cofnięcie: kolumna wraca z `false`,
kaskady wracają do wersji bez `ON DELETE` — a wtedy usunięcie wpisu z historią znów będzie
odmawiane przez bazę.

## Open Questions

Kolejność archiwizacji, ta sama co przy poprzedniej zmianie i o jeden stopień gorsza:
`REMOVED` w tej delcie dotyczy wymagania, które żyje w delcie `add-teams-schedules-and-triggers`,
a nie w `openspec/specs/`. Zarchiwizowanie tej zmiany przed tamtą usuwałoby wymaganie,
którego w specyfikacji jeszcze nie ma. Do rozstrzygnięcia przy archiwizacji; nie zmienia
ani wymagań, ani zadań, ani kodu.
