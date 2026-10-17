## Context

Brama (`modules/workbench/telegram_gateway`) ma już boty, adresatów, wiązanie tapnięciem i rozmowę z
botem-twórcą przez Telethon (`creator.py`); sesja konta to dziś string w `TELEGRAM_SESSION`, a trzej
producenci wysyłają do jednego adresata z `ALERT_DESTINATION`. Workbench to jeden proces uvicorn z
jednym workerem (`Dockerfile`), jedna replika w Compose. Zrzut każdej bazy, `telegram` włącznie,
codziennie trafia na komputer operatora (`deploy/scripts/backup.sh`).

## Goals / Non-Goals

**Goals:** producent nie zna adresata; operator przepina cele bez wdrożenia; sesja konta w zrzucie
jest bezużyteczna bez serwera.

**Non-Goals:** reguły alertów u producentów (alert ceny, news) — ta zmiana daje im cel, nie regułę;
narzędzie MCP wyliczające cele (spec na nie pozwala, nikt go dziś nie potrzebuje); szyfrowanie
tokenów botów; kolejka i historia wiadomości — `telegram-gateway-delivery` zostaje.

## Decisions

**1. Otwarty cel z rozstrzyganiem przedrostkiem, nie zamknięty katalog i nie reguły w bramie.**
Producent podaje cel kropkowany, a ostatni segment niesie źródło: `youtube.film.<kanał>`,
`social.post.<autor>`, `strategy.setup`, w przyszłości `market.price.<instrument>`. Przypisanie
`youtube.film` łapie wszystkie kanały, `youtube.film.<kanał>` przepina jeden, `*` łapie wszystko inne.
Rozważone: zamknięty katalog deklarowany w kodzie (każdy nowy rodzaj zdarzenia to zmiana bramy —
dokładnie to, czego operator nie chce) i silnik reguł w bramie z filtrami po treści (brama zaczęłaby
rozumieć zdarzenia, które należą do producentów). Przedrostek daje elastyczność bez wiedzy o treści.
Segment źródła jest normalizowany po stronie producenta: małe litery, wszystko spoza `[a-z0-9_-]`
zamienione na `-`.

**2. Rejestr celów to upsert przy wysyłce plus zgłoszenie przy starcie.** Każda wiadomość z celem
aktualizuje `purposes(name, first_seen, last_seen, last_caller, description)`; pakiet może zgłosić
cel z opisem (`PUT /purposes/{name}`), żeby był w terminalu przed pierwszym zdarzeniem. Koszt: jeden
upsert po kluczu głównym na wiadomość, a wiadomości jest kilkadziesiąt na dobę — klasa C0, do
potwierdzenia `db-cost-check`. Rozważone: rejestr tylko z deklaracji (cel wymyślony przez regułę w
locie byłby niewidoczny, dopóki ktoś go nie zgłosi).

**3. `assignments(key, destination_id)` z `ON DELETE RESTRICT`.** Klucz to cel, przedrostek albo
`*`, unikalny — „jeden cel, jeden adresat” trzyma baza. `RESTRICT` sprawia, że usunięcie adresata z
przypisaniem nie uda się nawet z pominięciem sprawdzenia w kodzie; bot dalej kaskaduje na adresatów,
więc bot z przypisanym adresatem też się nie usunie. Sprawdzenie w kodzie zostaje, żeby odmowa
nazywała cele i padła **przed** rozmową z botem-twórcą. Rozstrzyganie: kandydaci to cel i jego
przedrostki po segmentach plus `*`, jedno zapytanie `WHERE key = ANY($1) ORDER BY length(key) DESC
LIMIT 1`.

