## Why

`capital-gateway` publikuje kontrakt — historię świecową, strumień na żywo i handel — ale nikt go
jeszcze nie ogląda. Sprawdzenie, czy świeca w budowie faktycznie rusza wykresem, wymaga oka, nie
kolejnego testu, a operator nie ma dziś żadnego miejsca, w którym patrzyłby na rynek. Ten sam brak
blokuje decyzję o bazie świec: zanim powstanie moduł archiwum, warto zobaczyć, ile terminal jest w
stanie unieść, czytając prosto z gatewaya.

## What Changes

- Nowy moduł `modules/terminal` — React + TypeScript, Vite, pnpm, Tailwind v4 — stojący samodzielnie
  i rozmawiający z `capital-gateway` wyłącznie po HTTP i WebSockecie.
- **Shell terminala**: routing po `react-router`, zakładki jako strony, ciemny motyw oparty na
  tokenach w CSS variables. Rejestr zakładek jest otwarty — dołożenie `Positions` czy `Orders`
  to wpis, nie przebudowa.
- **Reużywalny wykres** na `lightweight-charts`: ten sam komponent w slocie siatki i solo. Zaciąga
  historię, dokleja świece ze strumienia, pokazuje świecę w budowie jako świecę w budowie i
  przełącza rozdzielczość bez przeładowania strony.
- **Siatka wykresów** z presetami `1x1`, `2x1`, `2x2`, `3x2`, wybieranymi z paska. Każdy slot ma
  własny instrument i własny interwał; układ i zawartość slotów przeżywają odświeżenie strony.
- **Zakładka Instruments**: wyszukiwarka po `GET /instruments/search`, z której instrument trafia
  do wskazanego slotu siatki.
- **Warstwa danych za jednym interfejsem** `MarketDataSource`, z jedną implementacją: gateway
  (`GET /instruments/{symbol}/history` + `/ws/stream`). Interfejs istnieje nie dla dzisiejszego
  wyboru, tylko dlatego, że baza świec — gdy powstanie — ma wejść jako druga implementacja, a nie
  jako przebudowa wykresu.
- Zakładki handlowe (`Positions`, `Orders`, `Account`) pojawiają się wyłącznie jako puste miejsca w
  rejestrze; ich zachowanie to osobne zmiany.

## Capabilities

### New Capabilities

- `terminal-shell`: powłoka aplikacji — routing, rejestr zakładek, motyw, obsługa nieznanej ścieżki
  i stan „gateway nie odpowiada" widoczny globalnie.
- `terminal-market-data`: jeden interfejs na świece i strumień, wymienna implementacja za nim,
  zszycie znaczników czasu REST (ISO) ze strumieniem (epoch w sekundach), współdzielenie jednego
  połączenia przez wielu odbiorców tej samej pary symbol + rozdzielczość.
- `terminal-chart`: reużywalny wykres świecowy — zaciąg historii, doklejanie świec na żywo, świeca
  w budowie, zmiana rozdzielczości, stan pusty, ładowania i błędu.
- `terminal-grid`: siatka slotów z presetami układu, przypisaniem instrumentu i interwału do slotu
  oraz trwałością tej konfiguracji między sesjami.
- `terminal-instruments`: wyszukiwanie instrumentów i wstawianie ich do slotu siatki.

### Modified Capabilities

Brak. `capital-gateway` nie zmienia zachowania — terminal jest jego konsumentem i korzysta z
kontraktu takiego, jaki jest opublikowany.

## Impact

- Nowy katalog `modules/terminal/` z własnym `package.json`, `README.md`, `.env.example` i testami.
  Nic poza nim się nie zmienia; usunięcie katalogu usuwa moduł.
- Nowe zależności, wszystkie wewnątrz modułu: `react`, `react-dom`, `react-router`,
  `lightweight-charts`, `tailwindcss`, `vite`, `typescript`, `vitest`.
- `capital-gateway` musi wpuścić przeglądarkę: dziś nie ma CORS, a terminal chodzi na innym porcie.
  Zmiana obchodzi to własnym proxy `Vite` w developmencie — bez ruszania gatewaya i bez zmiany jego
  spec.
- `README.md` repozytorium i `docs/architecture.md` dostają terminal w tabeli modułów i na rysunku,
  gdzie dziś stoi „terminal (later)".
- Wymaga uruchomionego `capital-gateway` na `http://localhost:8010`. Terminal nie ma trybu
  offline: bez gatewaya pokazuje, że źródło nie odpowiada, i nic nie rysuje.
