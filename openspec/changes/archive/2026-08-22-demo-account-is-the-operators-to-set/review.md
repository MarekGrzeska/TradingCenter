# Review — demo-account-is-the-operators-to-set

## Sufit powierzchni narzędzi: reguła była, testu nie było

`trading-mcp-tools` wymaga od modułu, żeby trzymał zserializowaną powierzchnię poniżej
sufitu **zapisanego w jego własnym teście** — i przy pisaniu zadania 4.2 okazało się, że
`trading-mcp` takiego testu nigdy nie miał. Miała go `market-data` (19 700 znaków), a ten
moduł tylko ślimowanie schematów z `tc-mcp-kit` i wiarę, że to wystarczy. Obrona bez
pomiaru, czyli dokładnie to, co ten repozytorium raz już przestało akceptować.

Test dopisany w tej zmianie, z liczbą wziętą z pomiaru, nie z sufitu:

| | znaków | narzędzi |
|---|---:|---:|
| przed | 11 092 | 9 |
| po | 13 772 | 12 |
| sufit | 15 000 | — |

Trzy narzędzia konta kosztują 2 680 znaków, czyli około 900 na każde — czytane w **każdej**
turze rozmowy, która ma te narzędzia włączone. Zapas ~9% jest świadomy: mieści jedno
kolejne narzędzie tej wielkości, nie mieści akapitu dopisanego do każdego istniejącego.
Gdyby kiedyś trzeba było schodzić, pierwszy do obejrzenia jest `place_order` — 2 178
znaków, najdroższe pojedyncze narzędzie w module.

## `_write` rozpadło się na dwa, bo zmieniło się znaczenie „zapisu"

Dotąd każdy zapis w tym module był zleceniem i `_write` czytał odpowiedź jak zlecenie
(`status`, `REJECTED`, `PENDING`). Konto nie ma statusu — odpowiada kontem. Tłumaczenie
błędów jest jednak identyczne i to ono niesie regułę „odmowa ≠ awaria dostępu", więc
wyszło z `_write` do `_send_change`, a `_write` je woła. Doszedł jeden parametr:
`read_back`, czyli co model ma przeczytać, zanim spróbuje ponownie — przy zleceniu pozycje,
przy koncie konta. Bez tego komunikat o nieznanym skutku kazałby sprawdzać pozycje po
nieudanym doładowaniu.

## Czego nie sprawdziłem na żywo

Odmów dostawcy przy przekroczeniu sufitu salda i przy wyczerpanym limicie dobowym.
Testy używają odpowiedzi zmyślonej na podstawie dokumentacji (`error.request.top.up.
balance.exceeded`), a nie zaobserwowanej. Zakładam z D3, że taka odmowa przychodzi jako
4xx z treścią — jeżeli capital.com odpowiada tu 200 z ciałem `{"successful": false}`,
gateway uzna to za sukces i odczyt salda pokaże niezmienioną kwotę. Pierwsze wywołanie na
żywo to rozstrzygnie; test do dopisania wtedy, na zaobserwowanym kształcie, nie na moim.

Podobnie zerwanie strumienia przy przełączeniu konta: wiem z dokumentacji, że następuje, i
wiem z kodu, że `Upstream` odtwarza połączenie z narastającym odstępem. Nie zmierzyłem, ile
trwa luka w świecach.

## Weryfikacja

- `capital-gateway`: `uv run pytest` — 215 passed, 11 skipped
- `trading-mcp`: `uv run pytest` — 92 passed
- `uv run python scripts/contract.py check` — snapshot odświeżony i zgodny
- `ruff` i `pyright` w obu modułach — czysto
- `openspec validate demo-account-is-the-operators-to-set --strict` — valid
