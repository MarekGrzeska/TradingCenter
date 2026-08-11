## 1. Szkielet modułu

- [x] 1.1 `modules/market-mcp/` z `pyproject.toml` (zależności: `mcp`, `httpx`, `pydantic`, `azure-identity`; grupa dev: `pytest`, `ruff`, `pyright`), `.env.example`, `README.md` z zapisaną wersją protokołu MCP i datą sprawdzenia
- [x] 1.2 `market_mcp/config.py` — przełącznik trybu dostępu do archiwum; konfiguracja niejednoznaczna albo adres zdalny bez tożsamości odmawiana przy starcie
- [x] 1.3 Testy `config.py`: adres zdalny bez tożsamości, pętla zwrotna bez tożsamości, oba tryby naraz
- [x] 1.4 `market_mcp/client.py` — klient HTTP archiwum z limitem czasu; metody inne niż czytające odrzucane, jedyny wyjątek `POST /indicators/{symbol}`
- [x] 1.5 Test klienta: próba żądania zmieniającego wywraca się; obliczenie wskaźników przechodzi
- [x] 1.6 `market_mcp/server.py` — serwer MCP z transportem stdio i aplikacją ASGI, trasa zdrowia obok, `market_mcp/__main__.py` dla obu transportów
- [x] 1.7 Narzędzie `list_tracked_pairs` i test przeciw podstawionemu archiwum
- [x] 1.8 `Dockerfile`, wpis w `README.md` repozytorium

## 2. Świece, pokrycie, instrumenty

- [x] 2.1 `market_mcp/reduce.py` — agregacja świec do grubszych okresów i obcinanie list, z nazwaniem faktu odcięcia w wyniku
- [x] 2.2 `market_mcp/uncertainty.py` — zdania budowane z `uncovered`, `derived` oraz z pustej serii dla pary niezbieranej (`settled` dołącza w grupie 3 — dotyczy tylko wyniku wskaźnika, którego tu jeszcze nie ma)
- [x] 2.3 Narzędzie `get_candles` — domyślny cel agregacji 200 świec, odmowa powyżej 2000 (10×, reguła „powyżej ~10× sufitu — odmowa”), `uncovered` w treści
- [x] 2.4 Narzędzie `get_last_price` — ostatnia świeca z jej momentem i wiekiem
- [x] 2.5 Narzędzie `summarize_range` — OHLC okna, zmiana bezwzględna i procentowa, średni i maksymalny zakres świecy, największy ruch z momentem, liczba świec i luk
- [x] 2.6 Narzędzie `describe_coverage` — przedziały zweryfikowane (limit 20, najnowsze pierwsze), najstarsza osiągalna świeca, dziury w oknie
- [x] 2.7 Narzędzie `search_instruments` — 10 trafień
- [x] 2.8 Testy: pusta seria dla pary niezbieranej nie czyta się jak cisza rynku; zakres ponad sufit wraca zagregowany i nazwany; okno roczne mieści się w budżecie znaków

## 3. Wskaźniki

