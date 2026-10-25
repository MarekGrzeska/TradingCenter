## Why

Na produkcji 25.10.2026 agent w czacie strategii odpowiadał JSON-em dokumentu, a edytor i streszczenie zostawały bez
zmian: zakładka wczytuje tylko zapisane rewizje. Operator chce widzieć w edytorze każdą zmianę agenta od razu, jeszcze
przed zapisem, a rewizję tworzyć dopiero wtedy, gdy uzna zmianę za gotową. Chce też czytać nazwę, hipotezę i założenia
strategii po polsku, a w streszczeniu widzieć, czym jest zmienna, a nie samą jej nazwę.

## What Changes

- **Szkic strategii.** Nowe narzędzie `draft_strategy` sprawdza dokument tak jak walidacja i kładzie go do edytora
  zakładki jako niezapisany tekst. Nie tworzy rewizji i nie zmienia licznika prób. Na jedną strategię (albo na nową,
  jeszcze niezapisaną) przypada jeden szkic, zastępowany kolejnym.
- Agent pracuje na tekście operatora: tura i tak niesie niezapisany tekst edytora, więc szkic agenta go zawiera.
  Edytor po turze po prostu pokazuje szkic.
- `save_strategy` zostaje do zapisu, gdy operator o niego prosi. Zapis rewizji (przez agenta albo operatora) usuwa szkic.
- Pakiet publikuje szkic przez REST: odczyt i usunięcie, dla strategii i dla nowej.
- Opis języka mówi modelowi, że nazwę, hipotezę i założenia pisze po polsku.
- **Streszczenie podstawia zmienne.** Formuła z `let` jest oddana tym, czym jest („EMA(10) przecina od dołu EMA(30)”),
  zamiast nazwą («fast»), której operator musiałby szukać. Lista zmiennych zostaje.

**Poza zakresem:** strumieniowanie szkicu w trakcie tury (edytor odświeża się po turze, jak dziś po zapisie).

## Capabilities

### New Capabilities
Brak.

### Modified Capabilities
- `strategies-tools`: narzędzie `draft_strategy`; opisy narzędzi prowadzą do szkicu i do polskich opisów.
- `strategies-api`: trasy szkicu.
- `terminal-strategies`: edytor po turze pokazuje szkic agenta.
- `strategies-documents`: streszczenie oddaje zmienną jej formułą.
- `agent-chat`: kontekst otwartej strategii mówi modelowi, że zmiany idą do edytora szkicem.

## Impact

- `modules/workbench/strategies`: migracja `0004` (`strategy_drafts`), `drafts.py`, narzędzie, trasy, usuwanie szkicu
  przy zapisie rewizji, kontrakt.
- `modules/workbench/agent/models.py`: zdanie kontekstu strategii.
- `modules/terminal`: wczytanie szkicu po turze i przy otwarciu, usunięcie przy „Porzuć zmiany” i „Nowa…”, kontrakt.
- `design.md` pominięty: jedna decyzja (szkic w tabeli pakietu, nie w narzędziach terminala) mieści się tutaj. Zakładka
  nie czyta wywołań narzędzi agenta, więc szkic musi być stanem pakietu, który zakładka odczytuje przez REST.
- `review.md` po zadaniach.
