# Review — the-seed-does-not-overwrite-the-operator

## Co dowodzi którego scenariusza

| Scenariusz wymagania | Test |
|---|---|
| Wdrożenie zasiewa prompt, gdy operator nic nie zapisał | `test_prompt_seed.py::TestTheSeedYields::test_a_seed_lands_when_the_newest_revision_is_itself_a_seed` |
| Wdrożenie zasiewa prompt po zapisie operatora | `test_prompt_seed.py::TestTheSeedYields::test_a_seed_does_not_land_after_the_operator_has_written` |
| Dwa zapisy o tej samej wersji | `test_prompt_seed.py::TestVersionsAreUnique::test_two_rows_may_not_share_a_version` |

Poza nimi: `test_migrate.py::test_the_prompt_source_migration_backfills_a_collision_the_way_it_claims`
przechodzi backfill na kolizji zbudowanej na `0012` i wraca w dół, a
`test_prompt_seed.py::test_the_operators_next_version_is_the_one_the_next_seed_would_use`
trzyma arytmetykę, z której cały bug wynikał, jako stwierdzenie, a nie wspomnienie.

**Obrona sprawdzona przez odwrócenie.** Po usunięciu `WHERE` z `_SEED` czerwienieją trzy
testy, w tym ten opisujący dokładnie scenariusz, przed którym straż broni. Bez tego kroku
byłby to `WHERE`, o którym nie wiadomo, czy cokolwiek trzyma.

## Znalezisko: ta zmiana o mało nie zrobiła dokładnie tego, przed czym ostrzega

`design.md` D1 odrzuca sam unikat na `version` argumentem, że migracje biegną w `lifespan`,
więc **ograniczenie, które pada, to moduł, który nie wstaje**. Backfill napisany w tej samej
zmianie aliasował podzapytanie jako `inner` — słowo zarezerwowane w PostgreSQL — więc
migracja rzucała `PostgresSyntaxError`. Czyli: nie ograniczenie, ale ta sama awaria, w tym
samym miejscu, z tego samego pliku.

Złapały to testy przy pierwszym uruchomieniu, nie przeczytanie migracji. Warto to zapisać,
bo migracja jest kodem, który na tym repozytorium **nie ma jak paść inaczej niż na
produkcji**, jeśli nie zostanie uruchomiony wcześniej — i to jest argument za tym, żeby
`test_migrate.py` chodziło po każdej nietrywialnej migracji, a nie tylko po tych, które
ktoś uznał za ryzykowne.

## Czego ta zmiana nie naprawia

**Kolizji, która już zaszła w produkcji.** Nie da się jej cofnąć: tekst operatora został
przykryty i tylko baza wie, czy tak się stało. Migracja odzyskuje ten wiersz spod unikatu
i nadaje mu czytelną wersję (`v11+operator<id>`), więc przestaje być niewidoczny
i kasowalny — ale treść, która obowiązywała, pozostaje zasiewem.

**Zasiew wciąż jest w migracji.** Druga rozważana droga — domyślny prompt jako stała
w kodzie, tabela wyłącznie na edycje operatora — kasuje 803 linie prozy z historii migracji
i jest pojęciowo czystsza. Odrzucona tu świadomie, bo zmienia opublikowany scenariusz
i wywraca 20 z 23 testów `test_prompt_store.py`; to decyzja o tym, czym prompt jest,
a nie naprawa tego, że ginie.

**Poprawka działa od następnej migracji zasiewającej.** `0003`–`0012` zostają nietknięte.
Nie ma dziś testu, który by tego pilnował — następna migracja zasiewająca musi zawołać
`seed_prompt`, i jedyne, co ją do tego popycha, to komentarz w `prompt_seed.py` oraz to,
że `test_seed_prompt_is_not_reachable_from_the_runtime_path` trzyma ten moduł tam, gdzie
migracje po niego sięgają. Test, który by *wymuszał* jego użycie w każdej przyszłej
migracji zasiewającej, wymagałby najpierw sposobu na rozpoznanie takiej migracji — i to
jest otwarta sprawa, nie przeoczenie.
