## 1. Szkielet modułu

- [ ] 1.1 `modules/market-mcp/` z `pyproject.toml` (zależności: `mcp`, `httpx`, `pydantic`, `azure-identity`; grupa dev: `pytest`, `ruff`, `pyright`), `.env.example`, `README.md` z zapisaną wersją protokołu MCP i datą sprawdzenia
- [ ] 1.2 `market_mcp/config.py` — przełącznik trybu dostępu do archiwum; konfiguracja niejednoznaczna albo adres zdalny bez tożsamości odmawiana przy starcie
- [ ] 1.3 Testy `config.py`: adres zdalny bez tożsamości, pętla zwrotna bez tożsamości, oba tryby naraz
- [ ] 1.4 `market_mcp/client.py` — klient HTTP archiwum z limitem czasu; metody inne niż czytające odrzucane, jedyny wyjątek `POST /indicators/{symbol}`
- [ ] 1.5 Test klienta: próba żądania zmieniającego wywraca się; obliczenie wskaźników przechodzi
- [ ] 1.6 `market_mcp/server.py` — serwer MCP z transportem stdio i aplikacją ASGI, trasa zdrowia obok, `market_mcp/__main__.py` dla obu transportów
- [ ] 1.7 Narzędzie `list_tracked_pairs` i test przeciw podstawionemu archiwum
- [ ] 1.8 `Dockerfile`, wpis w `README.md` repozytorium

## 2. Świece, pokrycie, instrumenty

- [ ] 2.1 `market_mcp/reduce.py` — agregacja świec do grubszych okresów i obcinanie list, z nazwaniem faktu odcięcia w wyniku
- [ ] 2.2 `market_mcp/uncertainty.py` — zdania budowane z `uncovered`, `derived`, `settled` oraz z pustej serii dla pary niezbieranej
- [ ] 2.3 Narzędzie `get_candles` — sufity 200/500, agregacja powyżej, `uncovered` w treści
- [ ] 2.4 Narzędzie `get_last_price` — ostatnia świeca z jej momentem i wiekiem
- [ ] 2.5 Narzędzie `summarize_range` — OHLC okna, zmiana bezwzględna i procentowa, średni i maksymalny zakres świecy, największy ruch z momentem, liczba świec i luk
- [ ] 2.6 Narzędzie `describe_coverage` — przedziały zweryfikowane, najstarsza osiągalna świeca, dziury w oknie
- [ ] 2.7 Narzędzie `search_instruments` — 10 trafień
- [ ] 2.8 Testy: pusta seria dla pary niezbieranej nie czyta się jak cisza rynku; zakres ponad sufit wraca zagregowany i nazwany; okno roczne mieści się w budżecie znaków

## 3. Wskaźniki

- [ ] 3.1 Cache katalogu wskaźników unieważniany przez `algorithm_version`
- [ ] 3.2 Narzędzia `list_indicators` (filtr po grupie) i `describe_indicator`
- [ ] 3.3 Redukcja kształtu `lines` — ostatnia wartość, nachylenie, odległość od ceny, świece od przecięcia
- [ ] 3.4 Redukcja kształtów `markers`, `zones` i `levels` — sortowanie po odległości od ceny albo po świeżości, z licznikiem pominiętych
- [ ] 3.5 Narzędzie `compute_indicators` — tryby `latest` i `series`, sufity 3/10 wskaźników i 200 punktów serii
- [ ] 3.6 Narzędzie `levels_near_price` — poziomy, strefy i znaki z odległością od ostatniej ceny w punktach i procentach
- [ ] 3.7 Testy: `settled=false` ma swoje zdanie; wpis z `error` przepisuje powód archiwum; nieznany wskaźnik odsyła do katalogu; każdy z czterech kształtów wyjścia ma swój test redukcji
- [ ] 3.8 Zasoby MCP: katalog wskaźników, zbierane pary, pokrycie pary jako szablon
- [ ] 3.9 Prompt MCP `analiza-symbolu` — pokrycie, streszczenie okna, wskaźniki, nazwanie tego, czego nie wiadomo

## 4. Rzetelność i kontrakt

- [ ] 4.1 Jednolity kształt odmowy: oznaczenie błędu wywołania plus parametr do zmiany; wszystkie narzędzia przez jedną drogę
- [ ] 4.2 Rozróżnienie trzech rodzajów „nie wiem" — para niezbierana, przedział niezweryfikowany, archiwum nie odpowiada — i test na każdy z nich
- [ ] 4.3 Jedno ponowienie na błąd serwera archiwum; przekroczenie czasu jako odmowa nazywająca awarię
- [ ] 4.4 `scripts/contract.py generate|check` i commitowany `contract/market-data.openapi.json` — proces uruchamiany w katalogu siostrzanym, bez działającego archiwum
- [ ] 4.5 `tests/test_contract.py` — asercja każdego pola, po które sięga klient
- [ ] 4.6 `tests/test_tool_surface.py` — opis, typowane parametry, wpisany sufit, nazwane jednostki i strefa dla każdego narzędzia; brak narzędzia zapisującego
- [ ] 4.7 Test: stdio i transport sieciowy publikują ten sam zestaw narzędzi
- [ ] 4.8 Limit współbieżnych wywołań archiwum

## 5. Dostęp, wdrożenie, uruchomienie

- [ ] 5.1 Tożsamość zarządzana wobec archiwum; dziennik zapisuje fakt i tożsamość, nigdy treści ani poświadczenia
- [ ] 5.2 Wymóg tożsamości wołającego przy transporcie sieciowym, wyłączalny wyłącznie dla pracy lokalnej; test odmowy bez tożsamości
- [ ] 5.3 Test sondy zdrowia: odpowiada bez sesji MCP i przy niedostępnym archiwum
- [ ] 5.4 `infra/` — piąta aplikacja na planie App Service, jej tożsamość i uprawnienie do wołania archiwum; `plan` w CI, `apply` u operatora
- [ ] 5.5 `.github/workflows/checks.yml` — job modułu, wchodzący do filtra także na zmianie `market_data/contract.py`
- [ ] 5.6 `.github/workflows/deploy-market-mcp.yml` zakończony sprawdzeniem wdrożonej sondy zdrowia
- [ ] 5.7 `scripts/dev.sh` i `scripts/dev.ps1` — start po `market-data`, przed agentem, z czekaniem na odpowiedź
- [ ] 5.8 `CLAUDE.md`, `README.md`, `docs/architecture.md` — moduł, jego port i jego granica
