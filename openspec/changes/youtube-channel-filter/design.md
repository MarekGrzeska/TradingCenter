## Context

Krok `discover` pętli pobiera 15 najnowszych filmów każdego aktywnego kanału i zapisuje je od razu w `videos` jako
`discovered` — od tego zapisu zaczyna się transkrypcja Gemini, najdroższy krok. Źródło zwraca już opis filmu (przycięty
do 1000 znaków) w tym samym wywołaniu `videos.list`, które daje długość. Tematy mają przesiew po metadanych
(`screening.py`): jedno wywołanie modelu na partię, ścisły schemat, tytuł i opis oznaczone jako dane obce, tokeny liczone
do `DAILY_TOKEN_LIMIT`. Stan `skipped` jest martwy — `drop_unwanted` kasuje takie wiersze.

## Goals / Non-Goals

**Goals:** ocena przed zapłatą za transkrypcję; każdy film oceniany najwyżej raz; zero dodatkowych jednostek YouTube.

**Non-Goals:** ponowna ocena po zmianie filtra; wspólny filtr dla wielu kanałów; filtr na tematach.

## Decisions

**1. Gdy oceny nie da się zrobić, film czeka — nie jest zapisywany.** Alternatywą było przepuszczenie bez oceny (wzorem
kandydatów `unscreened`). Kandydat nieoceniony nic nie kosztuje, bo tylko leży na liście; film kanału nieoceniony szedłby
prosto do Gemini, czyli wydawałby to, przed czym filtr ma chronić. Druga alternatywa — zapis w stanie „czeka na ocenę” —
dodaje stan i zapytanie kolejki dla sytuacji, którą lista 15 najnowszych filmów obsługuje sama: nieznany film wróci
w następnym przebiegu. Koszt: kanał publikujący ponad 15 filmów między udanymi ocenami zgubi najstarsze (zob. Risks).
Czekanie ma granicę dla odpowiedzi, za które zapłacono (odmowa, schemat, brak werdyktu): po trzech film trafia do
`filtered_out` z powodem „nie udało się ocenić” — wzorem `READING_MAX_FAILURES`. Licznik jest w pamięci procesu, bo
nieoceniony film nie ma wiersza; restart kosztuje najwyżej kilka odpowiedzi więcej. Transmisja w toku i film bez długości
czekają bez pytania modelu, bo stan `filtered_out` zamroziłby ich `live_status` i „Analizuj mimo to” nie miałoby czego
transkrybować.

**2. Odrzucenie to stan filmu w `videos`, nie osobna tabela ani kandydat.** Wiersz w `videos` sprawia, że `already_known`
i `upsert_films` same pilnują „oceniany raz”, film nie staje się też kandydatem tematu, a „Analizuj mimo to” to przejście
stanu tego samego wiersza. Kandydaci odpadają, bo z definicji pochodzą spoza obserwowanych kanałów
(`settled_channels`) i mają własne decyzje. Powód leży w istniejącym `skip_reason`; nowy stan `filtered_out` dostaje
własny CHECK „powód obecny”. Nowy stan, a nie `skipped`, bo ten kasuje `drop_unwanted`.

**3. Jeden screener, dwie ramki.** `screening.py` dostaje drugą ramkę systemową („kryteria operatora dla kanału”) obok
tematowej; schemat odpowiedzi, parsowanie (`verdicts_from`) i liczenie tokenów zostają wspólne. Osobny moduł powieliłby
obronę przed prompt injection, a ta ma być jedna. Filtr idzie w wiadomości użytkownika jako kryteria, metadane jako dane
obce — tak jak fraza tematu.

**4. Agent ustawia filtr tylko przy obserwowaniu nowego kanału.** Decyzja operatora: agent może podać filtr w
`follow_channel`. Zmiana filtra kanału już na liście zostaje w REST, tak jak zmiana jego promptu — narzędzie dla kanału
już obserwowanego niczego nie zmienia, i tak zostaje.

**5. „Analizuj mimo to” przez `analyse_film`.** `filtered_out` dołącza do stanów, w których film wskazany ręcznie jest
przetwarzany; przejście ustawia `discovered`, czyści powód, dopisuje `manual` do `origins` i — gdy podano — prompt. Film
kończy jako `quiet`, jak każdy film wskazany ręcznie.

## Risks / Trade-offs

- [Kanał z >15 filmami między udanymi ocenami gubi najstarsze] → dzienny limit tokenów wyczerpuje się rzadko, a
  `GET /state` mówi, że filmy kanałów z filtrem czekają; README to opisuje.
- [Model myli się w ocenie] → odrzucone filmy są widoczne z powodem i jednym kliknięciem przetwarzane.
- [Filtr napisany przez agenta niesie cudze instrukcje] → filtr steruje tylko werdyktem „przetwórz / pomiń” dla filmów
  tego kanału; nie ma narzędzi ani historii. Najgorszy przypadek to przepuszczony lub pominięty film, widoczny na liście.
- [Ocena dokłada wywołanie modelu na kanał] → tylko gdy są nieznane filmy, zwykle 0–2 na przebieg.

## Migration Plan

Migracja `0006`: kolumna `channels.filter text NULL` z CHECK długości, `filtered_out` w `videos_state_is_known`,
CHECK powodu. Kanały dostają `NULL`, więc zachowanie się nie zmienia. Wykonuje się sama przy starcie; `downgrade`
przestawia `filtered_out` na usunięcie wierszy (filmy wrócą jako nowe przy następnym przebiegu) i usuwa kolumnę.
