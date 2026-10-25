## 1. Workbench

- [x] 1.1 `workbench/config.py`: `agent_provider` (`openai` | `sim`), `agent_sim_scenario`; odmowa nieznanej wartości, `sim` bez pliku i `sim` przy `DATABASE_USER`; przekazanie do `agent.config.Settings`
- [x] 1.2 `agent/simulation.py`: odczyt i sprawdzenie scenariusza; dostawca `ModelProvider` odtwarzający `rounds[n]`, z podstawieniem nazwanych grup i zerowym zużyciem
- [x] 1.3 `workbench/app.py`: wybór dostawcy rozmowy według ustawienia
- [x] 1.4 `.env.example`: oba ustawienia z komentarzem o odmowie poza trybem lokalnym
- [x] 1.5 Testy: odmowy konfiguracji (unit); dopasowanie, podstawienie, brak reguły i zły plik (unit); jedna tura przez trasę rozmowy z narzędziem i dwoma wierszami zużycia (`db`)

## 2. E2E

- [x] 2.1 `e2e/workbench.env`: `AGENT_PROVIDER=sim`, `AGENT_SIM_SCENARIO=agent-scenario.json`; `e2e/agent-scenario.json` z regułami dla AG-01…04
- [x] 2.2 `e2e/tests/agent.spec.ts`: AG-01 nowa strategia z czatu, AG-02 szkic do istniejącej i jego porzucenie, AG-03 zmiana modelu się trzyma, AG-04 rewizja agenta przy niezapisanych zmianach operatora
- [x] 2.3 `scripts/tests/test_e2e.py`: stos E2E ma `AGENT_PROVIDER=sim`

## 3. Domknięcie

- [x] 3.1 `uv run pytest` · `ruff` · `pyright` w workbenchu; `pnpm e2e` i `pnpm test` · `lint` · `typecheck` w terminalu
- [x] 3.2 README workbencha (ustawienie), `modules/terminal/e2e/README.md`, sekcja fazy 2 w `docs/playwright-e2e-propozycja.html`
