## Why

Testy end-to-end terminalu (`pnpm e2e`, fazy 0–1 z `docs/playwright-e2e-propozycja.html`) obejmują dziś zakładki
Strategies i Backtests, ale nie rozmowę: każda tura woła OpenAI, a stos E2E celowo kieruje to wywołanie donikąd. Obieg
agent → narzędzie → edytor (`draft_strategy`, nowa strategia z czatu, zmiana modelu) nie ma więc żadnego testu, który
przechodzi przez prawdziwy workbench i terminal. Potrzebny jest model zastępczy, który odpowiada przewidywalnie, nie
otwiera połączenia i nie może trafić na wdrożenie.

## What Changes

- Nowe ustawienie `AGENT_PROVIDER`: `openai` (domyślne, jak dziś) albo `sim`. Przy `sim` rozmowa dostaje dostawcę, który
  odtwarza scenariusz z pliku wskazanego w `AGENT_SIM_SCENARIO`, zamiast wołać OpenAI.
- `sim` jest odmawiane przy starcie, gdy ustawiono `DATABASE_USER`, tak jak symulacja pakietu YouTube: to wdrożenie, a
  rozmowa na wdrożeniu nie może odpowiadać ze scenariusza.
- Scenariusz dopasowuje ostatnią wiadomość operatora wyrażeniem regularnym i odtwarza kolejne wywołania modelu: prośby o
  narzędzia albo tekst. Nazwane grupy wyrażenia trafiają do argumentów narzędzi. Plik niepoprawny to odmowa startu;
  wiadomość bez pasującej reguły dostaje odpowiedź, która mówi, że scenariusz jej nie zna.
- Narzędzia wykonują się naprawdę; symulowany jest tylko wybór, co powiedzieć. Zużycie każdego wywołania jest zapisane
  jako zero tokenów, bo nic nie zostało zużyte.
- Stos E2E włącza `sim` z własnym scenariuszem i dostaje testy AG-01…03.

## Capabilities

### New Capabilities
- `agent-simulated-model`: model zastępczy rozmowy dla testów lokalnych — wybór, odmowa poza trybem lokalnym,
  scenariusz i jego zachowanie.

### Modified Capabilities
Brak. `agent-usage` się nie zmienia: wiersz zużycia powstaje dla każdego wywołania jak dotąd, z liczbami, które dostawca
podał (tu zero).

## Impact

- `modules/workbench`: `workbench/config.py` (dwa ustawienia i odmowa), `agent/config.py`, nowy `agent/simulation.py`,
  wybór dostawcy w `workbench/app.py`, `.env.example`.
- `modules/terminal/e2e`: `workbench.env` (`AGENT_PROVIDER=sim`), `agent-scenario.json`, testy AG-01…03.
- Zespoły (`teams`) bez zmian: ich dostawca zostaje przy OpenAI do czasu, aż E2E obejmie zespoły.
- `review.md` pominięty: zmiana nie otwiera nowej granicy; jej regułę bezpieczeństwa (odmowa przy `DATABASE_USER`) pilnuje
  test konfiguracji, jak przy YouTube.
