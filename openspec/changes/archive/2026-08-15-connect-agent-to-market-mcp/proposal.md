## Why

Dwa moduły stoją obok siebie i żaden nie wie o drugim. `market-mcp` publikuje dziesięć
czytających narzędzi nad archiwum — świece, pokrycie, wskaźniki, poziomy — a `agent`
odpowiada wyłącznie z tego, co model pamięta z treningu, i ma to wpisane w prompt
systemowy: „You have no tools". Operator pytający o US100 dostaje zdanie brzmiące
wiarygodnie i niezwiązane z danymi, które leżą dwa porty dalej.

`add-market-data-mcp` wypchnął to połączenie poza swój zakres jednym zdaniem
(„podpięcie klienta MCP po stronie agenta: to zmiana w `modules/agent` i osobna
decyzja"), a `add-agent-chat` zostawił na nie miejsce w grafie rozmowy, świadomie
niewypełnione. To jest ta zmiana.

## What Changes

- `modules/agent` dostaje klienta MCP i pętlę narzędzi. Graf rozmowy przestaje mieć
  jeden węzeł: model może poprosić o narzędzie, dostać wynik i mówić dalej, aż odpowie
  operatorowi.
- Zestaw narzędzi jest **odkrywany**, nie wpisany. Klient pyta `market-mcp` o listę przy
  starcie sesji z serwerem i bierze opisy, jakie zastanie — nowe narzędzie po tamtej
  stronie jest dostępne bez zmiany w tym module i bez commitowanego snapshotu, bo
  protokół MCP opisuje sam siebie. To jedyny kontrakt w tym repozytorium, który nie
  potrzebuje kopii po stronie konsumenta.
- Pętla ma sufit wywołań na turę. Model, który wpadł w cykl, kosztuje pieniądze przy
  każdym obrocie, a operator widzi tylko to, że nic się nie dzieje.
- Odmowa narzędzia wraca do modelu jako wynik narzędzia, nie jako awaria tury. Zdania
  `market-mcp` są pisane właśnie po to, żeby model mógł poprawić żądanie i spróbować raz
  jeszcze — awaria tury odbiera mu tę możliwość.
- Wywołanie narzędzia zostawia ślad we własnej tabeli, nie w transkrypcie. Transkrypt
  jest tym, co czyta terminal, i ta zmiana go nie rusza.
- Każde wywołanie modelu w turze zostawia własny wiersz zużycia. Tura z trzema
  wywołaniami kosztuje trzy razy i rachunek MUSI to pokazać.
- Prompt systemowy `v3`: agent ma narzędzia, wie jakie, i wie, czego one nie mówią —
  archiwum zbiera wybrane pary, nie cały rynek, a to, czego nie zebrało, nie jest ciszą
  rynku.
- `infra/`: tożsamość zarządzana agenta wpisana w `allowed_applications` Easy Auth
  `market-mcp`, w miejsce zaślepki, którą tamta zmiana zostawiła świadomie.
- `scripts/dev.sh` i `dev.ps1`: kolejność już jest właściwa (`market-mcp` przed
  agentem), ale zależność przestaje być teoretyczna — czekanie na `/health` zaczyna coś
  znaczyć.

**Poza zakresem, świadomie i na życzenie:**

- **Cokolwiek w terminalu.** Panel agenta pokazuje to, co dziś: pytanie operatora i
  odpowiedź agenta. Wywołania narzędzi jadą do bazy i nie wychodzą na kontrakt — po to,
  żeby następna zmiana miała co pokazać. Podgląd wywołań („które narzędzie, z czym, co
  odpowiedziało") jest osobną zmianą, i to ona rusza `agent/contract.py` i panel.
- Narzędzia zapisujące — nie ma ich po tamtej stronie i ta zmiana ich nie dokłada.
- `capital-gateway`: pozycje, zlecenia, strumień na żywo. Agent widzi archiwum, nie
  rachunek maklerski.
- Wybór narzędzi per sesja, budżet kosztowy per sesja, równoległe wywołania w jednej
  turze.

## Capabilities

### New Capabilities

- `agent-tools`: skąd bierze się zestaw narzędzi, że wszystkie są czytające, jak wygląda
  tura z wywołaniem, sufit wywołań na turę, co się dzieje z odmową narzędzia i jaki ślad
  zostaje po wywołaniu.
- `agent-tool-access`: na jakich warunkach moduł łączy się z `market-mcp` — jednoznacznie
  wybrany tryb i tożsamość, skończony czas oczekiwania, oraz to, że niedostępny
  `market-mcp` nie zabiera agentowi mowy.

### Modified Capabilities

- `agent-chat`: wymaganie „Agent pracuje na jednym prompcie systemowym" każe promptowi
  mówić, że agent nie ma dostępu do świec ani wskaźników. Od tej zmiany to nieprawda i
  prompt MUST mówić coś innego — co dokładnie, jest treścią delty. Zakaz rekomendacji
  inwestycyjnej i zakaz podawania liczby, której agent nie widział, zostają bez zmian;
  ten drugi robi się właśnie teraz sprawdzalny.
- `agent-usage`: wymaganie „Każde wywołanie modelu zostawia ślad zużycia" pisano, gdy
  wywołanie na turę było dokładnie jedno, i jego scenariusz czyta się jak „jeden wiersz
  na wiadomość". Delta nazywa wprost przypadek wielu wywołań pod jedną wypowiedzią
  agenta.

## Impact

**Nowy kod**: `modules/agent` — klient MCP i węzeł narzędzi w grafie, tabela wywołań z
własną migracją, ustawienia dostępu do `market-mcp`, prompt `v3`. Zależności: klient
`mcp` (ten sam pakiet, którego `market-mcp` używa po stronie serwera) — `langgraph` i
`langchain-openai` już są.

**Bez zmian**: `agent/contract.py`, a więc i terminal. `market-mcp` nie jest dotykany ani
jedną linijką: agent jest jego konsumentem dokładnie tak, jak zaprojektowano, i wszystko,
czego potrzebuje, jest już opublikowane. `market-data` i `capital-gateway` tym bardziej.

**Infrastruktura**: `infra/app-service.tf` — `allowed_applications` na Easy Auth
`market-mcp` dostaje client id tożsamości agenta (`data.azuread_service_principal` po
`principal_id`, ten sam wzór, którym market-mcp wchodzi do market-daty), plus ustawienia
`MARKET_MCP_URL` i `MARKET_MCP_SCOPE` na aplikacji agenta. Apply robi operator.

**Wspólne**: `CLAUDE.md`, `README.md`, `docs/architecture.md` — diagram dostaje krawędź,
której dziś świadomie nie ma, a zdanie „agent nie ma narzędzi" znika z trzech miejsc.
`checks.yml` bez zmian: żaden kontrakt nie zyskuje drugiej kopii do pilnowania.

**Koszt bieżący**: żaden nowy po stronie infrastruktury. Po stronie dostawcy — realny i
w górę: tura z wywołaniem narzędzia to co najmniej dwa wywołania modelu zamiast jednego,
a wynik narzędzia wchodzi do promptu następnego z nich. Dlatego sufity `market-mcp` są
tam, gdzie są, i dlatego zużycie liczy się per wywołanie, nie per wiadomość.
