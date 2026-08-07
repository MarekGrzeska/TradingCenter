## 1. Szkielet

- [x] 1.1 Utworzyć `modules/capital-gateway/` z `pyproject.toml` (Python ≥3.12, `uv`, `package = false`, ruff line-length 100, pytest `asyncio_mode = "auto"` i marker `live`)
- [x] 1.2 Dodać `.env.example` z `CAPITAL_API_KEY`, `CAPITAL_IDENTIFIER`, `CAPITAL_PASSWORD`, `CAPITAL_BASE_URL`, `CAPITAL_STREAM_URL`
- [x] 1.3 Napisać `config.py`: ustawienia pydantic plus bezpiecznik demo-only — adres bazowy albo adres strumienia spoza demo podnosi wyjątek, zanim powstanie aplikacja
- [x] 1.4 Napisać `errors.py` — typ błędu modułu niosący status HTTP
- [x] 1.5 Test: host produkcyjny w którymkolwiek adresie wywala start; brak poświadczeń wywala start, nazywając brakującą wartość

## 2. Typy kontraktu

- [x] 2.1 Napisać `dtos.py`: `AssetClass`, `Direction`, `Resolution`, `OrderStatus`, `OrderType`, `Instrument`, `InstrumentPage`, `Candle`, `Account`, `Position`, `Order`, `WorkingOrder`, `PlaceOrderRequest`, `UpdatePositionRequest`, `Capabilities` — przeniesione z `broker-gateway`, z `Capabilities` rozszerzonym o środowisko i streaming
- [x] 2.2 Dodać typ odpowiedzi głębokiej historii: świece plus liczba zebranych, liczba wysłanych żądań, pokryty okres i informacja, czy historia skończyła się przed zaspokojeniem żądania
- [x] 2.3 Walidacja: LIMIT/STOP bez poziomu jest odrzucane; zmiana niewskazująca żadnego stopu jest odrzucana

## 3. Klient REST i sesja

- [x] 3.1 Napisać `client.py`: asynchroniczny klient httpx, logowanie przechwytujące `CST` i `X-SECURITY-TOKEN`, helper żądania uwierzytelnionego, jedno ponowne logowanie i ponowienie na 401
- [x] 3.2 Dzielić jedno trwające logowanie między współbieżnych wywołujących, żeby seria żądań powodowała pojedyncze logowanie
- [x] 3.3 Przepuścić każde wywołanie do providera przez jedną ograniczoną bramkę trzymającą moduł poniżej 10 żądań/s
- [x] 3.4 Test na `respx`: wygasła sesja uwierzytelnia się ponownie i ponawia raz; współbieżni wywołujący wywołują dokładnie jedno logowanie; bramka ogranicza współbieżność żądań

## 4. Mapping i adapter

- [x] 4.1 Nagrać fixture'y payloadów providera do `tests/fixtures/` (sesja, konta, wyszukiwanie rynków, nawigacja po katalogu, ceny, pozycje, zlecenia oczekujące, confirms)
- [x] 4.2 Napisać `mapping.py` — czyste funkcje payload→DTO, świece czytane ze strony **bid**
- [x] 4.3 Napisać `adapter.py`: konta, przełączanie aktywnego konta, wyszukiwanie instrumentów, obchód katalogu z własnym ograniczeniem i flagą `truncated`, odczyt świec
- [x] 4.4 Adapter: pozycje, składanie zleceń (MARKET → pozycja, LIMIT/STOP → zlecenie oczekujące), zamknięcie, zmiana z trójstanem na polu, lista i anulowanie zleceń oczekujących
- [x] 4.5 Adapter: rozliczenie `dealReference → confirms`, ograniczona liczba prób, nierozwiązana referencja zwraca `PENDING`, nigdy `FILLED`
- [x] 4.6 Testować mapping wyłącznie na fixture'ach; adapter na `respx`, łącznie z odrzuconą transakcją i rozliczeniem, które nigdy nie przychodzi

## 5. Głęboka historia

