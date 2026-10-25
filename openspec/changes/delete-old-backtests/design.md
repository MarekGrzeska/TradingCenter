## Context

`runs` trzyma uruchomienia, `run_trades` ich transakcje (klucz obcy na `runs`). Licznik prób strategii nie jest kolumną:
`store._SUMMARY` liczy podzapytaniem uruchomienia strategii w stanie `done`, ze wszystkich rewizji. Cały pakiet jest już
zamknięty przed rolą `viewer` (`tc-entra-auth` wpuszcza go tylko do `GET` pod `/social` i `/polymarket`), więc
nowa trasa nie dopisuje nic do reguł dostępu. Narzędzia pakietu dostaje wyłącznie rozmowa, nigdy zespoły
(`strategies-tools`, „Narzędzia strategii dostaje tylko rozmowa”).

## Goals / Non-Goals

**Goals:** usunięcie uruchomień z ekranu i przez agenta, bez możliwości zmniejszenia licznika prób.

**Non-Goals:** kasowanie strategii albo rewizji; usuwanie uruchomień po kryterium („starsze niż”, „wszystkie nieudane”)
— operator lub agent wskazuje identyfikatory; odzyskiwanie usuniętych. Nie ma kosza ani miękkiego usuwania.

## Decisions

**D1. Licznik przeżywa usunięcie jako kolumna `strategies.deleted_trials`.** Migracja `0006` dodaje
`deleted_trials integer NOT NULL DEFAULT 0`, a licznik w `_SUMMARY` staje się `count(done) + s.deleted_trials`.
Usunięcie, w tej samej transakcji, policzy usuwane uruchomienia w stanie `done` per strategia i dopisze je do kolumny.
*Alternatywy:* (a) miękkie usuwanie (`deleted_at` na `runs`): liczy się samo, ale raporty i transakcje zostają w bazie
na zawsze, czyli nie ma tego, po co operator usuwa, a każde zapytanie o uruchomienia musi pamiętać o filtrze;
(b) licznik maleje: wymazuje ślad prób, czego operator wprost nie chce.

**D2. Usunięcie to jedno `DELETE ... WHERE status NOT IN ('queued','running') RETURNING` w transakcji, po
zablokowaniu wierszy `FOR UPDATE`.** Stan sprawdzany i usuwany pod tą samą blokadą, więc uruchomienie, które kończy się w
tej chwili, jest albo jeszcze „liczone” (odmowa), albo już `done` i trafia do licznika; nie ma okna, w którym znika bez
doliczenia (scenariusz „Wyścig z końcem uruchomienia”). Kolejność: odmowa, gdy któryś numer nie istnieje albo jest w
toku; potem `run_trades`, potem `runs`, potem `deleted_trials`.
*Alternatywa:* usuwać to, co się da, i raportować resztę. Odrzucona: agent dostałby częściowy skutek jednego wywołania,
a operator listę, której nie przewidział; wszystko albo nic daje jedną odpowiedź do zrozumienia.

**D3. Jedna trasa `DELETE /runs?run_id=…`, bez osobnej trasy na pojedyncze.** Powtórzony parametr jak w `GET /runs/compare`,
do 20. Ekran, który usuwa jedno uruchomienie, wysyła jeden numer. Ciało przy `DELETE` bywa gubione przez pośredników,
więc go nie używamy.

**D4. Agent: `delete_backtests(run_ids)` z adnotacją zapisu, ale bez własnej bramki.** Ochroną jest opis
(„tylko na prośbę operatora, nieodwracalne, licznik zostaje”), sufit 20 i to, że usunąć można wyłącznie to, co skończone.
Dodajemy narzędzie do powierzchni liczonej przez sufit znaków; ma zapas (10 367 z 11 500), ale jeśli opis go wyczerpie,
sufit rośnie świadomie w tym samym teście.
*Alternatywa:* potwierdzenie przez drugi krok (`prepare_delete` → `delete`). Odrzucona: to dwa narzędzia do utrzymania za
ochronę, którą operator i tak ma w rozmowie (prosi wprost), a skutek usunięcia jest ograniczony do raportów, których
licznik prób i tak nie zapomni.

**D5. Odmowa przy nieistniejącym uruchomieniu mówi, że mogło zostać usunięte.** Nie ma nagrobków, więc „nie istnieje”
i „usunięte” są nie do odróżnienia; komunikat mówi o obu, żeby agent nie szukał pomyłki w identyfikatorze, który sam
widział w rozmowie wcześniej.

**D6. Ekran: zaznaczenie do usunięcia jest osobne od zaznaczenia do porównania.** Porównanie dotyczy tylko zakończonych,
usuwanie także nieudanych i anulowanych, więc dwa zbiory w jednej tabeli (druga kolumna pól) i dwa przyciski, bez
mieszania warunków włączenia. Potwierdzenie przez istniejący `ConfirmDialog` z liczbą uruchomień i zdaniem o liczniku.
*Alternatywa:* przycisk „Usuń” przy każdym wierszu. Odrzucona: usuwa się zwykle całą kupkę po serii prób, a `Anuluj` już
zajmuje ostatnią komórkę.

## Risks / Trade-offs

- [Licznik prób może urosnąć ponad liczbę uruchomień widocznych na liście.] → To zamierzone; ekran pokazuje licznik jak
  dotąd, a README pakietu mówi, że różnica to usunięte próby.
- [Agent usunie coś, o co operator nie prosił.] → Opis narzędzia, sufit 20 i fakt, że skutek to utrata raportu, który
  można policzyć od nowa tym samym wkładem (ale kosztem kolejnej próby). Nie ma bramki w kodzie; jeśli się to
  pokaże w praktyce, następny krok to osobna zmiana.
- [Usunięcie uruchomienia, które agent trzyma w kontekście.] → Odczyt zwróci odmowę „nie ma, mogło zostać usunięte” (D5).

## Migration Plan

Migracja `0006` stosuje się sama przy starcie pakietu, pod jego blokadą doradczą, i ma `downgrade` usuwający kolumnę.
Istniejące strategie dostają `deleted_trials = 0`, więc licznik po wdrożeniu jest taki jak przed. Wycofanie obrazu bez
cofnięcia migracji jest bezpieczne: stary kod nie zna kolumny i jej nie czyta.
