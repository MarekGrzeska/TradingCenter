## 1. Pomiar dostawcy, zanim powstanie klient

- [x] 1.1 Metadane wydarzenia po adresie i po identyfikatorze: kształt odpowiedzi, rynki, wyniki, identyfikatory, po których odpytuje się cenę, stan rozstrzygnięcia; zapisać przykładowe odpowiedzi
- [x] 1.2 Szereg czasowy ceny: parametry, maksymalne okno na żądanie, dostępna rozdzielczość dla starych zakresów, zachowanie dla rynku rozstrzygniętego
- [x] 1.3 Cena ostatniej transakcji wobec wyceny z księgi na kilku rynkach o różnej płynności; wybrać domyślną dla odczytu
- [x] 1.4 Przeglądanie publicznej bazy: tagi dostawcy, porządki sortowania, stronicowanie
- [x] 1.5 Limity tempa obu powierzchni: gdzie dostawca zaczyna odmawiać; wartości startowe throttle i backoff
- [x] 1.6 Wyniki 1.1–1.5 dopisać do `design.md`; bez nich kolejne grupy stoją
- [x] 1.7 Poprawić artefakty tam, gdzie pomiar im zaprzeczył: wymaganie o dwóch powierzchniach w `polymarket-data-upstream-access`, przycinanie okna przy zapisie w `polymarket-data-ingest`, decyzja o próbkowaniu przez metadane w `design.md`

## 2. Szkielet modułu

- [x] 2.1 `modules/polymarket-data/`: pakiet `polymarket_data`, `pyproject.toml`, lock, `Dockerfile`, README, `.env.example`
- [x] 2.2 `config.py` — ustawienia bazy, taktu próbkowania, głębokości uzupełniania, sufitu obserwacji, throttle'a i tożsamości wołających
- [x] 2.3 `tc-runtime` (baza, Easy Auth) i `tc-mcp-kit` (tożsamość wołającego, odchudzanie schematów, kształt odmowy upstreamu); `mcp` przypięty tak jak w `market-data`
- [x] 2.4 Baza `polymarket` w `compose.yaml`; rola i baza tworzone przez `scripts/dev.py`
- [x] 2.5 Alembic + migracja w `lifespan` pod blokadą doradczą z kluczem 8070, własną tożsamością modułu
- [x] 2.6 Wiersz w tabeli startowej `scripts/dev.py`: port 8070, kolejność, powód; kontrola `.env` przy starcie
- [x] 2.7 Testy: konfiguracja (obie odmowy trybu połączenia, sufit okna dostawcy, puste listy wołających), klucz blokady, trasy zdrowia. Testy samej migracji są w 3.7 — przed pierwszą migracją nie mają czego sprawdzać
- [x] 2.8 Wyprzedzone z grupy 8, bo `scripts/tests` odmawia inaczej: `deploy-polymarket-data.yml` (Dockerfile bez workflow deploya to nieudany test), job i filtr w `checks.yml` (moduł bez joba jest zielony dlatego, że nic go nie uruchomiło) oraz linie w `CLAUDE.md`, których wymaga `test_guide_ceiling.py`
- [x] 2.9 `uv run pytest`, `ruff check .`, `pyright` — moduł i `scripts`

## 3. Model danych i archiwum

- [ ] 3.1 Wydarzenie → rynki → wyniki, z identyfikatorami dostawcy i stanem rozstrzygnięcia; kolumny zamiast surowego JSON parsowanego przy każdym użyciu
- [ ] 3.2 Grupy obserwacji (lokalne kategorie), przypisanie wydarzenia, skasowanie grupy bez skutków dla danych
- [ ] 3.3 Próbka na wynik: rodzaj wyceny, moment pobrania i moment, którego wycena dotyczy; unikalność (wynik, moment) z nadpisaniem
- [ ] 3.4 Zebrane zakresy i granica najstarszego osiągalnego momentu — zapisywana na najstarszym zwróconym punkcie, nie na krawędzi okna
- [ ] 3.5 Sufit liczby obserwacji sprawdzany w jednym miejscu, wspólnym dla obu powierzchni
- [ ] 3.6 Testy: rynek wielowynikowy, zapis dwiema drogami w ten sam moment, brak notowania wobec braku zbierania, `@pytest.mark.db` tylko tam, gdzie test rusza bazę

