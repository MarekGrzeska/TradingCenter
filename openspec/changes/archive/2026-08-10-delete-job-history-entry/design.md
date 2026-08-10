## Context

Zmiana idzie przez dwa moduły i przez wygenerowany kontrakt między nimi, więc jest tu co
rozstrzygnąć przed pisaniem kodu. Motywacja: `proposal.md`, sekcja Why. Wymagania:
`specs/market-data-jobs/spec.md` i `specs/terminal-collection-history/spec.md`.

Stan, który kształtuje podejście:

- `collection_job_chunks.job_id` ma klucz obcy **bez** `ON DELETE CASCADE`
  (`migrations/versions/0005_collection_jobs.py`), więc usunięcie zlecenia bez usunięcia
  kawałków zakończy się błędem bazy.
- `store.py` jest jedynymi drzwiami do obu tabel — tylko stamtąd wychodzi SQL ich dotyczący.
- Runner przejmuje pracę zapytaniem `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP
  LOCKED)`, w osobnym połączeniu i w dowolnym momencie.
- Terminal ma `http.send` obok `http.json`, więc odpowiedź bez treści nie wymaga nowego
  narzędzia w warstwie HTTP.
- `ConfirmDialog` zadaje **jedno** pytanie i ma **jedną** akcję potwierdzającą; dialog
  zlecenia już z niego korzysta w dwóch wariantach (ponowienie albo samo zamknięcie).

## Goals / Non-Goals

**Goals:**

- Usunięcie wpisu historii bez ruszania świec, w jednej transakcji, odporne na runnera
  pracującego równolegle.
- Odmowa czytelna i odróżnialna: „nie ma czego usuwać" ≠ „nie teraz".
- Droga w terminalu tam, gdzie zlecenie widać jako całość, bez rozszerzania wspólnego
  `ConfirmDialog`.

**Non-Goals:**

- Usuwanie hurtem (wszystkie zakończone, starsze niż data). Jeden wpis na raz; kryteria
  hurtu to osobna decyzja i osobne wymaganie.
- Usuwanie wpisów o skasowaniu danych pary. To inny rodzaj wpisu i inna rozmowa.
- Cofanie usunięcia. Nie ma kosza; potwierdzenie jest całym zabezpieczeniem.
- Automatyczne przycinanie historii po czasie.

## Decisions

### `DELETE /jobs/{job_id}`, odpowiedź 204 bez treści

Kształt idzie za `DELETE /pairs/{symbol}` w tym samym module, ale bez ciała odpowiedzi:
tam odpowiedzią jest `PairDeletionOut`, bo skasowanie danych **jest** zdarzeniem historii
i wraca z liczbą usuniętych świec. Tutaj nie ma czego pokazać — wymaganie mówi wprost, że
usunięcie nie zostawia po sobie wpisu, a odesłanie usuniętego zlecenia zaprasza terminal
do wyrenderowania czegoś, czego już nie ma.

Odrzucone: `200` z `JobOut` usuniętego zlecenia. Kusi, bo daje się z niego policzyć pary
i kawałki, ale te liczby terminal ma już na ekranie z wierszy, z których zbudował dialog.

Statusy: `404` dla zlecenia nieistniejącego, `409` dla zlecenia z pracą w toku — te same
dwa, którymi `POST /jobs/{job_id}/retry` odpowiada dziś na `UnknownJob` i `NothingToRetry`,
więc mapowanie po stronie terminala (`not-found`, `refused`) już istnieje i nic nowego nie
uczy.