- [x] 5.1 Napisać `history.py`: stronicowanie wstecz, szerokość okna `(liczba − 1) × rozdzielczość`, `from`/`to` jako `YYYY-MM-DDTHH:MM:SS` UTC
- [x] 5.2 Kotwiczyć każde kolejne okno na najstarszej pobranej świecy, a nie na zegarze
- [x] 5.3 Zatrzymywać się na `error.prices.not-found`, na oknie niedającym nic starszego albo na żądanej liczbie; sortować, usuwać duplikaty po znaczniku czasu, przycinać do żądania
- [x] 5.4 Przestać wysyłać żądania do providera, gdy wywołujący się rozłączy
- [x] 5.5 Test: odczyt wielostronicowy zwraca jedną uporządkowaną serię bez duplikatów; przebieg poza dno historii zwraca to, co zebrał, i mówi, że historia się skończyła; okno bez postępu kończy pętlę

## 6. Streaming

- [x] 6.1 Napisać `stream/messages.py` — publikowane kształty `candle`, `quote`, `status`, `error`
- [x] 6.2 Napisać `stream/forming.py`: kwotowania → świeca w budowie; zaokrąglanie znacznika czasu w dół do rozdzielczości wewnątrz dnia, rozciąganie ostatniej znanej świecy przy `DAY`/`WEEK`, nadpisanie złożonej świecy przez zamkniętą. Zero I/O
- [x] 6.3 Napisać `stream/upstream.py`: jedno wychodzące połączenie na `(epic, resolution)`, obie subskrypcje (`OHLCMarketData` + `marketData`), tokeny wstrzykiwane do każdej wiadomości, ping z zapasem wobec tolerancji providera, reconnect po zerwaniu, dopóki są subskrybenci
- [x] 6.4 Przepuszczać wyłącznie `priceType: "bid"` ze zdarzenia zamkniętej świecy, żeby publikowana była jedna świeca na okres
- [x] 6.5 Napisać `stream/hub.py`: pokoje kluczowane `(epic, resolution)`, rozgłaszanie, połączenie otwierane przy pierwszym subskrybencie i zamykane po odejściu ostatniego
- [x] 6.6 Testować `forming.py` w izolacji: pierwsze kwotowanie otwiera, kolejne rozciągają maksimum/minimum i przesuwają zamknięcie, nowy okres otwiera nową świecę, `DAY`/`WEEK` rozciągają zamiast otwierać, zamknięta świeca zastępuje złożoną
- [x] 6.7 Testować hub na sztucznym upstreamie: drugi subskrybent nie otwiera drugiego połączenia, ostatni odchodzący je zamyka, zerwanie publikuje `reconnecting` i wraca do publikowania

## 7. Powierzchnia HTTP i WebSocket

- [x] 7.1 Napisać `app.py`: lifespan będący właścicielem klienta i huba, handler mapujący typ błędu modułu na status, `/capabilities` podające providera, środowisko `demo`, streaming i typy zleceń
- [x] 7.2 Trasy: `/accounts`, `/accounts/active`, `/instruments`, `/instruments/search`, `/instruments/{symbol}/candles`, `/instruments/{symbol}/history`
- [x] 7.3 Trasy: `/positions`, `/orders`, `/positions/{id}` (zamknięcie, zmiana), `/working-orders`, `/working-orders/{id}`
- [x] 7.4 WebSocket `/ws/stream?symbol=&resolution=` — odmówić połączenia niewskazującego symbolu
- [ ] 7.5 Test: publikowane OpenAPI pokrywa każdą trasę; strumień bez symbolu jest odrzucany; żadna odpowiedź ani wiadomość nie niesie poświadczenia ani tokenu providera

## 8. Weryfikacja i dokumentacja

- [ ] 8.1 Test dymny na żywo za flagą `--run-live`: sesja się otwiera, głęboki odczyt stronicuje, strumień dostarcza kwotowania i zamkniętą świecę
- [ ] 8.2 Przepuścić `ruff` i pełny zestaw testów na czysto
- [ ] 8.3 Napisać README modułu — co / uruchomienie / testy / kontrakt — na jeden ekran, razem z kształtami wiadomości WebSocketa
- [ ] 8.4 Napisać README repozytorium i `docs/architecture.md` ustanawiające układ `modules/`
