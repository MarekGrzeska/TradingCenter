## 1. `market-data`: bilety i strażnik strumienia

Idzie pierwsze i w całości lokalnie. Ścieżka strumienia nie może wyjść spod Easy Auth (grupa 2),
zanim moduł nie zacznie sprawdzać biletów — inaczej powstaje otwarty WebSocket w internecie.

- [x] 1.1 Dodaj do `config.py` czas ważności biletu (domyślnie 30 s) oraz przełącznik „stoję za
      warstwą uwierzytelniającą"; przełącznik domyślnie wyłączony, w Azure włączany ustawieniem
      aplikacji — `stream_ticket_ttl_seconds` i `require_authenticated_principal`
- [x] 1.2 Napisz magazyn biletów: losowa wartość nieodgadywalna (`secrets.token_urlsafe`), zapis
      `bilet → (tożsamość, moment wygaśnięcia)`, zdjęcie przy użyciu, sprzątanie wygasłych przy
      okazji. Komentarz przy magazynie MUST mówić wprost, że jednoinstancyjność jest założeniem
      i co się psuje przy `worker_count > 1` (design.md, „Bilety żyją w pamięci procesu")
- [x] 1.3 Dodaj trasę wydającą bilet: czyta tożsamość wstrzykniętą przez Easy Auth
      (`X-MS-CLIENT-PRINCIPAL-ID`), zwraca bilet i czas jego ważności. Z włączonym przełącznikiem
      z 1.1 brak tożsamości to odmowa `401` bez utworzenia biletu
- [x] 1.4 Wepnij sprawdzenie biletu w handshake `/ws/candles`: brak, nieznany, wygasły lub zużyty
      bilet to odmowa **przed** przyjęciem połączenia i bez zapisania konsumenta do rozgłaszania
- [x] 1.5 Zadbaj, żeby odmowa z powodu biletu była odróżnialna od odmowy z powodu pary nieśledzonej
      — dwie różne przyczyny, na które konsument reaguje inaczej (`specs/market-data-browser-access`,
      „Bez ważnego poświadczenia strumień się nie zestawia")
- [x] 1.6 Sprawdź, że ani bilet, ani token konsumenta nie trafiają do logów, komunikatów błędów ani
      odpowiedzi; log odmowy niesie przyczynę, log wydania niesie sam fakt wydania. Poprawiony
      przy okazji docstring `Problem` w `contract.py`, twierdzący, że „na tej ścieżce nie ma
      żadnego poświadczenia" — od tej zmiany jest
- [x] 1.7 Testy do wszystkich wymagań `specs/market-data-browser-access/spec.md`: wydanie biletu,
      bilet użyty dwa razy, bilet wygasły, handshake bez biletu, handshake z biletem nieznanym,
      handshake z ważnym biletem dla pary nieśledzonej, odmowa wydania bez tożsamości przy włączonym
      przełączniku, wydanie bez tożsamości przy wyłączonym, brak wartości w logach
- [x] 1.8 Zaktualizuj `modules/market-data/.env.example` i `README.md` (w tym ograniczenie
      jednoinstancyjności i jego objaw)
- [x] 1.9 `ruff check` i `pytest` zielone dla modułu — 505 passed, 7 skipped. **`ruff format` nie
      jest bramką tego repozytorium** (CI uruchamia sam `ruff check`), a uruchomiony przeformatował
      28 nietkniętych plików; cofnięte. Odkryte przy pisaniu testu na higienę logów: `migrations/env.py`
      wołał `fileConfig` z domyślnym `disable_existing_loggers=True`, więc alembic uruchamiany
      w testach wyłączał **wszystkie** loggery `market_data.*` — każdy test na to, co moduł loguje,
      przechodziłby z niewłaściwego powodu. Poprawione
- [x] 1.10 Wdróż `market-data` i potwierdź, że nic nie przestało działać: `/health` odpowiada,
      strumień nadal stoi za Easy Auth — wdrożone z merge'a PR #22, obraz na App Service to
      `…:beba4a6`. Przed `apply` **oba** żądania odbijał Easy Auth (`401`, `WWW-Authenticate:
      Bearer`), co jest właśnie dowodem, że strumień był nadal przykryty. „`/health` odpowiada"
      nie da się sprawdzić z zewnątrz, bo Easy Auth odpowiada pierwszy; potwierdzone pośrednio
      w 2.9, gdzie aplikacja odpowiada na zwolnionej ścieżce

## 2. Infrastruktura: rejestracje, zwolnienie ścieżki, CORS

- [x] 2.1 Wystaw zakres `access_as_user` na rejestracji `market-data-easyauth`, nadaj jej
      `identifier_uris` — zrobione **w `app-service.tf`**, nie w `entra.tf` jak zakładało zadanie:
      tam ta rejestracja mieszka, a przenoszenie jej między plikami to szum w diffie bez zysku.
      Przy okazji `requested_access_token_version = 2`, żeby token pasował do endpointu `/v2.0`,
      którym skonfigurowany jest Easy Auth
- [x] 2.2 `infra/entra.tf`: rejestracja SPA terminala z adresem powrotnym pod adresem Static Web
      App, uprawnieniem do zakresu z 2.1 i wpisem autoryzującym ją z góry (bez ekranu zgody).
      **Adres powrotny MUSI mieć ukośnik na końcu** — provider odrzuca URI bez niego, gdy nie ma
      segmentu ścieżki, a domyślny `redirectUri` MSAL-a (`window.location.origin`) go nie ma;
      stąd jawny `redirectUri` w kodzie terminala (3.1). Wyszło z `terraform plan`
- [x] 2.3 `infra/app-service.tf`: `allowed_audiences` Easy Auth obejmuje identyfikator API,
      a lista uznanych aplikacji — klienta z 2.2. Audiencje dwie: token proszony po nazwie zakresu
      przychodzi z `api://…`, proszony jako `<client-id>/.default` — z identyfikatorem klienta
- [x] 2.4 `infra/app-service.tf`: `excluded_paths` dla **dokładnie jednej** ścieżki `/ws/candles`;
      komentarz MUST mówić, że ochronę przejmuje sprawdzenie biletu w module
- [x] 2.5 `infra/app-service.tf`: CORS na poziomie App Service z adresem Static Web App,
      `support_credentials` wyłączone. Komentarz MUST zapisać zakaz dokładania `CORSMiddleware`
      w aplikacji (podwójny nagłówek — design.md, „CORS konfigurowany na App Service")
- [x] 2.6 `infra/app-service.tf`: ustawienie aplikacji włączające przełącznik z 1.1
- [x] 2.7 `terraform fmt`, `validate`, `plan`, `apply` — wszystko czyste, `apply` wykonany na
      polecenie operatora z zapisanego planu (`plan -out` → `apply <plan>`, więc zastosowano
      dokładnie to, co przejrzano): **4 added, 2 changed, 0 destroyed**. Uwaga na przyszłość:
      `plan` w CI **nie** dostaje 403 na `azuread_application`, wbrew komentarzowi w
      `terraform.yml` — check `plan` w PR #22 przeszedł i dał ten sam wynik co lokalny.
      Komentarz opisuje stan sprzed naprawy `var.operator_object_id` i wymaga poprawki osobno
- [x] 2.8 **Zaraz po `apply`: sprawdź zapytanie wstępne** — **`200` z `Access-Control-Allow-Origin`
      i `Access-Control-Allow-Headers: authorization`. Droga główna; odwrót z `design.md`
      niepotrzebny.** Wbudowany CORS App Service faktycznie obsługuje preflight przed Easy Auth.
      **Pułapka do zapamiętania:** przez pierwsze ~60 s po `apply` ta sama próba zwracała `401`
      od Easy Auth, a `excluded_paths` też jeszcze nie działało — konfiguracja auth propaguje się
      z opóźnieniem. Sprawdzenie zrobione za wcześnie mówi „odwrót" o czymś, co działa
- [x] 2.9 Potwierdź `curl`-em, że `/ws/candles` nie jest już przechwytywane przez Easy Auth —
      potwierdzone w logach kontenera: `"WebSocket /ws/candles?symbol=US100&resolution=MINUTE" 403`,
      `connection rejected (403 Forbidden)`. To jest nasz strażnik: `websocket.close(1008)` przed
      `accept()` wychodzi na zewnątrz jako HTTP 403. `GET` na tę samą ścieżkę daje `404` z FastAPI,
      co osobno dowodzi, że odpowiada aplikacja, a nie platforma.
      **Nagłówek `x-ms-middleware-request-id` nie odróżnia Easy Auth od aplikacji** — dochodzi do
      obu; rozróżnia dopiero `401` z `WWW-Authenticate: Bearer`

## 3. `terminal`: tożsamość i bilet

- [x] 3.1 Dodaj `@azure/msal-browser`; moduł `src/auth/` opakowujący logowanie przekierowaniem,
      ciche odnawianie i pobranie tokenu dla zakresu archiwum. Pamięć podręczna w `sessionStorage`
- [x] 3.2 Konfiguracja tożsamości w `config.ts` (`VITE_ENTRA_*`) — jej **brak** oznacza pracę bez
      tokenu, nie awarię; testy jak dla pozostałych zmiennych (`config.test.ts`)
- [x] 3.3 Rozstrzygnij przekierowanie z logowania w `main.tsx`, zanim aplikacja się zamontuje —
      pierwszy render już subskrybuje świece
- [x] 3.4 `http.ts`: `jsonClient` dostaje dostawcę tokenu i dokłada `Authorization` do każdego
      żądania; `archive.ts` i `gatewaySource.ts` MUST NOT wiedzieć o tokenie
- [x] 3.5 `http.ts`: jedna ponowna próba po odmowie z powodu tożsamości, po cichym odnowieniu
      tokenu, ze strażnikiem przed pętlą „odmowa → odnowienie → odmowa"
- [x] 3.6 `archive.ts`: pobranie świeżego biletu przed **każdą** próbą zestawienia strumienia,
      w tym przed każdą próbą po zerwaniu; bilet trafia do adresu, token MUST NOT
- [x] 3.7 `socketHub.ts`: utrata tożsamości jako trzeci rodzaj niepowodzenia obok zerwania
      i odmowy dotyczącej pary — zatrzymuje ponawianie i mówi „zaloguj się"; nieudane pobranie
      biletu z innej przyczyny nadal znaczy „ponawiaj"
      (`specs/terminal-market-data/spec.md`, wymaganie zmodyfikowane)
- [x] 3.8 Powłoka pokazuje stan zalogowania obok stanu źródeł danych, z akcją logowania; stan
      „niezalogowany" MUST NOT być pokazany jako niedostępność archiwum
- [x] 3.9 `pnpm contract:generate` — trasa wydająca bilety wchodzi do kontraktu; `contract:check`
      zielony. `archive.ts` czyta bilet przez wygenerowany `StreamTicketOut`, nie przez kształt
      wpisany ręcznie
- [x] 3.10 Testy do `specs/terminal-identity/spec.md` i do zmodyfikowanego wymagania
      w `specs/terminal-market-data/spec.md`: nagłówek dokładany do każdego żądania, odmowa
      naprawiona odnowieniem, odmowa go przeżywająca, brak pętli, świeży bilet na każdą próbę,
      utrata tożsamości zatrzymuje ponawianie, brak poświadczeń w komunikatach, tryb bez
      konfiguracji
- [x] 3.11 Zaktualizuj `modules/terminal/.env.example` i `README.md` (w tym pułapka konta gościa
      B2B logującego się innym UPN-em)
- [x] 3.12 `pnpm test`, `lint`, `typecheck` zielone — 239 passed (17 plików). Zestawienie połączenia
      przestało być synchroniczne (najpierw bilet, potem socket), więc testy hubu i siatki czekają
      teraz jedno przejście pętli zdarzeń przed sięgnięciem po socket. Podwójka HTTP w `src/test/`
      przekazuje nagłówki — bez tego nie dało się sprawdzić, że token w ogóle wychodzi
- [x] 3.13 `.github/workflows/deploy-terminal.yml`: przekaż `VITE_ENTRA_*` do builda. Są to
      identyfikatory publiczne — idą jawnie albo przez `vars`, **nigdy przez `secrets`**

## 4. Wdrożenie i weryfikacja end-to-end

- [x] 4.1 Wdróż terminal i zaloguj się kontem organizacji — logowanie przeszło bez ekranu zgody
      (autoryzacja z góry działa). **Po drodze wyszedł błąd starszy niż ta zmiana:** Static Web Apps
      nie miało `navigationFallback`, więc każdy adres poza `/` był 404 od dnia pierwszego wdrożenia
      terminala. Logowanie tylko na to weszło jako pierwsze — MSAL wraca twardą nawigacją pod adres
      zakładki. Naprawione w PR #23
- [x] 4.2 Potwierdź, że wykres pokazuje świece z wdrożonego archiwum — potwierdzone w logach
      kontenera: `POST /stream-tickets 200`, a zaraz po nim
      `WebSocket /ws/candles?symbol=US100&resolution=MINUTE_5&ticket=… [accepted]`. Cały łańcuch
      token → bilet → strumień działa
- [x] 4.3 Potwierdź, że wyszukiwarka instrumentów działa — `GET /instruments?asset_class=INDICES 200`
      i `GET /asset-classes 200` w logach, czyli trasy proxujące gateway niosą token tak samo jak
      reszta
- [x] 4.4 Potwierdź, że ingest zapisuje świece do bazy w Azure — **19 880 świec** w bazie `market_data`,
      w tym po 5000 dla MINUTE_5/15/30 i 3697 dla HOUR, z zapisanym pokryciem. To backfill przy
      dodaniu pary, nie zlecenie — patrz uwaga pod grupą
- [x] 4.5 Zerwij połączenie strumieniowe i potwierdź, że wraca samo — zerwane restartem
      `market-data`, wykres wrócił bez ingerencji. Zużytego biletu archiwum by nie przyjęło, więc
      powrót jest dowodem, że próba kupiła nowy
- [x] 4.6 Potwierdź w logach App Service, że w adresach połączeń nie ma tokenu operatora — w logu
      widnieje `…&ticket=UCUWZvhpJNxnOUVjXPR8uBH2TpwK6KzGUT4ixLuCY-8` i **żadnego tokenu**. Bilet
      w logu jest dokładnie tym, co `design.md` przewidział: w chwili zapisu był już zużyty

**Znalezione przy okazji, poza zakresem tej zmiany.** Zlecenie zbierania stoi: osiem chunków
w `pending`, `min(started_at)` puste, po restarcie i po `Retry` tak samo — powtarzalnie, mimo że
pętla robocza odpytuje bazę co 5 s niezależnie od powiadomień. Wykluczone: brak uprawnień roli
aplikacyjnej (ma `UPDATE` na wszystkich tabelach) oraz zablokowane wiersze (`FOR UPDATE SKIP LOCKED`
pomijałby je po cichu — blokad nie ma). Przyczyna nierozpoznana. `JobRunner` nie był tą zmianą
ruszany, a produkcyjnie to pierwsze zlecenie w historii (`id = 1`). Do osobnej zmiany, razem z drugą
obserwacją: **logi `INFO` modułu nie docierają na produkcji nigdzie** — ani do stdout, ani do
Application Insights (root logger stoi na `WARNING`) — więc linia `chunk N done: wrote X candles`
jest niewidoczna, a „stoi" wygląda identycznie jak „działa i nie widać".

## 5. Domknięcie

- [ ] 5.1 Wprowadź `docs/terminal-market-data-auth.html` do repozytorium jako zapis decyzji,
      z dopiskiem, która opcja została wybrana i w jakiej zmianie zrealizowana
- [ ] 5.2 Zdejmij nieaktualny komentarz w `infra/app-service.tf` przy `unauthenticated_action`
      („Client-side handling of the 401 … flagged here, not solved here") — właśnie przestał być
      prawdą — i zaktualizuj komentarz o CORS w `deploy-terminal.yml`
- [ ] 5.3 Zamknij zadanie 11.4 w `openspec/changes/provision-azure-platform/tasks.md`, wskazując
      tę zmianę jako to, czego brakowało
- [ ] 5.4 `openspec validate authenticate-terminal-to-market-data --strict`, a następnie `review.md`
      wg szablonu projektu
