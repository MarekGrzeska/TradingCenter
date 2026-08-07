## 1. Szkielet modułu

- [x] 1.1 Utwórz `modules/market-data/` z `pyproject.toml`, `README.md` i `.env.example` wzorowanymi na `capital-gateway`
- [x] 1.2 Dodaj zależności: `fastapi`, `uvicorn`, `httpx`, `websockets`, `pydantic-settings`, `asyncpg`, `alembic`
- [x] 1.3 Napisz `config.py` — adres gatewaya, połączenie do bazy, limit śledzonych par, równoległość uzupełnień, domyślna głębokość historii
- [x] 1.4 Dodaj `pytest` z `docker`-owym Postgresem dla testów integracyjnych i sprawdź, że pusta suita przechodzi

## 2. Schemat bazy

- [x] 2.1 Migracja: tabela świec z kluczem (symbol, rozdzielczość, początek okresu) i jawną kolumną strony ceny
- [x] 2.2 Migracja: tabela śledzonych par z trwałym stanem i znacznikiem dodania
- [x] 2.3 Migracja: tabela zakresów pokrycia wraz z flagą „historia providera się skończyła"
- [x] 2.4 Test: powtórny zapis tej samej trójki nadpisuje wpis i nie tworzy duplikatu
- [x] 2.5 Test: zapis świecy w budowie jest odrzucany na poziomie warstwy dostępu do danych

## 3. Odczyt z gatewaya

- [x] 3.1 Klient HTTP do `/instruments/{symbol}/history` z mapowaniem `CandleHistory` na model wewnętrzny
- [x] 3.2 Klient WebSocket do `/ws/stream` z rozpoznaniem wiadomości świecy, kwotowania, statusu i błędu
- [x] 3.3 Sprowadzenie znaczników czasu do jednej postaci — ISO z historii i epoka ze strumienia na wspólny początek okresu
- [x] 3.4 Test: świeca z historii i świeca ze strumienia dla tego samego okresu mają identyczny znacznik czasu

## 4. Archiwum

- [x] 4.1 Zapis świecy zamkniętej z nadpisaniem wpisu o tej samej trójce
- [x] 4.2 Reguła autorytatywności: wartość z odczytu historii wygrywa z wartością ze strumienia
- [x] 4.3 Odczyt zakresu świec uporządkowany od najstarszej, bez powtórzeń
- [x] 4.4 Zapis i odczyt zakresów pokrycia, w tym granica wynikająca z `history_ended`
- [x] 4.5 Rozstrzyganie „rynek zamknięty" kontra „brak danych" na podstawie pokrycia
- [x] 4.6 Test: brak świecy wewnątrz pokrycia jest raportowany inaczej niż brak poza pokryciem

## 5. Rozdzielczości pochodne

- [x] 5.1 **Zweryfikuj empirycznie**, czy provider kotwiczy `HOUR_4` na północy UTC — wylicz próbkę z serii minutowej i porównaj ze świecami pobranymi z gatewaya
- [x] 5.2 Rollupy dla `MINUTE_5`, `MINUTE_15`, `MINUTE_30`, `HOUR`, `HOUR_4` (tabela, nie widok materializowany — patrz `design.md`)
- [x] 5.3 Przyrostowe odświeżanie po zamknięciu okresu
- [x] 5.4 Oznaczanie świecy powstałej z niepełnego okresu
- [x] 5.5 Test: wyliczona świeca ma otwarcie pierwszej, maksimum i minimum wszystkich, zamknięcie ostatniej

## 6. Śledzone pary

- [ ] 6.1 Dodanie pary z walidacją symbolu przez gateway i sprawdzeniem limitu
- [ ] 6.2 Usunięcie pary zatrzymujące zbieranie i zachowujące dane
- [ ] 6.3 Odczyt listy wraz ze stanem połączenia i czasem najnowszej świecy
- [ ] 6.4 Wykrywanie „zbieranie ustało" — najnowsza świeca starsza niż dwa okresy przy otwartym rynku
- [ ] 6.5 Test: konfiguracja przeżywa restart modułu
- [ ] 6.6 Test: dodanie ponad limit kończy się odmową z podaniem powodu

## 7. Ingest

