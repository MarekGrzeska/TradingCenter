## Why

Zespół wykonujący strategię z dokumentu to dziś trzy agenty modelu, które przepisują procedurę z prozy. 9 listopada
od zamknięcia świecy sygnałowej do zlecenia minęło 98 s: 63 s czekania na harmonogram i około 33 s myślenia modeli,
przy około 2 s pracy samych narzędzi. Na 55 historycznych wejściach strategii 5 takie opóźnienie nie zjada przewagi
systematycznie, ale rozjeżdża wykonanie z backtestem o około 24 pkt na transakcję przy średnim wyniku około 29 pkt
(`docs/zespoly-kroki-deterministyczne.html`). Prompt wykonawcy ma 4 564 znaki zakazów dopisanych po wpadkach, a
rozmiar pozycji (dokument 20%, prompt 35%) istnieje tylko w prozie. Mechanikę zlecenia trzeba przenieść do kodu, a
modelowi zostawić to, w czym jest dobry: opowiedzieć operatorowi, co się stało.

## What Changes

- Definicja rewizji niesie obok `agents` listę **kroków** (`steps`). Krok to węzeł tego samego grafu (te same
  krawędzie, kolejność, ślad, limity i harmonogramy), który nie woła modelu. Wykonuje **przepis** z zamkniętego
  katalogu w kodzie modułu, sparametryzowany w rewizji. Zespół może być mieszany: kroki i agenci w jednym grafie.
- Pierwszy przepis, `strategy_execute`, prowadzi własną pozycję zespołu za pozycją silnika strategii (`strategy_signal`):
  - wchodzi tylko na świeżym `enter`;
  - zamyka własną pozycję przy `exit` albo gdy silnik nie ma pozycji, więc wyjście o 14:00 jest tym samym przepisem;
  - nie nadrabia spóźnionych wejść i nie odwraca pozycji;
  - jedną próbę na świecę sygnałową gwarantuje klucz w bazie, a nie notatka w pamięci.
- Parametry, o które pytał operator, są w rewizji:
  - rozmiar domyślnie z dokumentu strategii, z jawnym nadpisaniem w kroku, które widać w terminalu;
  - opcjonalne `max_bar_age_seconds` (puste oznacza brak granicy);
  - czas czekania na świecę w archiwum.
- Wynik kroku to JSON z decyzją, rozmiarem, zleceniem, znacznikami czasu i poślizgiem względem otwarcia minuty
  przyjętego przez backtest. Następnik dostaje go jako wypowiedź poprzednika.
- Agent może nieść **powiadomienie zapasowe**: gdy jego model zawiedzie albo zatrzyma go granica kosztu, przebieg sam
  wysyła na Telegram stały tekst złożony ze streszczeń kroków. Kroki nie płacą za model, więc wyczerpana granica kosztu
  nie zatrzymuje kroków, tylko agentów.
- `tc-team-tools` (MCP, także z Claude Code przez Telegram):
  - zakłada i poprawia zespoły z krokami;
  - pokazuje katalog przepisów;
  - ustawia konto demo i granice handlowe zespołu.
  Przełączenie zespołu na konto realne zostaje czynnością w terminalu.
- Terminal pokazuje kroki na obrazie zespołu, edytuje ich parametry i powiadomienie zapasowe agenta, a w przebiegu
  pokazuje stan i wynik kroku.
- Żaden istniejący zespół się nie zmienia: rewizja bez `steps` czyta się i biegnie jak dziś. Teamy 8 i 11 zostają
  nietknięte. Pierwszy zespół z krokiem operator zakłada i testuje sam, na demo.

Poza zakresem: zegar zespołów budzący się na termin zamiast co 15 s, wyzwalacz „świeca zamknięta” z archiwum, przepisy
dla zleceń z limitem albo stopem, ogólny język potoków narzędzi.

## Capabilities

### New Capabilities
- `teams-steps`:
  - krok jako węzeł grafu zespołu, jego definicja i walidacja przy zapisie;
  - wykonanie przez plan narzędzi przebiegu;
  - przepis `strategy_execute`, klucz jednej próby i wynik kroku;
  - powiadomienie zapasowe agenta.

### Modified Capabilities
- `teams-usage`: wyczerpana dobowa granica kosztu nie odmawia przebiegu rewizji z krokami. Odmawia jej agentom.
- `workbench-team-tools`: zestaw zakłada i poprawia kroki, pokazuje katalog przepisów i ustawia konto demo z granicami.
- `terminal-teams`: kroki na obrazie zespołu, w edytorze i w przebiegu.

## Impact

- Kod `modules/workbench/teams`:
  - `contract.py`: `StepDefinition`, parametry przepisów, `fallback_notice` agenta;
  - `validation.py`;
  - `runner/`: węzeł kroku, wspólna ścieżka wywołań ze śladem i wierszem zlecenia, przepis, powiadomienie zapasowe;
  - `runner/starter.py`: granica kosztu wobec kroków;
  - `store/` i migracja łańcucha `teams`: klucz próby w `trades`.
- Kod `modules/workbench/teams_tools`: `catalogue.py` i nowy odczyt katalogu przepisów, sufit powierzchni narzędzi.
- Kod `modules/terminal`: edytor i widok przebiegu zespołu.
- Kontrakty: definicja rewizji i wynik kroku w kontrakcie zespołów, wygenerowany kontrakt terminala (`contract-sync`).
  Zmiana addytywna: `steps` domyślnie puste.
- Bez zmian w `strategies` („research only, never an order” zostaje), w `trading-mcp`, w bramach i we wdrożeniu.
- `review.md` zostanie napisany po zadaniach, bo krok składa zlecenia na koncie, także realnym.