## 4. Klient dostawcy i zbieranie

- [ ] 4.1 Klient obu powierzchni dostawcy z throttle'em, backoffem i identyfikacją klienta w nagłówku; odmowa i limit odróżnione od braku danych
- [ ] 4.2 Odświeżanie struktury obserwowanego wydarzenia: nowy rynek, rozstrzygnięcie rynku
- [ ] 4.3 Próbkowanie **wywołaniem na wydarzenie**, nie na token (design.md, „Próbkowanie idzie przez metadane"); rusza przy objęciu obserwacją bez restartu, ustaje przy rozstrzygnięciu i przy zakończeniu obserwacji
- [ ] 4.4 Uzupełnianie przeszłości oknami o szerokości z konfiguracji (zmierzony sufit dostawcy: 15 dni) — każde osobno się udaje, zawodzi i jest ponawiane; nieudane okno nie uchodzi za zebrane; obie krawędzie sprawdzane przy zapisie, bo odpowiedź wykracza poza żądane okno
- [ ] 4.5 Domknięcie luki przy starcie i po przerwie dłuższej niż takt
- [ ] 4.6 Porażka nie zapisuje próbki zastępczej ani nie powtarza ostatniej ceny; powtarzające się porażki widoczne w stanie obserwacji
- [ ] 4.7 Testy: odmowa dostawcy nie zostawia zakresu oznaczonego jako zebrany, uzupełnianie nie głodzi taktu, backoff po limicie, punkt spoza okna nie jest zapisywany
- [ ] 4.8 Test równoważności powierzchni: wycena z metadanych wobec wyceny z księgi na próbie — rozjazd ma wywrócić test, nie zmienić po cichu znaczenia serii

## 5. Kontrakt REST

- [ ] 5.1 `polymarket_data/contract.py` — kształty publikowane konsumentom, niezależne od kształtu dostawcy
- [ ] 5.2 Trasy obserwacji: lista, objęcie obserwacją (adres albo identyfikator, opcjonalna grupa), zakończenie obserwacji
- [ ] 5.3 Trasy grup: utworzenie, odczyt, przypisanie, skasowanie
- [ ] 5.4 Migawka ostatnich cen wszystkich obserwowanych wyników jednym żądaniem; historia ceny wyniku po zakresie
- [ ] 5.5 Zmiany w oknach 5m/15m/1h/4h/12h/24h/7d liczone przy odczycie, z tolerancją na nierówny takt i z momentem punktu bazowego w odpowiedzi
- [ ] 5.6 Kasowanie zebranej historii — wyłącznie tutaj, niepodzielnie z zapisem zebranych zakresów
- [ ] 5.7 Testy: po trzy na trasę CRUD (ścieżka szczęśliwa, błąd, odmowa); okno bez pokrycia jako brak z przyczyną, nie jako zero

## 6. Powierzchnia MCP

- [ ] 6.1 Sześć narzędzi odczytu: `search_events`, `browse_events`, `list_tracked_events`, `get_event`, `get_price_history`, `get_price_changes`
- [ ] 6.2 Trzy narzędzia listy obserwacji: `track_event`, `untrack_event`, `create_group` — wspólna droga zapisu z kontraktem REST, ten sam sufit, ta sama odmowa
- [ ] 6.3 Odpowiedzi odróżniają dane z archiwum od pobranych od dostawcy na żywo; cena niesie moment i wiek; skala ceny nazwana w opisie
- [ ] 6.4 Wynik przeszukania wskazuje, które wydarzenia są już obserwowane
- [ ] 6.5 Tożsamość wołającego z `tc-mcp-kit`, fail-closed; rozdział uprawnień trasa narzędziowa wobec REST; sonda zdrowia poza wymogiem
- [ ] 6.6 Test sufitu powierzchni narzędzi z zapisaną liczbą; test schematu odpowiedzi wobec tego, co narzędzie naprawdę oddaje
- [ ] 6.7 Testy odmowy: żadne narzędzie nie kasuje historii, nie zmienia konfiguracji i nie dotyka rachunku; każda para „tożsamość — powierzchnia bez prawa" ma test
- [ ] 6.8 `uv run pytest`, `ruff check .`, `pyright`

## 7. Workbench

- [ ] 7.1 Trzecia trójka pól w `workbench/config.py` obok `market_mcp_*` i `trading_mcp_*`, przepuszczona przez `for_conversation()` i `for_teams()` oraz `AgentSettings` i `TeamsSettings`
- [ ] 7.2 `_blank_means_unset` obejmuje nowe pola — `POLYMARKET_MCP_URL=` znaczy to samo co linia nieobecna
- [ ] 7.3 Kolizja nazw narzędzi: uogólnienie na dowolną liczbę serwerów, komunikat wymieniający wszystkie ogłaszające tę nazwę (`teams/`)
- [ ] 7.4 Testy: nieobecność URL-a jest konfiguracją wspieraną; zespół z przypisanymi narzędziami odmawia startu przebiegu bez serwera; kolizja trzech serwerów wymienia trzy
- [ ] 7.5 `.env.example` workbencha i akapit w README o trzeciej parze
- [ ] 7.6 `uv run pytest`, `ruff check .`, `pyright`

## 8. Infrastruktura i CI

- [ ] 8.1 App Service z własną tożsamością zarządzaną, Easy Auth, nazwa zasobu zgodna z modułem od pierwszego dnia
- [ ] 8.2 Baza `polymarket` na produkcji; `scripts/grant-schema-ownership.sql` raz, przez operatora
- [ ] 8.3 Tożsamość workbencha w `allowed_applications` i `TOOL_CALLER_APPLICATION_IDS` nowego modułu; identyfikatory aplikacji z `azp`/`appid`
- [ ] 8.4 `POLYMARKET_MCP_URL` i zakres w ustawieniach workbencha
- [ ] 8.5 `deploy-polymarket-data.yml` na wzór pozostałych czterech, kończący się `scripts/deploy_probe.py`
- [ ] 8.6 `checks.yml`: nowy job z filtrem `changes` oraz para — zmiana w `polymarket_data/contract.py` odpala job terminala
- [ ] 8.7 `terraform plan` na PR; `apply` lokalny operatora, bo zmiana rusza `azuread_*`

## 9. Prawda w plikach

- [ ] 9.1 `CLAUDE.md`: mapa modułów, tabela komend, linia portów — 8070 znika z listy niczyich, zostają 8040 i 8050
- [ ] 9.2 `CLAUDE.md`: akapit o `MARKET_MCP_URL` dostaje trzeciego brata — nieobecność `POLYMARKET_MCP_URL` jest działającą konfiguracją
- [ ] 9.3 `docs/architecture.md`: nowy moduł, jego dwie powierzchnie i powód, dla którego nie ma osobnej bramki
- [ ] 9.4 README modułu: co zbiera, czego nie robi, i skąd wziął się kształt (analiza z 22 sierpnia 2026)

## 10. Wdrożenie i sprawdzenie

- [ ] 10.1 Wypuścić moduł; sonda `/` odpowiada, migracja wykonana, `deploy_probe.py` przechodzi
- [ ] 10.2 `apply` operatora — ustawienia i listy wołających **przed** wdrożeniem workbencha
- [ ] 10.3 Wdrożyć workbench z trzecią parą
- [ ] 10.4 Sprawdzenie: rozmowa widzi dziewięć nowych narzędzi; objęcie obserwacją z poziomu modelu rusza próbkowanie i uzupełnianie; historia jest odczytywalna godzinę później
- [ ] 10.5 Sprawdzenie odmów: wołający bez tożsamości odbity, wołający narzędzi nie kasuje historii, sufit obserwacji odmawia z powodem
- [ ] 10.6 `review.md` — co zmierzono na dostawcy, co odpowiedziało po wdrożeniu, i test na każdy scenariusz albo nazwana luka
