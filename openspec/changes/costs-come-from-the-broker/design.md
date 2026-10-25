## Context

Motywacja w proposal.md. Stan, który kształtuje podejście:

- Pakiet `strategies` MUST NOT mieć drogi do bramy ani do `trading-mcp` (`strategies-api`, „Pakiet nie ma drogi do
  rachunku”). Archiwum `/market` czyta już przez REST w procesie (`strategies/archive.py`).
- Archiwum przekazuje bramie wyszukiwanie instrumentów, które niesie `bid` i `ask` (`market_data/routers/instruments.py`).
  Warunków instrumentu nie przekazuje.
- Brama czyta `GET /markets/{epic}` dla warunków (`mapping.instrument_terms_from_details`) i odrzuca z niego
  `instrument.overnightFee`. Nagranie z demo (`capital-gateway/tests/fixtures/market_gold.json`) ma tam `longRate`
  −0,0151992, `shortRate` 0,0069792, `swapChargeTimestamp` (ms, wypada o 21:00 UTC) i `swapChargeInterval` 1440.
- Wymaganie „Warunki handlowe instrumentu są osobnym odczytem” zabrania ceny w warunkach, więc spread trzeba wziąć z
  wyszukiwania, a nie z warunków.
- Panel agenta (`AgentChat`) przyjmuje magazyn jako argument, a `createAgentChatStore(storage, …)` tworzy niezależną
  instancję. Panel zapisuje w `localStorage` otwartą rozmowę i zwinięcie, a instancja bez `storage` nie zapisuje nic.

## Goals / Non-Goals

**Goals:**
- Pierwszy backtest instrumentu bez ani jednej liczby wpisanej przez operatora, z kosztami, które da się sprawdzić.
- Każdy raport mówi, skąd są jego koszty.
- Czat z agentem widoczny w oknie tworzenia strategii, z rozmową należącą do tej strategii.

**Non-Goals:**
- Godzinowy profil spreadu (archiwum ma tylko bid, broker podaje jeden bieżący spread).
- Koszty zmieniające się z czasem w obrębie jednego uruchomienia.

## Decisions

### D1. Koszty od brokera przez archiwum, nie przez nową drogę pakietu

Pakiet pyta `/market` o dwie rzeczy:
- `GET /instruments/search?q=SYMBOL` dla `bid` i `ask` (dokładne dopasowanie `symbol`);
- nowe proxy `GET /instruments/{symbol}/terms` dla finansowania.

Archiwum nic nie interpretuje, a przeliczenie robi `strategies/broker_costs.py`.

*Odrzucone:*
- Klient bramy w pakiecie strategii: łamie wymaganie, na którym stoi „research only”.
- `trading-mcp` przez agenta: jest opcjonalny i jest drzwiami do rachunku, a agent i tak mógłby wpisać co innego, niż
  przeczytał.
- Pole ceny w warunkach: łamie „Odczyt MUST NOT nieść ceny”.

### D2. Profil pobrany raz i trzymany, aż ktoś każe go odświeżyć

Profil powstaje przy pierwszej potrzebie i zostaje. Dwa uruchomienia tego samego dnia mają te same koszty, więc
`compare_runs` może je zestawić. Odświeżenie jest jawne (`POST /costs/{symbol}/from-broker`, przycisk w formularzu).
Profil zapisuje `source`, `fetched_at` i surowe wartości brokera (`broker`).

*Odrzucone:* pobieranie przy każdym uruchomieniu. Spread zmienia się co sekundę, więc żadne dwa uruchomienia nie
byłyby porównywalne, a każde byłoby zależne od pory dnia, o której je zlecono.

### D3. Przeliczenie stawek capital.com

- `longRate` i `shortRate` to procent wartości pozycji za dobę.
- Ujemna stawka oznacza, że posiadacz płaci. W nagraniu złota long płaci, a short dostaje, co zgadza się z rynkiem.
- Wynika z tego `overnight_long = −longRate / 100` i `overnight_short = −shortRate / 100` (u nas dodatnie = opłata).
- `rollover_hour` to godzina UTC chwili `swapChargeTimestamp`.
- Odstęp inny niż 1440 minut jest odmową z nazwaną przyczyną, bo model zna tylko naliczanie dobowe.
- Poślizg to 0, zapisany jawnie.

Sprawdzone na demo 25.10.2026 (zadanie 1.2): US100, EURUSD, GOLD i BTCUSD niosą `overnightFee`, wszystkie z
naliczeniem o 21:00 UTC i odstępem 1440. Historia konta ma opłatę BTCUSD z 25.08.2026 21:00 UTC: long 0,6021 po
78 195,4 (wartość 47 081,5 USD) zapłacił 29,02 USD, czyli 0,0616% wartości, a dzisiejszy `longRate` BTCUSD to
−0,0616438. Stawka jest więc w procentach wartości za dobę, a ujemna oznacza opłatę.