- [x] 3.1 Cache katalogu wskaźników — pobierany raz na proces (kolejna zmiana `algorithm_version` przychodzi z restartem modułu, nie z odpytywania w kółko)
- [x] 3.2 Narzędzia `list_indicators` (filtr po grupie) i `describe_indicator`
- [x] 3.3 Redukcja kształtu `lines` — ostatnia wartość, nachylenie, odległość od ceny, świece od przecięcia
- [x] 3.4 Redukcja kształtów `markers`, `zones` i `levels` — świeżość w `compute_indicators` (wybór wskaźników jest już decyzją wołającego), odległość od ceny w `levels_near_price`; licznik pominiętych w obu
- [x] 3.5 Narzędzie `compute_indicators` — tryby `latest` i `series`, twardy sufit 10 wskaźników (bez osobnego „domyślnie 3" — nie ma tu agregacji, więc nie ma czego stopniować), 200 punktów serii
- [x] 3.6 Narzędzie `levels_near_price` — poziomy, strefy i znaki z odległością od ostatniej ceny w punktach i procentach, wsadowo po 10 wskaźników na żądanie
- [x] 3.7 Testy: `settled=false` ma swoje zdanie; wpis z `error` przepisuje powód archiwum; nieznany wskaźnik (i alias) odsyła do katalogu; każdy z czterech kształtów wyjścia ma swój test redukcji
- [x] 3.8 Zasoby MCP: katalog wskaźników, zbierane pary, pokrycie pary jako szablon
- [x] 3.9 Prompt MCP `analyze-symbol` (nazwa po angielsku — CLAUDE.md: identyfikatory kodu, nie proza OpenSpec) — pokrycie, streszczenie okna, wskaźniki, nazwanie tego, czego nie wiadomo

Przy okazji: `market_mcp/tools.py` rozbite na pakiet `market_mcp/tools/` (`pairs.py`, `candles.py`, `instruments.py`, `indicators.py`, `_shared.py`) — ten sam podział co `market_data/routers/`, zanim jeden plik urósł do rozmiaru, który ten podział miał zapobiec.

## 4. Rzetelność i kontrakt

- [x] 4.1 Jednolity kształt odmowy: `ToolRefusal` przez `raise_for_status` na każdym z 13 miejsc wołania klienta (audyt: liczba wywołań `upstream.get`/`compute_indicators` równa liczbie `raise_for_status` w każdym pliku); test na 7 narzędziach naraz
- [x] 4.2 Rozróżnienie trzech rodzajów „nie wiem" — para niezbierana, przedział niezweryfikowany, archiwum nie odpowiada — test na poziomie narzędzia (nie tylko klienta) na każdy z nich, plus test że trzy zdania różnią się treścią
- [x] 4.3 Jedno ponowienie na błąd serwera archiwum (nie na 4xx); `httpx.TimeoutException`/`RequestError` jako `ToolRefusal` nazywająca awarię, nie surowy wyjątek
- [x] 4.4 `scripts/contract.py generate|check` i commitowany `contract/market-data.openapi.json` — proces uruchamiany w katalogu siostrzanym, bez działającego archiwum. Po drodze złapane: Windows koduje stdout w kodowaniu ANSI, więc em-dash w docstringach `market_data.contract` wywalał dekodowanie UTF-8 — ten sam problem, przed którym ostrzegał `contract.mjs`, naprawiony tym samym sposobem (`PYTHONIOENCODING`/`PYTHONUTF8`)
- [x] 4.5 `tests/test_contract.py` — asercja każdego pola i każdej ścieżki, po które sięga klient (16 modeli, 6 ścieżek); `/instruments/search` świadomie pominięte — market-data przekazuje tam JSON gatewaya nieodczytany, bez `response_model`, więc nie ma kontraktu do sprawdzenia
- [x] 4.6 `tests/test_tool_surface.py` — opis, typowane parametry, wpisany sufit (tam gdzie istnieje), nazwana strefa czasowa i strona ceny (bid) dla narzędzi, które ich dotyczą; `readOnlyHint=True` na każdym narzędziu jako strukturalny, nie tylko nazewniczy, dowód braku zapisu. Po drodze uzupełnione braki w opisach (UTC, bid, sufity), które ten test faktycznie wyłapał
- [x] 4.7 Test: prawdziwy subproces stdio i prawdziwy serwer HTTP (realny port, `uvicorn.Server` w wątku) publikują ten sam zestaw 10 narzędzi — nie asercja przez czytanie kodu, tylko przez oba transporty naraz
- [x] 4.8 Limit 8 współbieżnych wywołań archiwum (`asyncio.Semaphore` w `client.py`), test mierzący szczyt współbieżności

## 5. Dostęp, wdrożenie, uruchomienie

- [ ] 5.1 Tożsamość zarządzana wobec archiwum; dziennik zapisuje fakt i tożsamość, nigdy treści ani poświadczenia
- [ ] 5.2 Wymóg tożsamości wołającego przy transporcie sieciowym, wyłączalny wyłącznie dla pracy lokalnej; test odmowy bez tożsamości
- [ ] 5.3 Test sondy zdrowia: odpowiada bez sesji MCP i przy niedostępnym archiwum
- [ ] 5.4 `infra/` — piąta aplikacja na planie App Service, jej tożsamość i uprawnienie do wołania archiwum; `plan` w CI, `apply` u operatora
- [ ] 5.5 `.github/workflows/checks.yml` — job modułu, wchodzący do filtra także na zmianie `market_data/contract.py`
- [ ] 5.6 `.github/workflows/deploy-market-mcp.yml` zakończony sprawdzeniem wdrożonej sondy zdrowia
- [ ] 5.7 `scripts/dev.sh` i `scripts/dev.ps1` — start po `market-data`, przed agentem, z czekaniem na odpowiedź
- [ ] 5.8 `CLAUDE.md`, `README.md`, `docs/architecture.md` — moduł, jego port i jego granica
