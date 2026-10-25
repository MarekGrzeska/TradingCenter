## Context

Rozmowa dostaje dostawcę w `workbench/app.py` (`AgentProvider(conversation_settings)`), a tura woła go przez protokół
`ModelProvider.stream(...)` z `tc_openai`, dostając strumień `TextDelta`, `ToolCallRequest` i `UsageReport`. Numer
wywołania w turze to długość `rounds`. Symulacja pakietu YouTube jest precedensem: wybór ustawieniem, odmowa w
`model_validator` przy `DATABASE_USER`. Analiza wariantów: `docs/playwright-e2e-propozycja.html`, sekcja 05.

## Goals / Non-Goals

**Goals:** deterministyczna tura z prawdziwymi narzędziami; jeden statyczny plik scenariusza na cały zestaw E2E; reguła
bezpieczeństwa w konfiguracji, nie w dyscyplinie.

**Non-Goals:** symulacja zespołów; nagrywanie i odtwarzanie prawdziwych odpowiedzi; atrapa API OpenAI.

## Decisions

**Dostawca w procesie, nie atrapa API pod `OPENAI_BASE_URL`.** Atrapa nie zmieniłaby kodu, ale musiałaby odtwarzać strumień
Responses API, który zmienia się z wersjami SDK, i testowałaby parsowanie cudzej biblioteki. Dostawca w procesie ma kształt
`tests/teams/scripted_provider.py`, który już istnieje dla testów.

**Ustawienia w `workbench/config.py`, przekazane do `agent.config.Settings`.** Tak przechodzą dziś wszystkie ustawienia
rozmowy (`for_conversation()`); odmowa przy `DATABASE_USER` stoi tam, gdzie widać oba ustawienia naraz.
`AGENT_OPENAI_API_KEY` zostaje wymagany także przy `sim`: zmiana jednej reguły zamiast dwóch, a stos E2E i tak podaje atrapę.

**Scenariusz jako JSON z regułami `when` → `rounds`.** Wywołanie numer *n* w turze to `rounds[n]`; to ten sam licznik, który
tura już przekazuje. Podstawienie `{nazwa}` z nazwanych grup pozwala jednemu plikowi obsłużyć strategię o dowolnym numerze,
bez zapisywania scenariusza w trakcie testu i bez trasy do jego zmiany. Plik czytany raz przy starcie i sprawdzany wtedy:
błąd w scenariuszu ma być odmową startu, nie zagadką w trzecim teście.

**Ścieżka pliku względem katalogu, z którego proces startuje.** Stos E2E startuje workbench z `modules/terminal/e2e`, więc
`AGENT_SIM_SCENARIO=agent-scenario.json` wskazuje plik obok `workbench.env`.

## Risks / Trade-offs

- [Scenariusz rozjedzie się z narzędziami, gdy zmieni się ich schemat] → narzędzie odmówi tak jak modelowi, a test E2E
  pokaże odmowę w transkrypcie; scenariusz poprawia się w jednym pliku.
- [Ktoś ustawi `sim` lokalnie i zapomni] → rozmowa mówi wtedy tekstem scenariusza, co widać od pierwszej tury; na
  wdrożeniu start jest odmówiony.