- [ ] 7.1 Nasłuch na żywo z subskrypcją na śledzoną parę i zapisem świec zamkniętych
- [ ] 7.2 Wznawianie subskrypcji z rosnącym odstępem, dopóki para jest śledzona
- [ ] 7.3 Uzupełnianie wstecz przez `/history`, bez własnego stronicowania
- [ ] 7.4 Domknięcie luki przy starcie modułu dla każdej śledzonej pary
- [ ] 7.5 Domknięcie luki po wznowieniu zerwanej subskrypcji
- [ ] 7.6 Ograniczenie równoległości uzupełnień, żeby nie zagłodzić ruchu interaktywnego
- [ ] 7.7 Raportowanie postępu i przyczyn niepowodzeń, czytelne dla operatora
- [ ] 7.8 Test: start po przerwie dociąga brakujący przedział; start bez przerwy nie wysyła żądań

## 8. Kontrakt modułu

- [ ] 8.1 `GET` świec po zakresie czasu z rozdzielczością i stroną ceny w odpowiedzi
- [ ] 8.2 Oznaczanie części żądanego przedziału, która nie jest pokryta
- [ ] 8.3 Subskrypcja WebSocket ze snapshotem jako pierwszą wiadomością, czytanym w jednej transakcji z dopięciem odbiorcy
- [ ] 8.4 Rozgłaszanie zmian po snapshocie, z jawnym oznaczeniem świecy zamkniętej i w budowie
- [ ] 8.5 `GET` pokrycia pary
- [ ] 8.6 Zarządzanie śledzonymi parami przez kontrakt
- [ ] 8.7 Błędy nazywające przyczynę, bez surowych błędów bazy i bez poświadczeń
- [ ] 8.8 OpenAPI dla tras HTTP i opis wiadomości WebSocket w `README.md`, z testem pilnującym, że ścieżka WS jest nieobecna w schemacie
- [ ] 8.9 Test: subskrypcja nieśledzonej pary jest odrzucana
- [ ] 8.10 Test: snapshot i kolejne zmiany nie tworzą duplikatu świecy tego samego okresu

## 9. Terminal — źródło składane

- [ ] 9.1 Implementacja `MarketDataSource` czytająca świece i strumień z archiwum
- [ ] 9.2 Złożenie w `marketData.ts`: świece z archiwum, instrumenty z gatewaya, jedna instancja na aplikację
- [ ] 9.3 Obsługa snapshotu w `useBarFeed` — zastąpienie dotychczasowego zszywania historii ze strumieniem
- [ ] 9.4 Usunięcie dociągania luki po stronie terminala, skoro przynosi ją snapshot
- [ ] 9.5 Rozróżnienie stanów: archiwum nieosiągalne kontra gateway nieosiągalny
- [ ] 9.6 Test: wykres, siatka i wyszukiwarka działają bez zmian w swoim kodzie
- [ ] 9.7 Test: gdy archiwum nie odpowiada, wyszukiwarka instrumentów działa dalej

## 10. Terminal — panel konfiguracji

- [ ] 10.1 Nowa zakładka w rejestrze, z własną ścieżką
- [ ] 10.2 Lista archiwizowanych par ze stanem zbierania i czasem najnowszej świecy
- [ ] 10.3 Dodawanie pary: wybór instrumentu z wyszukiwarki plus rozdzielczość
- [ ] 10.4 Pokazanie powodu, gdy archiwum odmawia dodania
- [ ] 10.5 Wyróżnienie pary, dla której zbieranie ustało
- [ ] 10.6 Podgląd pokrycia wybranej pary
- [ ] 10.7 Zdejmowanie pary z potwierdzeniem i informacją, że dane zostają
- [ ] 10.8 Odróżnienie pustej listy od nieosiągalnego archiwum
- [ ] 10.9 Test: dodanie i zdjęcie pary odzwierciedla się na liście

## 11. Domknięcie

- [ ] 11.1 `README.md` modułu: co, jak uruchomić, jak testować, kontrakt — na jeden ekran
- [ ] 11.2 `docs/architecture.md` i `README.md` repozytorium: moduł w tabeli i na rysunku
- [ ] 11.3 Uruchom pełną suitę obu modułów i terminala, zanotuj polecenie i wynik
- [ ] 11.4 Przejdź ręcznie ścieżkę: dodaj parę w panelu, poczekaj na świece, otwórz wykres, zrestartuj moduł, sprawdź domknięcie luki
- [ ] 11.5 Napisz `review.md` — dwa przejścia wymagane przez schemat, przed archiwizacją zmiany
