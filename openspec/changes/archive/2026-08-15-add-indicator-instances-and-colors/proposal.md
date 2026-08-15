## Why

Operator porównuje bias na kilku horyzontach naraz — EMA 20 obok EMA 50 obok EMA 200 to
codzienna robota, a nie egzotyka. Dziś wykres pozwala włączyć każdy wpis katalogu **raz**:
wybierak trzyma selekcje po `id`, więc druga EMA nie ma jak powstać, a zmiana okresu
przestawia tę jedyną. Kolor linii przydziela cykl palety w kolejności liczenia, więc ta
sama średnia potrafi zmienić barwę, gdy operator dołoży inny wskaźnik — i nie ma jak
powiedzieć „ta wolna niech będzie szara".

Archiwum jest już na to gotowe: `POST /indicators` przyjmuje listę zamówień i odpowiada
osobnym wynikiem na każde, powtarzając parametry (`market-data-indicators`, „Ten sam
wskaźnik z różnymi parametrami"). Brakuje wyłącznie strony terminala.

## What Changes

- Wybór wskaźnika przestaje być przełącznikiem „włączony / wyłączony", a staje się listą
  **instancji**: operator dokłada kolejną instancję tego samego wpisu katalogu, ustawia jej
  parametry osobno i usuwa ją osobno. Dotyczy każdego wpisu katalogu, nie tylko średnich.
- Instancja niesie **kolor wybrany przez operatora** — próbka z palety motywu, ta sama,
  z której dziś rysuje się cykl. Instancja bez wybranego koloru zachowuje się jak dziś.
- Zestaw wskaźników slotu zapamiętywany razem z kolorami i podziałem na instancje; slot
  zapisany przed tą zmianą wczytuje się dalej.
- Archiwum MUST odpowiadać w kolejności zamówienia — dziś tak robi, ale nigdzie tego nie
  obiecuje, a terminal zaczyna po tej kolejności wiązać wyniki z instancjami.
- Bez zmian w kontrakcie: `market_data/contract.py` zostaje nietknięty, kolor nie jedzie na
  drut. `pnpm contract:generate` nie jest potrzebne.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `terminal-chart`: wybór wskaźników dopuszcza kilka instancji jednego wpisu katalogu,
  każdą z własnymi parametrami i własnym kolorem; wartości spod kursora i panele własne
  rozróżniają instancje.
- `terminal-grid`: stan slotu niesie instancje wraz z kolorami, a slot zapisany wcześniej
  wczytuje się bez utraty wskaźników.
- `market-data-indicators`: odpowiedź MUST układać wyniki w kolejności zamówionych
  wskaźników.

## Impact

- `modules/terminal`: `chart/indicators/IndicatorPicker.tsx`, `chart/indicators/useIndicators.ts`,
  `chart/Chart.tsx` (klucze serii, paneli, prymitywów i legendy), `chart/theme.ts`,
  `data/types.ts` (`IndicatorSelection`), `data/archive.ts`, `grid/model.ts` (walidacja
  zapisanego slotu i wczytanie starego kształtu).
- `modules/market-data`: test kolejności wyników; kod routera bez zmian.
- Bez zmian: `market_data/contract.py`, `contract.generated.ts`, katalog wskaźników,
  `infra/**`.
