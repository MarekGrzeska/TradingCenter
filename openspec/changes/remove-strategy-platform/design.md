## Context

Strategia jest dziewiątym pakietem workbencha, montowanym pod `/strategy`, z własną bazą
`strategy` (tabele `parameter_sets`, `watches`, `decisions`, `backtest_runs`,
`strategy_definitions`, `strategy_revisions`), łańcuchem migracji pod blokadą 8080 i pętlą
oceniającą co 60 s. Poza pakietem dotykają jej: zespół (`workbench/app.py` składa jej narzędzia
w źródła lokalne rozmowy i zespołów; zegar wyzwalaczy szuka `pending_setups` po nazwie), droga
do archiwum świec (`workbench/archive_client.py`, jedyny użytkownik), droga do Telegrama
(`workbench/telegram_client.py`, wspólna z archiwum postów i YouTube — zostaje), terminal
(zakładka, kontrakt, scope, proxy) i deploy (compose, `db-init`, kopie zapasowe, sekret).

Mechanizm zespołów jest ogólny: wyzwalacz i przypisanie narzędzia odnoszą się do nazwy, a nie do
strategii, więc usunięcie źródła nie wymaga zmiany kodu zespołów — tylko komentarzy i jednego
testu, który używa atrapy `pending_setups`.

`deploy.sh release` przy niezdrowym wydaniu przywraca **poprzednie obrazy** z **nowym** plikiem
compose i nowym `.env`. Ustawienia workbencha mają `extra="ignore"`, więc nowy obraz toleruje
nadmiarowe `STRATEGY_*`, ale stary obraz bez `STRATEGY_DATABASE_URL` albo bez bazy nie wstanie.

## Goals / Non-Goals

**Goals:**
- Po zmianie w repozytorium, na serwerze i w dev nie ma śladu platformy: kodu, bazy, roli,
  sekretu, zakładki, kontraktu, wymagań.
- Żadnego kroku operatora między merge'em a działającą produkcją; rollback działa na każdym
  etapie.

**Non-Goals:**
- Projekt nowej platformy i rezerwowanie dla niej czegokolwiek.
- Przepisywanie danych innych pakietów (np. definicji zespołów w bazie `teams`).
- Usuwanie datowanych migawek w `docs/` (`przeglad-*`, `stan-projektu-*`) i `docs/archive/`.

## Decisions

**Dwa wydania, nie jedno.** Wydanie A usuwa kod (workbench, terminal, CI, skrypty,
dokumentacja), ale zostawia w compose `STRATEGY_DATABASE_URL`, `STRATEGY_DB_PASSWORD`, wpis w
`db-init` i bazę — nowy obraz je ignoruje, a rollback do starego obrazu wciąż ma czego użyć.
Wydanie B, dopiero po zdrowym A, usuwa bazę, rolę i zmienne. Alternatywa „wszystko naraz”
odpada: nieudane wydanie przywróciłoby obraz, który wymaga bazy usuniętej chwilę wcześniej, i
rollback zakończyłby się drugą awarią.

**Bazę usuwa wdrożenie, idempotentnie.** `ensure-databases.sh` dostaje obok `ensure` funkcję
`retire strategy`: `DROP DATABASE IF EXISTS strategy WITH (FORCE)` i `DROP ROLE IF EXISTS
strategy`, wykonywane przy każdym wdrożeniu. `dev.py` robi to samo z lokalną bazą. Odrzucone:
zostawienie bazy jako sieroty (nowa platforma zastałaby stary `alembic_version` pod tą samą
nazwą, a kopia zapasowa ciągnęłaby martwe dane) i `DROP` ręką operatora (stała reguła: merge
zostawia produkcję gotową bez kroku operatora). Raporty backtestu żyją wyłącznie w
`backtest_runs` — w repozytorium nie ma żadnego pliku z wynikiem — więc usunięcie bazy usuwa je
wszystkie.

**Kopie zapasowe wygasają same.** Wydanie B usuwa `strategy` z list w `backup.sh` i
`backup-check.sh`; zrzuty sprzed niego zostają na komputerze operatora, dopóki nie wypadną z
retencji. To jedyna droga powrotu do starych danych i nie warto jej przyspieszać.

**Otwarta zmiana `the-screen-is-mostly-refusals` jest usuwana, nie archiwizowana.**
Archiwizacja wpisałaby `terminal-strategy` do specyfikacji tylko po to, żeby ta zmiana
natychmiast ją usunęła.

**Dane zespołów zostają nietknięte.** Wyzwalacz na `pending_setups` po zmianie zgłasza „żadne
źródło nie ogłasza tej nazwy”, a zespół z przypisanym narzędziem strategii odmawia startu —
tak, jak już dziś zachowuje się przy każdym brakującym źródle. Zmiana nie pisze do bazy
`teams`; zamiast tego przed wydaniem A sprawdza (odczyt, za zgodą operatora), czy takie wpisy
istnieją, i operator decyduje, czy je usunąć.

**Kolejność względem telegrama.** Gałąź `feat/telegram-terminal` (zmiana
`telegram-bots-from-the-terminal`, inny agent) modyfikuje `strategy/alerts.py`,
`strategy/config.py` i specyfikację `strategy-alerts` oraz rejestruje cel `strategy.setup`.
Ta zmiana wchodzi **po niej**: rebase, usunięcie przerobionych plików razem z resztą, lista
`REMOVED` w delcie `strategy-alerts` odtworzona z głównej specyfikacji po archiwizacji
tamtej, i cel `strategy.setup` usunięty tak, jak tamta zmiana traktuje cel bez producenta.
Odwrotna kolejność kazałaby tamtej zmianie przerabiać pliki, których już nie ma.

## Risks / Trade-offs

- [Usunięcie bazy jest nieodwracalne] → wydanie B dopiero po zdrowym A; ostatni nocny zrzut
  `strategy` potwierdzony na komputerze operatora przed merge'em B.
- [Zespół lub wyzwalacz na produkcji używa narzędzi strategii i po cichu przestaje działać] →
  odczyt bazy `teams` przed wydaniem A; skutek jest głośny (odmowa startu, wpis w historii
  wyzwoleń), nie cichy.
- [Konflikt z gałęzią telegrama w plikach terminala] → `config.ts`, `config.test.ts`,
  `marketData.ts`, `vite.config.ts`, `contract.mjs` i `deploy-vps.yml` są dziś zmienione w
  głównym worktree; rebase po merge'u telegrama, nie równolegle.
- [Martwe odwołania w dokumentacji] → `git grep -i strateg` po wydaniu B ma zwracać tylko
  `docs/archive/`, `openspec/changes/archive/` i datowane migawki w `docs/`.
