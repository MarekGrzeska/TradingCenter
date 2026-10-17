## Why

Wszystko, co brama Telegrama umie — założyć bota, związać adresata, wysłać — operator robi dziś
`curl`-em z tokenem z `az`, a o tym, kto dostaje alerty, decyduje jedno ustawienie
`ALERT_DESTINATION`, wspólne dla każdego pakietu. Operator chce, żeby bot mógł mówić o **dowolnej**
rzeczy — alercie ceny, który sam ustawi, nowym filmie na kanale, poście, newsie giełdowym — i żeby
o tym, który bot mówi o czym, decydował w terminalu, bez wdrożenia i bez edycji `.env`. Wiadomość
nadawana nazwą adresata przez każdego producenta z osobna tego nie uniesie: każdy nowy rodzaj
zdarzenia byłby nowym ustawieniem.

## What Changes

- **Cel zamiast adresata u producenta.** Pakiet wysyła `{purpose, text}`; brama sama wybiera
  adresata z przypisania. Cel jest **otwartą** nazwą kropkowaną (`youtube.film`,
  `market.price.eurusd`), którą producent może wymyślić w chwili wysyłki — reguła ustawiona przez
  operatora może nieść własną. Brama zapamiętuje każdy cel, jaki zobaczyła, i pokazuje go w terminalu.
- **Przypisanie: jeden cel → jeden adresat**, rozstrzygane od najdłuższego pasującego przedrostka
  (`youtube.film` → `youtube` → domyślne `*`). Nowy rodzaj zdarzenia trafia więc gdzieś od razu,
  a operator może go przepiąć, kiedy zechce. Cel bez przypisania to osobna odpowiedź, nie błąd.
- **Adresowanie nazwą zostaje** dla rozmowy i zespołów — model decyduje sam, komu pisze.
- **`ALERT_DESTINATION` odchodzi** (**BREAKING** dla `.env`): przy pierwszym starcie po zmianie
  zasiewa przypisanie domyślne, potem trafia do `RETIRED_SETTINGS`.
- **Konto-właściciel botów jest osobnym, dedykowanym kontem Telegrama**, nie prywatnym kontem
  operatora. Operator loguje je z terminala (numer → kod → hasło 2FA); sesja leży w bazie
  `telegram` **zaszyfrowana** kluczem `TELEGRAM_SESSION_KEY` ze środowiska `vps`, więc nocny zrzut
  bez klucza jej nie zdradza. Wylogowanie unieważnia ją po stronie Telegrama.
  `TELEGRAM_SESSION` w env odchodzi; `TELEGRAM_API_ID` / `_API_HASH` zostają.
- **Rotacja tokenu bota** przez `/revoke` u bota-twórcy — wiązania adresatów przeżywają.
- **Nowa zakładka terminala „Telegram”**: konto, lista botów (założenie, wklejenie tokenu,
  rotacja, usunięcie), aktywacja adresata odnośnikiem i kodem QR z czekaniem na tapnięcie, cele i
  ich przypisania. Terminal dołącza do listy wołających REST bramy, obok `az`.
- **Usunięcie bota albo adresata, na którym wisi przypisanie, jest odmową** nazywającą te cele.

Poza zakresem: same reguły alertów (alert ceny, news) — to zmiany producentów, które ta zmiana
umożliwia; szyfrowanie tokenów botów w bazie; dwustronna rozmowa przez Telegram; wiele adresatów
na jeden cel. `review.md` powstanie po zadaniach, bo zmiana dotyka sekretu konta.

## Capabilities

### New Capabilities
- `telegram-gateway-purposes`: cel, jego rejestr, przypisanie do adresata i rozstrzyganie przedrostkiem.
- `telegram-gateway-account`: logowanie konta-właściciela z terminala, sesja zaszyfrowana w bazie, wylogowanie.
- `terminal-telegram`: zakładka terminala nad bramą.

### Modified Capabilities
- `telegram-gateway-delivery`: wiadomość adresowana nazwą **albo** celem.
- `telegram-gateway-bots`: sesja z logowania zamiast z ustawienia; rotacja tokenu; usunięcie bota z przypisaniem jest odmową.
- `telegram-gateway-upstream-access`: sesja konta służy także logowaniu, wylogowaniu i rotacji; zawsze konto dedykowane.
- `telegram-gateway-destinations`: usunięcie adresata z przypisaniem jest odmową.
- `telegram-gateway-api`: trasa stanu mówi, czyje jest konto i ile celów nie ma adresata.
- `social-data-alerts`, `strategy-alerts`: „brak bramy” staje się „cel bez adresata”.

## Impact

- **Kod**: `modules/workbench/telegram_gateway/` (cele, przypisania, konto, rotacja, kontrakt),
  migracja `migrations/telegram/versions/0002_*`; `social_data/alerts.py`, `strategy/alerts.py`,
  `youtube_data/alerts.py` i ich `config.py`; `workbench/config.py`; `scripts/dev.py`
  (`RETIRED_SETTINGS`). Zależność `cryptography` w workbenchu.
- **Terminal**: nowy kontrakt generowany z `telegram_gateway/contract.py` (siódmy), zakładka
  `src/telegram/`; `contract-sync`.
- **Wdrożenie**: `deploy/docker-compose.yml` (terminal w `TELEGRAM_REST_CALLER_APPLICATION_IDS`,
  `TELEGRAM_SESSION_KEY`, bez `ALERT_DESTINATION` i `TELEGRAM_SESSION`), `deploy/env.required`,
  `assemble_env.py`, `fill-github-environment.sh`.
- **Otwarta zmiana `add-youtube-archive`**: jej delta `youtube-data-alerts` mówi o adresacie —
  wyrównana przy jej archiwizacji, nie tutaj.
- **Operator**: nowe konto Telegrama z własnym numerem i 2FA, `api_id`/`api_hash` z
  my.telegram.org z tego konta, wygenerowany `TELEGRAM_SESSION_KEY` w `vps`.
