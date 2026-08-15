## 1. Baza i kontrakt agenta

- [x] 1.1 `agent/models.py`: model polecenia wykresu — numer kolejny, znacznik czasu,
      sesja, symbol, interwał, lista wskaźników (id, parametry, kolor)
- [x] 1.2 Migracja w `agent/migrations/versions/`: tabela `chart_commands` z numerem
      rosnącym w obrębie modułu i indeksem po numerze
- [x] 1.3 `agent/store.py`: zapis polecenia i odczyt „ostatnie" oraz „nowsze niż N"
- [x] 1.4 Testy magazynu (`-m db`): numer rośnie ponad sesjami, odczyt powtórzony daje to
      samo, odczyt nowszych niż ostatni daje pusto

## 2. Narzędzie lokalne modułu agent

- [x] 2.1 `agent/tools/`: rejestr narzędzi własnych — `ToolDescriptor` z ręcznie
      napisanym `input_schema`, oddzielony od klienta MCP
- [x] 2.2 Narzędzie ustawiające wykres: pola opcjonalne (pominięte = „zostaw jak jest"),
      wskaźniki jako pełny zestaw
- [x] 2.3 Sprawdzenie polecenia przed zapisem: wskaźniki i granice parametrów przeciw
      katalogowi, symbol i interwał przeciw zbieranym parom — oba przez `market-mcp`
- [x] 2.4 Odmowa jako `ToolOutcomeKind.REFUSED` ze zdaniem, co poprawić; polecenie
      zapisywane w całości albo wcale
- [x] 2.5 Bez serwera narzędzi: narzędzie odmawia z powodu „nie mam jak sprawdzić",
      zamiast zapisywać na ślepo
- [x] 2.6 Testy narzędzia: pełny zestaw, sam interwał, nieznany wskaźnik, parametr poza
      zakresem, symbol niezbierany, brak serwera narzędzi

## 3. Pętla tury

- [x] 3.1 `agent/graph.py`: `run_tools` kieruje wywołanie do rejestru własnego albo do
      serwera, po nazwie narzędzia; sufit tury i ślad wspólne
- [x] 3.2 Narzędzia własne dołączane do zestawu ogłaszanego modelowi także wtedy, gdy
      serwera narzędzi nie ma
- [x] 3.3 Ślad wywołania odróżnia narzędzie modułu od narzędzia serwera
- [x] 3.4 Testy tury: model woła narzędzie własne i serwera w jednej turze, sufit liczy
      oba, odmowa narzędzia własnego nie kończy tury

## 4. Migawka wykresu w żądaniu tury

- [x] 4.1 `agent/contract.py`: opcjonalne pole migawki w żądaniu tury (symbol, interwał,
      wskaźniki)
- [x] 4.2 Migawka podana modelowi jako kontekst tury, nie zapisana w transkrypcie ani
      w bazie
- [x] 4.3 Testy: tura z migawką i bez niej, transkrypt bez migawki

## 5. Publikacja poleceń

- [x] 5.1 `agent/contract.py` + router: odczyt ostatniego polecenia i poleceń nowszych
      niż podany numer
- [x] 5.2 Odczyt bez skutków ubocznych — powtórzenie daje ten sam wynik
- [x] 5.3 Testy routera: pusto gdy nic nowego, ostatnie polecenie po przerwie

## 6. Terminal: stosowanie poleceń

- [x] 6.1 `agent/agentApi.ts`: odczyt poleceń nowszych niż zapamiętany numer
- [x] 6.2 Kursor ostatnio zastosowanego polecenia w `localStorage`, obok konfiguracji
      siatki
- [x] 6.3 `gridStore`: zastosowanie polecenia do aktywnego slotu — wskaźniki, symbol,
      interwał — zapisane tak samo jak zmiana ręczna
- [x] 6.4 Polecenie spoza granic slotu (symbol albo interwał niezbierany) pomijane
      z komunikatem, zamiast wykresu bez danych
- [x] 6.5 Testy: zastosowanie do aktywnego slotu, pozostałe sloty nietknięte, to samo
      polecenie nie stosuje się dwa razy, ręczna zmiana po poleceniu zostaje

## 7. Terminal: panel agenta

- [x] 7.1 Odczyt poleceń po zakończonej turze i po wejściu na stronę
- [x] 7.2 Migawka aktywnego slotu wysyłana w żądaniu tury
- [x] 7.3 Komunikat w panelu: wykres został zmieniony przez agenta, i czego dotyczyła
      zmiana
- [x] 7.4 Nieudany odczyt poleceń nie przerywa rozmowy ani nie czyści wykresu
- [x] 7.5 Testy panelu: zmiana widoczna bez odświeżania, polecenie sprzed zamknięcia karty
      stosowane raz, odczyt nieudany zostawia rozmowę i wykres

## 8. Prompt systemowy

- [x] 8.1 Nowa rewizja promptu nazywa narzędzie i mówi, kiedy po nie sięgać (i kiedy nie)
- [ ] 8.2 Ręczne sprawdzenie w rozmowie: „pokaż EMA 200 na godzinie" ustawia wykres

## 9. Domknięcie

- [x] 9.1 `modules/agent`: `uv run pytest`, `uv run pytest -m db`, `ruff check .`, `pyright`
- [x] 9.2 `modules/terminal`: `pnpm lint`, `pnpm typecheck`, `pnpm test`
- [ ] 9.3 `alembic upgrade head` w bazie deweloperskiej — krok ręczny, odnotowany
      w opisie pull requesta dla wdrożenia
- [x] 9.4 `openspec validate add-agent-chart-control --strict`
- [ ] 9.5 Gałąź, commit, pull request
