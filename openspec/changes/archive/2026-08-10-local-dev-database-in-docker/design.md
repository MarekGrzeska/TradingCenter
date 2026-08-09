## Context

`db.py` ma już dwa tryby połączenia: z `user` pobiera token Entra przy każdym fizycznym
połączeniu, bez `user` używa `DATABASE_URL` dosłownie — z tego drugiego od początku korzystają
testy na testcontainers. Zmiana nie dodaje więc mechanizmu połączenia; zmienia to, co
`config.py` uznaje za poprawną konfigurację, oraz to, co skrypty deweloperskie uruchamiają
i czego pilnują.

## Goals / Non-Goals

**Goals**

- Świeży checkout z Dockerem startuje lokalnie bez ani jednej wartości z `terraform output`.
- Pomyłkowe skierowanie lokalnego modułu na produkcję jest odrzucane przy starcie, a nie
  wykrywane po fakcie.
- Ścieżka produkcyjna — App Service, tożsamość zarządzana, TLS — niezmieniona co do bajta
  konfiguracji (`infra/app-service.tf` ustawia `DATABASE_USER`, więc wybiera tryb tożsamości).

**Non-Goals**

- Zmiany w capital-gateway i terminalu — nie dotykają bazy.
- Migracja danych z `market_data_dev` — baza dev jest z definicji odtwarzalna.
- Zdejmowanie reguły firewalla na IP operatora — wciąż potrzebna do migracji produkcyjnych
  i DBeavera.

## Decisions

**Tryb wybiera `DATABASE_USER`, nie nowa zmienna.** Zmienna już rozdziela te światy:
produkcja ustawia ją w Terraformie, testy jej nie ustawiają. Osobny przełącznik
(`DATABASE_MODE=...`) byłby drugim źródłem prawdy o tym samym.

**Tryb bez tożsamości działa wyłącznie na pętli zwrotnej.** To jest właściwy strażnik — mocniejszy
niż dotychczasowa kontrola nazwy bazy w `dev.sh`. Dotąd przed produkcją chronił grep w skrypcie;
teraz chroni walidator w module: bez tożsamości nie da się w ogóle zestawić połączenia poza
maszynę. Zamyka to też ryzyko, którego kontrola nazwy nie widziała: `DefaultAzureCredential`
na maszynie operatora znajduje jego sesję `az login` — tożsamość administratora Postgresa,
która omija każdy GRANT. Po tej zmianie tryb tożsamości wymaga jawnego `DATABASE_USER`,
a tryb bez niego nie wyjdzie poza localhost.

**TLS pozostaje bezwzględny dla bazy zdalnej, na pętli zwrotnej nie obowiązuje.** Uzasadnienie
wymagania („ruch przechodzi przez sieć, której moduł nie kontroluje") na pętli zwrotnej po
prostu nie zachodzi. Warunek w spec zostaje zawężony, nie usunięty.

**`compose.yaml` wraca z historii zamiast powstawać na nowo.** Wersja skasowana przy przejściu
na Azure (rodzic `531bd04`) miała przemyślane detale, które łatwo zgubić: port 55432 z dala od
pasma Postgres.app, bind na `127.0.0.1` (baza z opublikowanym hasłem nie może słuchać na wifi
w kawiarni), healthcheck nazywający użytkownika i bazę (goły `pg_isready` odpowiada przed
końcem pierwszego bootstrapu), nazwany wolumen odporny na `docker compose down`. Wraca w
całości, ze zaktualizowanym nagłówkiem.

**Strażnik w skryptach pilnuje hosta, nie nazwy bazy.** Kontrola „nazwa musi być
`market_data_dev`" traci sens, gdy jedyna baza w Azure to produkcyjna. Nowa kontrola —
host musi być pętlą zwrotną — jest tym samym warunkiem, który wymusza moduł; skrypt
powtarza go tylko po to, by odmówić wcześniej i czytelniej (przed uruchomieniem czegokolwiek,
z komunikatem wskazującym `.env`).

**Dev-owy service principal i baza `market_data_dev` znikają z Terraforma.** Oba istniały
wyłącznie dla pracy lokalnej. SP z sekretem to dokładnie ta rotacja, którą audyt wskazał jako
koszt stały. Skasowanie bazy przy `apply` jest destrukcyjne — dane dev są odtwarzalne, ale
decyzję podejmuje operator w momencie apply, nie ten dokument. CI robi wyłącznie `plan`,
więc PR pokaże oba destroy jako diff do przeczytania.

## Risks / Trade-offs

- **Dryf schematu między kontenerem a Azure** — wersja obrazu (`postgres:17-alpine`) jest
  przypięta w `compose.yaml` obok wersji serwera w `infra/database.tf`; testy `db` w CI dalej
  chodzą na tym samym obrazie, więc rozjazd wyszedłby w testach, nie na produkcji.
- **Docker wraca jako wymaganie dev** — świadomie: był już wymagany do testów `db`, więc
  na maszynie deweloperskiej i tak jest.
- **`az login` operatora wciąż sięga produkcji przez psql/DBeaver** — to narzędzia
  operatorskie, poza zasięgiem tej zmiany; moduł uruchomiony lokalnie już nie.

## Migration Plan

1. Wejście zmiany: kod, skrypty, dokumentacja (ten PR).
2. Operator: `docker compose up -d db` albo po prostu `./scripts/dev.sh`; w
   `modules/market-data/.env` podmienia `DATABASE_URL` na lokalny i czyści
   `DATABASE_USER`/`AZURE_*`.
3. Operator, osobno i świadomie: `terraform apply` w `infra/` — destroy dev-SP i bazy dev.
   Do tego czasu oba żyją w Azure nieużywane; nic nie pęka.

## Open Questions

— brak.