**4. Sesja w bazie, szyfrowana Fernetem, nie sekret w GitHubie.** `account_session` ma jeden wiersz:
nazwa konta, zamaskowany numer, `cryptography.fernet` nad stringiem `StringSession`, kluczem
`TELEGRAM_SESSION_KEY`. Rozważone: sekret w środowisku `vps` i skrypt lokalny (bezpieczniejsze dla
konta prywatnego, ale każde ponowne logowanie to wdrożenie — przy koncie dedykowanym ta cena nic
już nie kupuje) oraz AES-GCM wprost (Fernet niesie wersję i znacznik czasu, i nie zostawia wyboru
nonce'a implementującemu). Fernet zamiast hasła wyprowadzanego, bo klucz i tak leży w środowisku.

**5. Rozpoczęte logowanie trzymane w pamięci procesu.** Między numerem a kodem Telethon potrzebuje
`phone_code_hash` i tego samego połączenia; brama trzyma jeden połączony klient przez 10 minut i
zamyka go po sukcesie, wygaśnięciu albo nowym rozpoczęciu. Bezpieczne, bo proces jest jeden. Restart
gubi logowanie, a spec mówi to wprost. Rozważone: stan w bazie (dałby przetrwanie restartu, ale
zapisałby połowę logowania w zrzucie).

**6. Rotacja przez `/revoke`.** Ta sama rozmowa co przy zakładaniu (`/revoke`, `@bot`), token z
odpowiedzi tą samą funkcją `token_in`; `getMe` nowym tokenem przed zapisem. Wiązania przeżywają, bo
`chat_id` należy do rozmowy z botem, nie do tokenu.

**7. Kod QR rysowany w terminalu.** Odnośnik niesie jednorazowy sekret, więc nie idzie do żadnej
usługi generującej obrazki; biblioteka `qrcode` w przeglądarce. Terminal odpytuje
`GET /destinations/{name}` co 3 s, tylko dopóki odnośnik jest otwarty i karta widoczna — C0.

**8. Terminal na liście REST bramy, obok `az`.** `TELEGRAM_REST_CALLER_APPLICATION_IDS` dostaje
`TERMINAL_APPLICATION_ID`, jak już ma `YOUTUBE_REST_CALLER_APPLICATION_IDS`. Do terminala loguje się
tylko operator, więc to nie poszerza kręgu ludzi, tylko daje mu ekran.

## Risks / Trade-offs

- [Świeże konto logujące się z IP serwerowni może zostać ograniczone przez Telegram] → konto używane
  kilka dni z telefonu przed pierwszym logowaniem z serwera, 2FA od razu; odmowa Telegrama dociera
  do ekranu jego słowami.
- [Utrata `TELEGRAM_SESSION_KEY` albo jego zmiana] → sesja staje się nieczytelna, a stan to mówi;
  koszt to jedno ponowne logowanie, wysyłka nie staje.
- [Klucz i zrzut leżą razem, gdy ktoś ma serwer] → poza zasięgiem tej zmiany: kto ma serwer, ma też
  tokeny botów. Szyfrowanie chroni zrzut na komputerze operatora, nie serwer.
- [Cel bez adresata wstrzymuje alerty bez hałasu] → licznik celów bez adresata w `/state` i
  wyróżnienie w zakładce; producenci nie stawiają znacznika, więc przypisanie później dostarcza
  zaległe w ich limitach (10 postów na przebieg, okno 48 h filmów).
- [Literówka w przedrostku łapie nie to, co trzeba] → zakładka pokazuje przy każdym celu przypisanie,
  z którego dziś bierze adresata.

## Migration Plan

1. Migracja `0002`: `purposes`, `assignments`, `account_session`. Przy starcie, po migracji, jeżeli
   `ALERT_DESTINATION` jest ustawione, nie ma jeszcze przypisania `*`, a adresat o tej nazwie istnieje,
   brama zasiewa `*` — jedyne miejsce, w którym czyta to ustawienie. W starcie, nie w migracji, bo
   migracja nie widzi ustawień procesu, a zasiew ma być idempotentny przy każdym starcie.
2. Producenci przechodzą na cel w tym samym wdrożeniu; dzięki zasianemu `*` alerty idą tam, gdzie
   szły.
3. Po zielonym wdrożeniu i sprawdzeniu `*` w terminalu: `ALERT_DESTINATION` i `TELEGRAM_SESSION`
   znikają z Compose, `assemble_env.py` i środowiska `vps`, a trafiają do `RETIRED_SETTINGS`.
4. Operator: konto dedykowane, `api_id`/`api_hash` z niego, `TELEGRAM_SESSION_KEY`
   (`Fernet.generate_key()`) w `vps`, logowanie w zakładce, nowe boty, rotacja albo usunięcie starych.

Cofnięcie: obraz sprzed zmiany ignoruje nowe tabele, a `ALERT_DESTINATION` jest jeszcze w środowisku
aż do kroku 3 — dlatego krok 3 jest osobnym wdrożeniem.