*Ryzyko:* zła interpretacja odwróciłaby znak finansowania w każdym raporcie. Dlatego profil trzyma surowe wartości, a
test sprawdza przeliczenie na nagraniu.

### D4. „Bez kosztów” to flaga, nie zera

`RunIn.without_costs = true` daje zerowy model, a `request` zapisuje `costs_source = "none"`. Wpisane zera to model z
`costs_source = "request"`. Raport (`ReportOut.costs_source`, `without_costs`) i lista uruchomień odróżniają te przypadki,
bo zero wpisane świadomie i brak kosztów to różne zdania o strategii. Wtedy `compare_runs` i tak odmawia
zestawienia z uruchomieniem z kosztami, bo różnią się koszty.

### D5. Czat strategii to druga instancja rozmowy, osadzona w oknie tworzenia

Okno tworzenia ma własny czat obok edytora, tak jak Alerty mają pole „opisz zdaniem” w swoim oknie. Pod spodem jest ta
sama rozmowa workbencha (`/sessions`, strumień, narzędzia, ślad wywołań, koszt) z kontekstem strategii
(`strategyInView`). Inna jest tylko instancja magazynu w terminalu: `createAgentChatStore(null, …)` nie zapisuje nic w
`localStorage`, więc nie rusza otwartej rozmowy ani zwinięcia panelu. Transkrypt i pole wpisu to te same komponenty co w
panelu, wyjęte z `AgentChat.tsx` do wspólnego użytku. Sesje czatu strategii widać też na liście rozmów w panelu, bo to
zwykłe rozmowy. Nazywają się nazwą strategii.

Strategia pamięta swoją rozmowę w pakiecie strategii (`strategies.conversation_id`, `PUT /strategies/{id}/conversation`).
Pakiet trzyma tylko liczbę: nie czyta rozmowy i nie importuje `agent`. Przy nowej strategii rozmowa powstaje pierwsza, a
okno przypisuje ją strategii, którą agent w niej zapisał (`createdDuringTurn`).

*Odrzucone:*
- Szkic z modelu w pakiecie strategii, jak `POST /drafts` w alertach: drugi model z własnym kluczem, bez narzędzi i bez
  pętli walidacji, którą agent już ma. Do tego jednorazowe zdanie zamiast rozmowy, a strategia wymaga dopytania.
- Pole w zakładce, które pisze do panelu i go rozwija: tak było w pierwszej wersji tej propozycji. Operator chce czatu w
  oknie tworzenia, nie przekierowania do panelu.
- Przypisanie rozmowy w `localStorage` terminala: znikałoby na innym urządzeniu i po wyczyszczeniu przeglądarki.

## Risks / Trade-offs

- [Spread pobrany poza godzinami handlu jest szerszy albo nieaktualny] → profil zapisuje stan rynku i chwilę pobrania,
  formularz je pokazuje, a odświeżenie jest jednym kliknięciem.
- [Jeden spread zamiast profilu godzinowego zaniża koszt strategii minutowych w nocy i na otwarciu] → raport podaje
  źródło kosztów, a profil godzinowy operator dalej może wpisać ręcznie.
- [Godzina rozliczenia przesuwa się z czasem letnim] → profil zapisuje godzinę z chwili pobrania, a odświeżenie ją
  aktualizuje. Model kosztów zna jedną godzinę na uruchomienie.
- [Pierwsze uruchomienie zależy od bramy] → odmowa z przyczyną, nic nie zostaje zapisane, a ponowienie działa po
  powrocie bramy.

## Migration Plan

1. Merge = wdrożenie. Migracja `0003` w lifespanie pod kluczem 8130 dodaje `cost_profiles.source` (domyślnie
   `operator`), `fetched_at`, `broker` (jsonb) i `strategies.conversation_id` (bigint, puste).
2. Brama, archiwum i workbench wdrażają się razem (jeden `deploy.sh`). Starsza brama nie ma pól finansowania, więc
   pobranie profilu odmówiłoby z nazwaną przyczyną.
3. Wycofanie: poprzednie obrazy. Nowe kolumny są opcjonalne dla starego kodu.

## Open Questions

- Czy capital.com podaje `overnightFee` dla każdej klasy instrumentów? Na demo tak dla indeksu, waluty, surowca i krypto
  (D3). Brak pola i tak jest odmową z nazwą, więc instrument bez niego nie zmienia podejścia.
