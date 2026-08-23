# Design — an-observation-is-collected-or-gone

## Context

Motywacja w proposal.md. Stan zastany, który kształtuje rozwiązanie:

- `tracked_events` jest korzeniem kaskady: `markets`, `outcomes`, `price_samples`
  i `collected_ranges` wiszą pod nim przez `ON DELETE CASCADE` (migracje 0001 i 0002).
- `store.delete_history` kasuje próbki i zakresy razem, w jednej transakcji, i zeruje
  `oldest_available_at` — bo zakres uchodzący za zebrany po usunięciu próbek jest wiążący dla
  planowania i uzupełnianie już tam nie wróci.
- `views.collection_of` wylicza stan z dwóch pól: `event.tracking` i `event.resolved`.
  `ended` jest pierwszą gałęzią tej funkcji.
- Sufit obserwacji jest wymaganiem (`polymarket-data-tracking`), a `track_event` odsyła model
  do `untrack_event`, gdy w niego uderzy.

## Goals / Non-Goals

**Goals:**

- Dwa stany obserwacji, z których żaden nie jest miejscem na liście, które nic nie robi.
- Usunięcie niepodzielne: albo znika wydarzenie z całą historią, albo nie znika nic.
- Reguła „żadne narzędzie nie niszczy historii" nienaruszona po zdjęciu `untrack_event`.

**Non-Goals:**

- Zmiana sposobu zbierania, uzupełniania i sufitu obserwacji.
- Archiwizacja obserwacji „na bok" zamiast usunięcia — to byłby czwarty stan zamiast
  trzeciego.
- Kosz, cofanie, potwierdzenie dwustopniowe. Jedno potwierdzenie nazywające zakres
  i nieodwracalność jest tym, co ten repozytorium już stosuje do kasowania historii.

## Decisions

**1. Usunięcie robi kaskada schematu, nie transakcja napisana w Pythonie.** Jedno
`DELETE FROM tracked_events WHERE provider_event_id = $1` zabiera rynki, wyniki, próbki
i zakresy, bo tak stoją klucze obce. Niepodzielność jest wtedy własnością bazy, a nie
czterech instrukcji, których kolejność ktoś kiedyś poprawi. Odrzucone: wywołanie
`delete_history` i `end_tracking` po kolei — to jest ta sama czynność złożona z dwóch, która
umie paść w połowie i zostawić historię bez obserwacji albo odwrotnie.

**2. Zdejmujemy `tracking_ended_at`, a nie tylko przestajemy je ustawiać.** Kolumna, której
nic nie zapisuje, i stan `ended`, którego nic nie potrafi wytworzyć, dalej byłyby ogłaszane
przez `CollectionOut.state` — obietnica bez producenta. To jest dokładnie ten kształt, który
market-data usunął ze swojego katalogu wskaźników („trzeci, «anchored», był zadeklarowany
tutaj i przez żaden wpis nieosiągalny"). Razem z kolumną znika `include_ended` z trzech
funkcji magazynu i gałąź z `views.collection_of`.

**3. Zdjęcie `untrack_event` jest ceną dwóch stanów, i płacimy ją po stronie modelu.**
Gdyby narzędzie zostało, model dalej wytwarzałby stan, którego nie ma; gdyby zostało
i usuwało całkowicie, model dostałby do ręki czynność nieodwracalną, której moduł odmawia mu
świadomie. Trzecie wyjście — zostawić i ukryć zatrzymane na ekranie — jest najgorsze
z trzech: historia w bazie, nieosiągalna z ekranu, nie do usunięcia.

Skutek dla modelu jest konkretny i trzeba go nazwać: **po uderzeniu w sufit model nie zrobi
sobie miejsca sam.** Odmowa mówi, żeby poprosił operatora. To jest utrata autonomii i jest
zamierzona — miejsce robiło się dotąd kosztem cudzej obserwacji, o czym operator dowiadywał
się z wiersza, który przestał zbierać.

**4. Zastane `ended` znikają razem z historią, w migracji.** Alternatywa — wznowić im
zbieranie — nie niszczy niczego i została odrzucona przez operatora: te obserwacje zostały
zatrzymane, bo przestały być interesujące, a wznowienie ich to ruch do dostawcy za dane,
których nikt nie chce. Migracja kasuje przed zdjęciem kolumny, w tej kolejności, i to jest
jedyna kolejność, która działa.

**5. Zwinięty wiersz nie niesie ceny, i to nie jest oszczędność miejsca.** Skrót pokazywał
„lidera" każdego rynku — jedną cenę na rynek, wybraną przez ten widok. Dla rynku dwuwynikowego
brał `Yes`, dla wielowynikowego najwyższą. To jest sprowadzenie rynku do jednej ceny „za",
którego rozwinięty widok ma zakaz. Zwinięcie MUST identyfikować obserwację; odczyt jest po
rozwinięciu.

**Stan zbierania zostaje**, mimo że jest to informacja spoza tytułu i grupy: obecność na
liście nie dowodzi, że ceny przychodzą, i po to moduł w ogóle publikuje ten stan. `stalled`
na zwiniętym wierszu jest jedynym miejscem, w którym operator dowie się, że coś stoi, zanim
to rozwinie.

## Risks / Trade-offs

- [Model nie zwolni sobie miejsca i utknie na suficie] → odmowa `track_event` mówi wprost,
  co ma zrobić i kto ma to zrobić; sufit jest parametrem modułu, nie stałą.
- [Operator usunie obserwację, chcąc tylko zatrzymać zbieranie] → potwierdzenie nazywa zakres
  („wydarzenie i wszystko, co dla niego zebrano") i nieodwracalność, a zatrzymania nie ma już
  na ekranie, więc nie ma czego pomylić z czym.
- [Migracja kasuje historię, której ktoś chciał] → nazwane w proposal.md jako świadomy koszt;
  liczba usuniętych wierszy idzie do logu na poziomie `warning`, tak jak przy
  `delete_history`.
- [`resolved` zostaje na liście i nic nie zbiera] → to nie jest ten sam przypadek: rynek
  rozstrzygnięty ma cenę, która stoi, a jego historia jest tym, czego dostawca nie odda.
  `polymarket-data-tracking` wprost zabrania mu znikać samoczynnie i to zostaje bez zmian.

## Migration Plan

Migracja 0003, dwa kroki w jednej rewizji i w tej kolejności:

1. `DELETE FROM tracked_events WHERE tracking_ended_at IS NOT NULL` — kaskady zabierają
   rynki, wyniki, próbki i zakresy.
2. `ALTER TABLE tracked_events DROP COLUMN tracking_ended_at`.

Odwrotnie się nie da: po zdjęciu kolumny nie ma po czym poznać, które wiersze usunąć.
`downgrade` przywraca kolumnę jako nullowalną i nie przywraca danych — nie ma skąd.

Wdrożenie zwykłe: moduł migruje własną bazę we własnym lifespanie pod swoją blokadą, bez
kroku operatora. Kolejność obraz-vs-ustawienia nie ma tu zastosowania, bo nic w `infra/` się
nie zmienia.

## Open Questions

- Czy sufit obserwacji powinien wzrosnąć, skoro model nie robi już sobie miejsca sam. Do
  rozstrzygnięcia po pierwszej odmowie, którą operator faktycznie zobaczy — dziś nie wiadomo,
  jak często się w niego uderza.
