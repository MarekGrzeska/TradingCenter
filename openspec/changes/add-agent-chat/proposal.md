## Why

W terminalu wisi panel czatu, za którym nie ma niczego — odpowiedzi są zaszyte w
`agentChatStore.ts`, a plakietka „mockup" mówi operatorowi, że to makieta. Układ został
przyjęty (PR #70), więc pytanie o kształt jest zamknięte i zostaje pytanie o treść:
operator chce rozmawiać z modelem nad tym, co ma na ekranie, wracać do wcześniejszych
rozmów i widzieć, ile go ta rozmowa kosztowała — zanim rachunek przyjdzie z Azure, a nie
po fakcie.

Zużycie liczone od pierwszego dnia, nie dołożone później: koszt wywołania da się
odtworzyć tylko w chwili, gdy się je wykonuje, bo cennik modeli zmienia się szybciej niż
transkrypty się starzeją (Luna staniała o 80% 30 lipca 2026, dwanaście dni przed tym
zapisem).

## What Changes

- Nowy moduł `modules/agent` — Python, FastAPI, port 8030, własne zależności, testy,
  migracje i baza. Graf rozmowy prowadzi LangGraph, model liczy Azure OpenAI.
- Trzy modele do wyboru w oknie agenta: `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol` —
  trzy różne modele jednej generacji, rosnące kosztem i możliwościami. Moduł publikuje je
  jako katalog; terminal buduje z niego wybierak i nie zna ich z nazwy.
- Sesje i wiadomości trwają w bazie. Operator wybiera rozmowę z historii albo zaczyna
  nową; zamknięcie przeglądarki nie kasuje transkryptu.
- Odpowiedź przychodzi strumieniem (SSE), a nie jednym blokiem po kilkunastu sekundach.
- Każde wywołanie modelu zapisuje tokeny i koszt, ze stawką **przepisaną na wiersz w
  chwili zapisu** — koszt historyczny nie zmienia się, gdy zmienia się cennik.
- Nowa zakładka terminala **Agents cost**: zużycie i koszt w podziale na model, sesję i
  czas.
- Jeden standardowy prompt systemowy agenta terminala tradingowego, wersjonowany w kodzie
  i oznaczany przy sesji — o transkrypcie da się powiedzieć, którym promptem odpowiadał.
- Infrastruktura: `azurerm_cognitive_account` (kind OpenAI) z trzema deploymentami, czwarta
  aplikacja na istniejącym planie App Service, druga baza logiczna na istniejącym serwerze
  PostgreSQL, dostęp do modeli przez tożsamość zarządzaną — bez klucza do rotacji.
- CI dostaje czwarty job i czwarty workflow wdrożeniowy; skrypty `dev.sh`/`dev.ps1`
  uruchamiają moduł w kolejności zależności.

Poza zakresem, świadomie: agent nie ma **żadnych narzędzi** — nie sięga po świece,
wskaźniki ani pozycje. To pionowy plaster, na którym kolejne funkcje osiądą przyrostowo;
graf ma na nie zostawić miejsce, nie zajmować go z góry.

## Capabilities

### New Capabilities

- `agent-chat`: sesja rozmowy i jej transkrypt — powstawanie, trwanie, kolejność, prompt
  systemowy, oraz to, że odpowiedź płynie strumieniem i co się dzieje, gdy strumień pęka.
- `agent-models`: katalog modeli, wybór modelu dla sesji i odmowa wobec modelu, którego
  moduł nie zna.
- `agent-usage`: pomiar zużycia każdego wywołania i koszt przypisany do niego w chwili
  zapisu; odczyt zagregowany dla zakładki kosztów.
- `agent-database-connection`: na jakich warunkach moduł łączy się ze swoją bazą — tryb
  tożsamości wobec bazy zdalnej, pętla zwrotna bez niej.
- `agent-browser-access`: kto może rozmawiać z agentem — tożsamość wołającego, dostęp z
  przeglądarki i uwierzytelnienie strumienia, którego nagłówkiem opatrzyć się nie da.
- `terminal-agent-chat`: panel agenta w terminalu — lista rozmów, nowa rozmowa, wybór
  modelu, strumień w dymku.
- `terminal-agent-cost`: zakładka **Agents cost** — co operator widzi o zużyciu i koszcie.

### Modified Capabilities

Żadnych. Rejestr zakładek terminala jest otwarty (`terminal-shell`, „Rejestr zakładek jest
otwarty"), więc czwarta zakładka nie zmienia jego wymagania; panel agenta wisi obok
outletu, nie w nim, i to jest wymaganie nowej zdolności, nie zmiana starej.

## Impact

**Nowy kod**: `modules/agent/` w całości — `agent/` (pakiet), `tests/`, `migrations/`,
`pyproject.toml`, `Dockerfile`, `README.md`, `.env.example`. Zależności: `langgraph`,
`langchain-openai`, `fastapi`, `sqlalchemy`, `alembic`, `azure-identity`.

**Terminal**: `src/agent/` (istniejąca makieta przestaje nią być), nowy widok kosztów,
`src/data/config.ts` (`VITE_AGENT_HTTP`), `vite.config.ts` (proxy `/agent-api`),
`src/app/tabs.ts`.

**Infrastruktura**: `infra/` — nowy plik na Azure OpenAI, zmiany w `app-service.tf`,
`database.tf`, `entra.tf`, `variables.tf`, `outputs.tf`. Wersje modeli nie są potwierdzone
i wchodzą jako zmienne — operator sprawdza je `az cognitiveservices account list-models`
przed `apply`. Apply robi operator, nie CI.

**Wspólne**: `compose.yaml` (druga baza lokalna), `scripts/dev.sh`, `scripts/dev.ps1`,
`.github/workflows/checks.yml`, nowy `.github/workflows/deploy-agent.yml`, `CLAUDE.md`,
`README.md`, `docs/architecture.md`.

**Czego nie ruszamy**: `market-data` i `capital-gateway` — ani linijki. Agent nie importuje
z nich nic i na razie nawet ich nie woła.

**Koszt bieżący**: pierwszy element platformy poza darmowym grantem. Azure OpenAI płaci się
za token; plan B1 i serwer PostgreSQL są już opłacone i czwarta aplikacja ich nie zmienia,
ale jeden worker obsługuje teraz o jedną aplikację więcej.
