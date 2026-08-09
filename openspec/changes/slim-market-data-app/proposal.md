## Why

[`app.py`](modules/market-data/market_data/app.py) urósł do 773 linii i trzyma trzy rzeczy, z których
tylko jedna do niego należy: składanie aplikacji, wszystkie piętnaście tras modułu, i kawałek logiki
domenowej z własnym, globalnym stanem.

Objaw, który to nazywa, jest w testach. `_market_status_cache` to słownik na poziomie modułu
([`app.py:360`](modules/market-data/market_data/app.py#L360)), więc żyje tak długo jak proces
i jest wspólny dla każdej instancji aplikacji. `test_app.py` musi po niego sięgnąć do wnętrza
modułu i wyczyścić go w fixture `autouse`:

```python
from market_data.app import _market_status_cache
_market_status_cache.clear()
```

Test importujący prywatną nazwę z warstwy HTTP po to, żeby posprzątać stan, którego nie stworzył,
nie jest dziwactwem testu — jest raportem o tym, gdzie ten stan leży. Każda inna zależność modułu
(`pool`, `hub`, `ingest`, `job_runner`, `settings`, `history`, `client`) jest obiektem budowanym
w `lifespan` i trzymanym na `app.state`; cache statusu rynku jest jedynym wyjątkiem i jedynym,
który przecieka między testami.

Obok niego siedzi około stu linii logiki domenowej — `_market_status`, `_decide_late_pairs`,
`_fill_out`, `_tracked_pair_out` ([`app.py:363-454`](modules/market-data/market_data/app.py#L363-L454)) —
która nie ma nic wspólnego z HTTP: decyduje, czy para jest `STALLED` czy `MARKET_CLOSED`, i pod
jakim warunkiem wolno o to zapytać gatewaya. Żeby to przetestować, trzeba dziś wstać z całym
`TestClient`.

A ponad tym wszystkim piętnaście tras z pięciu niezależnych obszarów — meta, świece i pokrycie,
pary i usunięcia, zlecenia, subskrypcja — w jednym pliku, gdzie zmiana w zleceniach i zmiana
w subskrypcji konfliktują ze sobą bez powodu.

## What Changes

- Cache statusu rynku przestaje być słownikiem na poziomie modułu i staje się obiektem budowanym
  w `lifespan` i trzymanym na `app.state`, tak jak każda inna zależność tego modułu. Test tworzy
  własny, zamiast czyścić cudzy.
- Logika domenowa wyprowadzona z pliku tras: rozstrzyganie stanu spóźnionej pary trafia obok
  `collection_state` w `tracking.py`, a odpytywanie gatewaya o status rynku wraz z jego TTL — do
  własnego, małego modułu.
- Trasy rozbite na routery po obszarach: `meta` (`/`, `/health`), `candles` (`/candles/{symbol}`,
  `/coverage/{symbol}`), `pairs` (`/pairs`, `/pairs/{symbol}`, `/deletions`), `jobs`
  (`/jobs/estimate`, `/jobs`, `/jobs/{job_id}`, `/jobs/{job_id}/retry`) i `stream` (`/ws/candles`).
  `app.py` zostaje z tym, czym jest: `lifespan`, obsługa wyjątków, montaż routerów.
- **Żadna trasa nie zmienia ścieżki, metody, kodu odpowiedzi ani modelu odpowiedzi.** Kontrakt na
  drucie jest bit w bit ten sam.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

Brak. To jest refaktor: te same trasy, te same odpowiedzi, ten sam schemat OpenAPI. Zmienia się
wyłącznie to, w którym pliku co mieszka i skąd bierze się stan cache'a. Dlatego `.openspec.yaml`
niesie `skip_specs: true` — spec opisuje zachowanie, a zachowanie się nie zmienia.

## Impact

**market-data**: `app.py` (z 773 linii do składania aplikacji), nowy pakiet z routerami, nowy moduł
statusu rynku, `tracking.py` (przyjmuje rozstrzyganie stanu spóźnionej pary), `tests/test_app.py`
(znika fixture czyszczący globalny cache).

**Zasięg**: wyłącznie `market-data`. Terminal, gateway i baza nietknięte.

**Kolejność względem `generate-terminal-contract-from-openapi`**: tamta zmiana powinna wejść
pierwsza. Rozbicie tras na routery to dokładnie ten rodzaj przestawiania, przy którym schemat
OpenAPI potrafi się ruszyć niezauważenie — inne `tags`, inne `operationId`, inna kolejność
komponentów. Z wygenerowanym plikiem pod kontrolą wersji taka zmiana jest widocznym diffem,
a bez niego — niczym.