Nowe ciało odpowiedzi nie powstaje, ale **ścieżka** w dokumencie OpenAPI tak, a
`contract.generated.ts` opisuje ścieżki — więc `pnpm contract:generate` jest obowiązkowe
(CLAUDE.md, „A new field on market-data's wire", przystanek 3).

### Kawałki usuwa jawnie ta sama transakcja, nie `ON DELETE CASCADE`

`DELETE FROM collection_job_chunks WHERE job_id = $1`, potem `DELETE FROM collection_jobs
WHERE id = $1`, obie w `conn.transaction()`.

Odrzucone: migracja zmieniająca klucz obcy na kaskadowy. Kaskada jest właściwością
schematu, którą widać dopiero w migracji sprzed roku, i sprawia, że usunięcie zlecenia
staje się ciche — a to jedyne miejsce w module, które ma prawo usuwać kawałki. Jawny
`DELETE` w `store.py` zostawia tę wiedzę tam, gdzie mieszka reszta SQL-a tych dwóch tabel,
i nie wymaga migracji.

### Odmowa dla pracy w toku sprawdzana pod blokadą wierszy

Warunek: zlecenie ma choć jeden kawałek w stanie `pending` albo `running`.

Sprawdzenie i usunięcie idą w jednej transakcji, a kawałki zlecenia są w niej wybrane
przez `SELECT ... FOR UPDATE`. To domyka wyścig, którego sam odczyt nie domyka: runner
przejmuje kawałek zapytaniem z `FOR UPDATE SKIP LOCKED`, więc kawałek zablokowany przez
naszą transakcję zostanie przez niego **pominięty**, a nie przejęty w międzyczasie. Bez
blokady sekwencja „sprawdziliśmy, że nic nie czeka → runner przejmuje → usuwamy" kończy
się kawałkiem `running`, którego zlecenia już nie ma, i błędem w runnerze przy zapisie
wyniku.

`pending` liczy się na równi z `running` z tego samego powodu: kawałek oczekujący to
kawałek, który runner przejmie za chwilę.

Odrzucone: usuwanie zlecenia w toku po uprzednim ustawieniu jego kawałków na
`interrupted`. Wygodne, ale to już nie jest usunięcie zapisu — to zatrzymanie pracy pod
nazwą sprzątania historii, a zatrzymywanie zleceń jest osobną zdolnością, której moduł
dziś nie ma.

### Nowy wyjątek `JobStillRunning` obok `UnknownJob`

`store.py` sygnalizuje odmowy wyjątkami, a router zamienia je na statusy — tak działa
`retry_job`. Usunięcie idzie tą samą drogą: `UnknownJob` (już istnieje) → 404,
`JobStillRunning` (nowy) → 409. Bez zwracania `bool`/`None`, które router musiałby
tłumaczyć na powód po własnym domyśle.

### W terminalu: druga akcja to drugi dialog, nie drugi przycisk w `ConfirmDialog`

Dialog zlecenia dostaje przycisk „Remove from history" w swojej treści, a wybranie go
podmienia dialog na drugi — pytanie o zgodę, `tone="danger"`, z treścią mówiącą, ilu par
i ilu kawałków dotyczy oraz że świece zostają.

Odrzucone: dodanie `ConfirmDialog`-owi drugiej akcji potwierdzającej. Komponent jest
opisany jako „jedno pytanie, jedna odpowiedź" i używa go cały terminal; dialog z dwoma
przyciskami, z których każdy robi coś nieodwracalnego, to dokładnie ta sytuacja, w której
operator klika nie ten. Rozdzielenie na dwa kroki nic nie kosztuje — `ConfirmDialog`
zostaje nietknięty.

Przy zleceniu z pracą w toku przycisk się nie pojawia, a dialog mówi dlaczego. Stan
„w toku" terminal zna z `row.status === "running"`, bez pytania archiwum.

Po udanym usunięciu: `onChanged()` (to samo, co po ponowieniu) i zamknięcie dialogu.
Lista przeładowuje się z archiwum, więc wiersze znikają bez odświeżania strony, a
dziesięciosekundowe odpytywanie nie ma szansy przywrócić ich na moment.

## Risks / Trade-offs

- **Operator usuwa wpis w przekonaniu, że kasuje dane** → potwierdzenie mówi wprost, że
  świece zostają; to jedyne zdanie, które odróżnia tę operację od skasowania pary, i
  dlatego jest wymaganiem, a nie detalem widoku.
- **Usunięcie zlecenia zaciera, skąd wzięły się świece w archiwum** → przyjęte świadomie.
  Pokrycie pary pozostaje i to ono odpowiada na pytanie „co archiwum ma"; historia
  zlecenia odpowiada na „co było robione", i to ona jest tu przedmiotem decyzji operatora.
- **Wyścig z runnerem przy usuwaniu** → domknięty blokadą wierszy opisaną wyżej; test
  `-m db` MUST obejmować przypadek zlecenia z kawałkiem `pending`.
- **Zapomniane `pnpm contract:generate`** → `contract:check` w CI, uruchamiany przed
  testami terminala; job terminala rusza także dla diffu dotykającego wyłącznie Pythona.
