## 1. Bramka: odnowiona sesja wraca na swoje konto (D3)

- [x] 1.1 `CapitalClient` zna konto docelowe; `_login` przywraca je przed zakończeniem zadania logowania, a odmowa przełączenia kończy logowanie błędem
- [x] 1.2 `set_active_account` ustawia konto docelowe sesji domyślnej
- [x] 1.3 Test jednostkowy (respx): 401, ponowne logowanie na koncie preferowanym, przełączenie i ponowienie na właściwym koncie; wspólne logowanie dla wielu czekających
- [x] 1.4 Test `--run-live-trading`: pomiar 3 (świeży login ląduje na koncie preferowanym, a sesja po wymuszonym logowaniu wraca na swoje konto)

## 2. Bramka: pula sesji i nagłówek konta (D1, D2, D4)

- [x] 2.1 Jeden `RateGate` wstrzykiwany do każdego `CapitalClient`
- [x] 2.2 `SessionPool`: sesja domyślna, sesje po koncie tworzone leniwie, sprawdzanie identyfikatora na liście kont z pamięcią podręczną
- [x] 2.3 Zależność FastAPI czytająca opcjonalny `X-Capital-Account` i wybierająca adapter z puli; nieznane konto daje 400 z nazwą konta, bez logowania i bez zlecenia
- [x] 2.4 Nagłówek na `/positions`, `/orders`, `/positions/{id}` (DELETE, PUT), `/working-orders`, `/working-orders/{id}`, `/accounts/top-up`
- [x] 2.5 Strumień na własnej sesji z puli; usunięcie ostrzeżenia o zerwaniu z docstringu `PUT /accounts/active` i z README
- [x] 2.6 Testy: dwa konta jednocześnie, przełączenie aktywnego nie rusza żądania z nagłówkiem, nieznane konto, korekta salda wskazanego konta
- [x] 2.7 Testy `--run-live-trading`: pomiary 1 i 2 (konto per sesja, zlecenie niewidoczne z drugiej sesji, strumień bez przerwy przy przełączeniu)
- [x] 2.8 README bramki: sekcja o sesjach na konto i wyniki pomiarów z 28.10

## 3. trading-mcp

- [x] 3.1 Opcjonalne `account_id` w `get_positions`, `get_working_orders`, `get_balance`, `place_order`, `close_position`, `amend_stops`, `cancel_working_order`, `top_up_demo_account`, przekazywane jako `X-Capital-Account`
- [x] 3.2 `get_balance` z `account_id` czyta wskazane konto, a nie aktywne
- [x] 3.3 Konto w obu liniach `trading_mcp.trace` każdego zapisu
- [x] 3.4 Opis `switch_active_account` bez ostrzeżenia o strumieniu; w razie potrzeby świadoma korekta sufitu powierzchni narzędzi
- [x] 3.5 `scripts/contract.py` — odświeżenie snapshotu OpenAPI bramki i `check`
- [x] 3.6 Testy: konto trafia do nagłówka, brak konta to brak nagłówka, nieznane konto to odmowa, a nie awaria dostępu

## 4. teams

- [x] 4.1 `TradingLimits.account_id` (opcjonalne) w kontrakcie rewizji
- [x] 4.2 Walidacja zapisu: rewizja z kontem i `switch_active_account` albo `top_up_demo_account` u któregoś agenta jest odrzucana z nazwą narzędzia i agenta
- [x] 4.3 `assignment.py`: dla zespołu z kontem `account_id` znika ze schematu narzędzi `trading-mcp`
- [x] 4.4 Silnik: nadpisuje `account_id` kontem rewizji w każdym wywołaniu narzędzia `trading-mcp`
- [x] 4.5 Silnik: przy starcie runu zespołu z kontem `list_accounts`; nieznane konto zatrzymuje run przed pierwszym agentem z nazwą konta
- [x] 4.6 Migracja `teams`: nullable `account_id` w tabeli zleceń; `record_trade` je zapisuje, a odczyt zleceń przebiegu je zwraca
- [x] 4.7 Testy: nadpisanie konta podanego przez model, odmowa zapisu, odmowa startu, wiersz śladu z kontem (`-m db`), rewizja bez konta bez zmian
- [x] 4.8 Katalog zespołów niesie konto najnowszej rewizji (`account_id` w `TeamOut`), żeby terminal mógł ostrzec o współdzielonym koncie bez czytania definicji

## 5. Terminal

- [x] 5.1 `contract-sync` po zmianach w bramce i teams
- [x] 5.2 Edytor zespołu: wybór konta przy granicach handlowych (nazwa, waluta, saldo; pusty to konto aktywne) i ostrzeżenie, gdy konto ma już inny zespół
- [x] 5.3 Odmowa zapisu z powodu narzędzia przełączającego konto pokazana przy agencie (już działa: `locateRefusal` czyta `'agent'` z komunikatu modułu; test ogólny tego mechanizmu wystarcza)
- [x] 5.4 Ekran kont: wybór konta do oglądania pozycji bez przełączania aktywnego; tekst przed przełączeniem mówi, kogo przełączenie dotyczy
- [x] 5.5 Konto w wierszu zlecenia w śladzie przebiegu
- [x] 5.6 Testy widoków: przypisanie konta (happy path), odmowa przy agencie, oglądanie innego konta bez przełączenia

## 6. Zamknięcie

- [x] 6.1 `openspec validate team-trades-on-its-own-account --strict`
- [x] 6.2 Aktualizacja `docs/demo-wiele-kont-rownolegle.html` o stan po wdrożeniu
- [x] 6.3 Po wdrożeniu: dwa zespoły na random i devtest biegną jednocześnie, a każde konto pokazuje wyłącznie swoje pozycje
