## Why

Agent z `add-agent-chat` rozmawia o rynku, nie widząc go: nie ma ani jednego narzędzia i
odpowiada wyłącznie z tego, co model pamięta z treningu. Operator, pytając o US100,
dostaje zdanie wiarygodnie brzmiące i niezwiązane z archiwum, które stoi obok, na porcie
8020.

Nie wystarczy jednak podać modelowi kontraktu `market-data` takim, jaki jest. Ten
kontrakt jest zbudowany dla wykresu: doba świec MINUTE to 1440 obiektów JSON, dziesiątki
tysięcy tokenów za odpowiedź, która brzmi „rynek stoi w miejscu". Model nie ma jak
wiedzieć, że to drogo, więc sufit i streszczenie muszą siedzieć po stronie narzędzia.

## What Changes

- Nowy moduł `modules/market-mcp` — Python, serwer MCP nad archiwum, port 8040. Bez bazy,
  bez stanu, bez migracji.
- Dwa transporty z jednego zestawu narzędzi: **streamable http** dla agenta stojącego w
  innym kontenerze i **stdio** dla klienta na biurku operatora.
- Dziesięć narzędzi, **wszystkie czytające**: pary i pokrycie, świece i ich streszczenie,
  katalog wskaźników, obliczenie wskaźników zredukowane do wartości bieżących, poziomy i
  strefy posortowane po odległości od ceny.
- Każda odpowiedź ma sufit i jest streszczana, a odcięcie zawsze zostawia po sobie zdanie
  — nic nie znika po cichu.
- Niepewność archiwum (`uncovered`, `derived`, `settled`) jedzie w treści odpowiedzi jako
  zdanie dla modelu. Pusta seria świec MUST NOT czytać się jak cisza rynku.
- Moduł czyta opublikowany kontrakt `market-data`, nie importuje z niego niczego.
  Commitowany snapshot OpenAPI i test asercji pól bronią przed rozjazdem — ten sam
  mechanizm, którym broni się terminal.
- Do `market-data` idą wyłącznie żądania czytające. Jedyny `POST` to
  `POST /indicators/{symbol}`, które jest obliczeniem, nie zapisem.

Poza zakresem, świadomie: cokolwiek zapisującego. Nie ma `track_pair`, nie ma kasowania
pary, nie ma przełącznika, który by je włączył — przełącznik jest obietnicą, że kiedyś
się go przestawi. Poza zakresem także pozycje i zlecenia z `capital-gateway`, subskrypcja
strumienia oraz podpięcie klienta MCP po stronie agenta: to zmiana w `modules/agent` i
osobna decyzja.

## Capabilities

### New Capabilities

- `market-mcp-tools`: jakie narzędzia moduł publikuje, na jakie pytanie każde odpowiada i
  czego nie publikuje nigdy — łącznie z tym, że żadne nie zmienia stanu.
- `market-mcp-answers`: kształt odpowiedzi — sufity, agregacja, reguła „nic nie znika po
  cichu", niepewność archiwum w treści oraz jeden kształt odmowy dla wszystkich narzędzi.
- `market-mcp-upstream-access`: na jakich warunkach moduł łączy się z `market-data` —
  tryb tożsamości wobec adresu zdalnego, pętla zwrotna bez niej, snapshot kontraktu i
  wyłącznie metody czytające.
- `market-mcp-transport`: dwa transporty, kto może wołać moduł i co się dzieje z żądaniem
  bez tożsamości.

### Modified Capabilities

Żadnych. `market-data` nie jest w tej zmianie dotykane ani jedną linijką — moduł jest jej
konsumentem dokładnie tak, jak terminal, i wszystko, czego potrzebuje, jest już
opublikowane.

## Impact

**Nowy kod**: `modules/market-mcp/` w całości — `market_mcp/` (pakiet), `tests/`,
`contract/market-data.openapi.json`, `scripts/contract.py`, `pyproject.toml`,
`Dockerfile`, `README.md`, `.env.example`. Zależności: `mcp`, `pydantic`, `httpx`,
`azure-identity`.

**Infrastruktura**: `infra/` — piąta aplikacja na istniejącym planie App Service, jej
tożsamość zarządzana i uprawnienie do wołania `market-data`. Plan B1 ma jednego workera i
to jest realny nacisk do zmierzenia po wdrożeniu, nie do przewidzenia teraz. Apply robi
operator, nie CI.

**Wspólne**: `scripts/dev.sh` i `scripts/dev.ps1` (start po `market-data`, przed
agentem), `.github/workflows/checks.yml` (piąty job, wchodzący do filtra także na zmianie
`market_data/contract.py`), nowy `.github/workflows/deploy-market-mcp.yml`, `CLAUDE.md`,
`README.md`, `docs/architecture.md`.

**Czego nie ruszamy**: `market-data`, `capital-gateway`, `terminal` i `agent`.

**Koszt bieżący**: żaden nowy poza planem App Service, który jest już opłacony. Moduł nie
woła modelu i nie dotyka dostawcy — czyta archiwum.
