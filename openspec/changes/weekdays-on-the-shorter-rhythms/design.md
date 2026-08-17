## Context

`recurrence.py` trzyma rytmy i obie zamiany, a `from_cron` jest celowo wąskie: odpowiada
rytmem tylko dla wyrażenia, które `to_cron` wyprodukowałoby z powrotem, i `None` dla
wszystkiego innego. Ta jedna właściwość jest dowodem poprawności pary — i jednocześnie
ograniczeniem, w które wchodzi ta zmiana: **jedno wyrażenie może mieć najwyżej jeden rytm**.
Motywacja jest w `proposal.md`; wymagania w delcie `specs/`.

Dzisiejszy `weekly` już domyśla się poniedziałku–piątku (`scheduleDraft.ts`). Operator ma
więc dni tygodnia, byle chciał jednego wyzwolenia dziennie.

## Goals / Non-Goals

**Goals.** Dni tygodnia przy rytmach częstszych niż dobowy, bez odbierania `from_cron`
jednoznaczności i bez migracji.

**Non-Goals.** Kalendarz świąt giełdowych — rynek stoi nie tylko w weekend, a data
świąteczna to inna rzecz niż dzień tygodnia i inne źródło prawdy. Godziny sesji („tylko
9:00–17:30") — cron umie to wyrazić, kreator nie, i to jest osobna decyzja. Zmiana
czegokolwiek w `scheduler/`: zegar dostaje wyrażenie i o rytmach nie wie.

## Decisions

**D1. Dni tygodnia dostają `every_minutes` i `hourly`, nie `daily`.**
`daily` z dniami tygodnia produkuje `35 9 * * 1,2,3,4,5` — to samo wyrażenie co `weekly`.
`from_cron` musiałoby wtedy wybrać jeden z dwóch rytmów dla jednego wyrażenia, a wybrany
pokazałby się operatorowi zamiast tego, który ułożył. Rozważone i odrzucone: **zwinąć
`weekly` do `daily` + dni** — mniej rytmów i ładniejszy model, ale zmienia rytm każdego już
zapisanego harmonogramu tygodniowego przy odczycie, a nazwa „codziennie" dla czegoś, co
chodzi trzy dni w tygodniu, jest gorsza niż dwa rytmy. `weekly` zostaje tam, gdzie jest, i
jest w kreatorze miejscem na „w wybrane dni o wybranej godzinie".

**D2. Komplet siedmiu dni normalizuje się do braku dni, przy walidacji modelu.**
Inaczej `*/15 * * * 0,1,2,3,4,5,6` i `*/15 * * * *` to jedno wyzwolenie z dwoma zapisami, a
`from_cron` odpowie na pierwsze rytmem bez dni i round-trip przestanie się domykać.
Normalizacja w walidatorze `Recurrence`, nie w `to_cron`: model ma być tym, co operator
zobaczy z powrotem, a nie tym, co ładnie się drukuje. Rozważone: **zostawić siedem dni i
nauczyć `from_cron` je akceptować** — to znaczy przyjąć dwa zapisy jednego stanu i pilnować
ich zgodności w dwóch miejscach zamiast zakazać drugiego w jednym.

**D3. Zero dni to odmowa, nie „każdy dzień".**
Pusta lista jest już dziś odmową przy `weekly` („weekdays must name at least one day") i
zostaje odmową wszędzie. Odróżnienie „nie podano" (`None`, każdy dzień) od „podano pustą"
(odmowa) jest tym, co pozwala brakowi pola znaczyć zgodność wstecz, a nie ciszę.

**D4. Piąte pole zapisujemy listą, nie zakresem.**
`1,2,3,4,5`, tak jak `weekly` robi dziś — nie `1-5`. Powód jest ten sam co przy D2: jedna
postać kanoniczna. Operator, który wpisał `1-5` ręcznie pod „Advanced", dostaje swoje
wyrażenie z powrotem nietknięte i z pustym rytmem, i to jest zachowanie zgodne z
wymaganiem, a nie niedoróbka.

**D5. W kreatorze te same przełączniki dni, co przy `weekly`.**
Rozważone: **osobny checkbox „pomiń weekend"** — krótszy i bliższy temu, jak operator to
zgłosił. Odrzucone, bo nie umie pokazać harmonogramu z dniami `1,3,5`: przy odczycie takiego
rytmu checkbox musiałby być odznaczony i nie mówiłby prawdy o tym, co jest zapisane. Jedna
kontrolka dla wszystkich rytmów niosących dni to też jeden stan do przetestowania.

## Risks / Trade-offs

**Harmonogram już zapisany zmienia znaczenie** → nie zmienia: brak `weekdays` znaczy siedem
dni, dokładnie tak jak dziś. Zmiana jest wyłącznie dodaniem pola opcjonalnego, więc stary
`ScheduleIn` bez niego jest dalej poprawny.

**Terminal wdraża się osobno od modułu** → moduł idzie pierwszy. Terminal sprzed zmiany nie
wysyła `weekdays` przy tych rytmach i dostaje dotychczasowe zachowanie; terminal po zmianie
z modułem sprzed niej dostałby odmowę walidacji z nazwanym polem, a nie ciszę. Kolejność
wdrożeń jest w `tasks.md`.

**Operator ustawia „co 15 minut, pon–pt" i myśli, że kupił sobie sesję giełdową** → nie
kupił: dzień handlowy ma godziny, a święta nie są dniem tygodnia. Kreator MUST NOT nazywać
tego „dniami handlowymi" ani „sesją" — to są dni tygodnia i tak mają się nazywać.

## Migration Plan

Brak migracji bazy: harmonogram trzyma wyrażenie czasowe, a rytm jest z niego wyliczany przy
odczycie, więc nowe pole nie ma czego przepisać. Wycofanie to cofnięcie kodu — wyrażenia
zapisane w międzyczasie (`35 * * * 1,2,3,4,5`) zostają poprawnymi wyrażeniami i dalej się
wyzwalają, tyle że kreator pokaże je jako rytm pusty, czyli pod „Advanced".

## Open Questions

Kolejność archiwizacji: oba modyfikowane wymagania żyją dziś w delcie
`set-a-schedule-without-cron`, nie w `openspec/specs/`. Ta zmiana waliduje się mimo to,
bo delta jest sprawdzana strukturalnie, ale **archiwizacja tej zmiany przed tamtą nałożyłaby
`MODIFIED` na wymaganie, którego w specyfikacji nie ma**. Do rozstrzygnięcia przy
archiwizacji, nie przy pisaniu kodu — i nie zmienia ani wymagań, ani zadań.
