## 1. Schemat i cele

- [x] 1.1 Migracja `0002`: `purposes`, `assignments` (`key` unikalny, `ON DELETE RESTRICT`); `account_session` jest w migracji `0003` (grupa 2); zasianie `*` z `ALERT_DESTINATION` przy starcie (`seed_default_assignment`), nie w migracji — migracja nie widzi ustawień procesu; testy `-m db`
- [x] 1.2 Walidacja kształtu celu i kandydaci przedrostkowi — testy jednostkowe (segmenty, `market.price` ≠ `market.prices`, `*`)
- [x] 1.3 `store`: upsert celu przy wysyłce, zgłoszenie z opisem, rozstrzygnięcie jednym zapytaniem, CRUD przypisań, liczba celów bez adresata; `db-cost-check` dla upsertu i rozstrzygnięcia
- [x] 1.4 `POST /messages` przyjmuje dokładnie jedno z `destination` / `purpose`; odmowa `unassigned` odróżnialna od reszty; odpowiedź nazywa adresata
- [x] 1.5 REST: `GET /purposes`, `PUT /purposes/{name}`, `GET /assignments`, `PUT` / `DELETE /assignments/{key}`; odmowa usunięcia bota i adresata z przypisaniem, z nazwami celów, przed botem-twórcą
- [x] 1.6 `GET /state`: konto, klucz sesji, przypisanie domyślne, cele bez adresata
- [x] 1.7 Test powierzchni narzędziowej: brak narzędzi przypisań, konta i rotacji

## 2. Konto-właściciel

- [x] 2.1 `cryptography` w `pyproject.toml`; `TELEGRAM_SESSION_KEY` w `config.py` (walidacja klucza Fernet, pusty = brak); `TELEGRAM_SESSION` przestaje być czytane
- [x] 2.2 Logowanie w pamięci: `POST /account/login` (numer), `/account/login/code`, `/account/login/password`; jedno naraz, 10 minut, odmowy słowami Telegrama
- [x] 2.3 Zapis zaszyfrowanej sesji, nazwa konta i zamaskowany numer; nieczytelna albo odrzucona sesja jako stan
- [x] 2.4 `DELETE /account`: `log_out()` u Telegrama, usunięcie z bazy mimo jego niedostępności, odpowiedź mówiąca, co się nie udało
- [x] 2.5 `creator.py` bierze sesję z bazy zamiast z ustawień; `RedactTokens` obejmuje kod, hasło, sesję i klucz — test logu nieudanego logowania
- [x] 2.6 `POST /bots/{username}/token` — rotacja przez `/revoke`, `getMe` nowym tokenem przed zapisem; test, że adresat dalej odbiera

## 3. Producenci

- [x] 3.1 `social_data/alerts.py`: cel `social.post.<autor>`, zgłoszenie `social.post` przy starcie, `unassigned` bez znacznika, stan mówi „cel bez adresata”
- [x] 3.2 `strategy/alerts.py`: to samo z `strategy.setup`
- [x] 3.3 `youtube_data/alerts.py`: `youtube.film.<kanał>`, zgłoszenie `youtube.film`; reguły `always`/`threshold`/`never` bez zmian
- [x] 3.4 Normalizacja segmentu źródła jako funkcja każdego producenta z osobna (bez wspólnego importu); jeden test na producenta
- [x] 3.5 `workbench/config.py`: `alert_destination` znika z ustawień pakietów; `alerts_configured` zastąpione odpowiedzią bramy

## 4. Terminal

- [x] 4.1 `telegram_gateway/contract.py` i `openapi.py` obejmują nowe trasy; siódmy kontrakt terminala; `contract-sync`
- [x] 4.2 Zakładka `src/telegram/`: stan i pierwsze kroki, sekcja konta z ostrzeżeniem o koncie dedykowanym i krokiem hasła
- [x] 4.3 Boty: założenie / wklejenie tokenu, licznik wobec sufitu, rotacja i usunięcie z potwierdzeniem
- [x] 4.4 Aktywacja: odnośnik i QR (`qrcode` w przeglądarce), odpytywanie co 3 s tylko przy otwartym odnośniku i widocznej karcie, wygaśnięcie i nowy odnośnik
- [x] 4.5 Cele: adresat dziś, przypisanie, z którego pochodzi, przypisz / przepnij / zdejmij dla celu, przedrostka i `*`; wyróżnienie celów bez adresata
- [x] 4.6 Testy według reguły CRUD (szczęśliwa ścieżka, błąd, odmowa) na zakładkę; rozstrzyganie „skąd adresat” jako test jednostkowy funkcji, nie DOM

## 5. Wdrożenie

- [x] 5.1 `deploy/docker-compose.yml`: `TERMINAL_APPLICATION_ID` w `TELEGRAM_REST_CALLER_APPLICATION_IDS`, `TELEGRAM_SESSION_KEY`; `assemble_env.py` (opcjonalne), `fill-github-environment.sh`, `.env.example` workbencha
- [x] 5.2 `telegram_gateway/README.md` przepisany pod VPS i terminal (zamiast `curl` z `az`)
- [ ] 5.3 Merge, `deploy-watch`, potem w terminalu: przypisanie `*` zasiane, alert dochodzi
- [ ] 5.4 Drugie wdrożenie: `ALERT_DESTINATION` z Compose, `assemble_env.py`, `vps`, `.env.example` i z `seed_default_destination`; do `RETIRED_SETTINGS` w `scripts/dev.py` (`TELEGRAM_SESSION` zdjęte już w 5.1 — nic go nie czytało)
- [ ] 5.5 Operator: konto dedykowane z 2FA, `api_id`/`api_hash` z niego w `vps`, `TELEGRAM_SESSION_KEY`; logowanie w zakładce, nowy bot, aktywacja, przypisania; stare boty zrotowane albo usunięte
- [x] 5.6 `review.md`
