## Why

`terminal` i `market-data` są wdrożone i każdy z osobna odpowiada, a mimo to wykres nie zobaczy ani
jednej świecy. Terminal stoi pod `*.azurestaticapps.net`, `market-data` pod `*.azurewebsites.net`,
a ciasteczko Easy Auth jest wystawione dla tego drugiego adresu — przeglądarka celowo nie dokłada
go do żądań między obcymi stronami (`SameSite`). `market-data` widzi żądanie bez tożsamości
i odpowiada `401`, dokładnie tak, jak został skonfigurowany.

Drugi problem jest twardszy od pierwszego: świece płyną WebSocketem, a przeglądarkowe API
WebSocketu nie pozwala ustawić żadnego nagłówka. Tokenu nie ma tam gdzie włożyć — i nie jest to
brak w naszym kodzie, tylko brak tej funkcji w każdej przeglądarce.

Analiza czterech dróg wyjścia i uzasadnienie wyboru: `docs/terminal-market-data-auth.html`.
Wybrana została **opcja B**, bo jako jedyna tania zostawia `market-data` czystym API chronionym
tokenem — czyli w formie, której potrzebuje każdy przyszły konsument niebędący przeglądarką (ten
nie ma żadnego z opisanych problemów: bierze token tożsamości zarządzanej i wysyła go w nagłówku),
i w której moduł już dziś jest.

Zamyka to zadanie 11.4 zmiany `provision-azure-platform` — ostatnie otwarte w tamtej zmianie — oraz
kwestię odłożoną wprost w komentarzu `infra/app-service.tf` przy `unauthenticated_action =
"Return401"` („Client-side handling of the 401 … is application work, not infrastructure — flagged
here, not solved here").

## What Changes

### Terminal zdobywa tożsamość, zamiast liczyć na ciasteczko

- **Nowa rejestracja aplikacji Entra typu SPA** dla terminala. Osobna od `market-data`, bo to
  osobny podmiot: przeglądarka jest klientem, `market-data` jest API. Rejestracja `market-data`
  zyskuje wystawiony zakres (`api://…/access_as_user`) i wpis autoryzujący klienta z góry, żeby
  operator nie dostał ekranu zgody na własne API.
- **MSAL w terminalu** (`@azure/msal-browser`, przepływ przekierowaniem): logowanie kontem
  Microsoft, ciche odnawianie tokenu, jedno miejsce, z którego reszta kodu bierze token.
- **Każde żądanie HTTP do `market-data` niesie `Authorization: Bearer …`.** Nagłówek dokłada
  wspólny klient HTTP (`http.ts`), a nie każde wywołanie z osobna — dzięki temu obejmuje też trasy
  proxujące katalog instrumentów, które idą tym samym adresem.
- **`401` przestaje być błędem nie do naprawienia**: terminal próbuje odnowić token po cichu, a gdy
  to się nie uda, prowadzi operatora przez logowanie, zamiast pokazywać źródło jako nieosiągalne.
- **Praca lokalna bez zmian.** Bez skonfigurowanej rejestracji terminal nie dokłada żadnego tokenu
  i rozmawia z `market-data` na `localhost` tak jak dotąd. Logowanie jest tym, co dochodzi na
  wdrożeniu, a nie tym, co trzeba postawić, żeby uruchomić `vite dev`.

### `market-data` wydaje jednorazowe bilety na strumień

- **Nowa trasa wydająca bilet** — krótkożyjący, jednorazowy, losowy identyfikator wydawany
  konsumentowi, którego tożsamość Easy Auth już sprawdził. Token Entra MUST NOT trafiać do adresu
  połączenia, bo adresy lądują w logach serwera; bilet po jednym użyciu jest bezwartościowy.
- **BREAKING** — zestawienie `/ws/candles` wymaga ważnego biletu. Bez niego albo z biletem już
  zużytym, wygasłym lub nieznanym moduł odmawia **przed** handshake'iem i nie zapisuje konsumenta
  do rozgłaszania.
- **Ścieżka `/ws/candles` zostaje wyłączona z Easy Auth** (`excluded_paths`), bo Easy Auth broni jej
  ciasteczkiem, którego przeglądarka i tak nie przyśle. Obrona przenosi się o warstwę niżej, do
  modułu — i to jest jedyne miejsce w platformie, gdzie o dostępie decyduje nasz kod.
- **Moduł skonfigurowany jako stojący za Easy Auth odmawia wydania biletu, gdy tożsamości nie ma.**
  Bez tego wyłączenie Easy Auth jedną błędną linią w Terraformie zostawiłoby otwartą wytwórnię
  biletów, a więc otwarty strumień — i nie objawiłoby się niczym widocznym. Ta sama zasada, co
  w `capital-access-control`: konfiguracja jest warstwą drugą, nie pierwszą.
- **CORS**: `market-data` zaczyna uznawać adres terminala jako pochodzenie, z którego wolno wołać
  z przeglądarki. Bez tego nagłówek `Authorization` sam z siebie wywoła zapytanie wstępne
  (preflight), które przeglądarka odrzuci.

### Infrastruktura i wdrożenie

- `infra/entra.tf`: rejestracja SPA terminala, wystawiony zakres na rejestracji `market-data`,
  autoryzacja klienta z góry.
- `infra/app-service.tf`: `excluded_paths` dla ścieżki strumienia, ustawienia CORS, adres
  terminala i ustawienie wymagające tożsamości przy wydawaniu biletu.
- `.github/workflows/deploy-terminal.yml`: identyfikatory rejestracji i zakres przekazywane do
  builda jako zmienne `VITE_*`. Są to identyfikatory publiczne, nie sekrety — idą przez `vars`
  albo wprost, tak jak dotychczasowe adresy usług. **Nie przybywa żaden przechowywany sekret.**

## Capabilities

### New Capabilities

- `terminal-identity`: skąd terminal bierze tożsamość operatora, co dokłada do żądań i połączeń
  do `market-data`, jak reaguje na jej utratę i czego o niej nie zapisuje ani nie pokazuje.
- `market-data-browser-access`: na jakich warunkach moduł przyjmuje wywołanie z przeglądarki —
  tożsamość na trasach HTTP, bilet jednorazowy na strumieniu, uznane pochodzenie żądania.

### Modified Capabilities

- `terminal-market-data`: pętla ponawiania połączenia strumieniowego przestaje być czystym
  ponawianiem. Każda próba potrzebuje świeżego biletu, a utrata tożsamości jest trzecim rodzajem
  niepowodzenia obok zerwania i odmowy — takim, którego ponawianie nie naprawi, a którego dzisiejsza
  reguła („porażka rozstrzygnięcia znaczy: ponawiaj dalej") kazałaby ponawiać bez końca.

`market-data-api` zostaje bez zmian: świece, pokrycie, snapshot i zarządzanie zbieraniem znaczą
dokładnie to samo, co znaczyły. Zmienia się to, kto ma prawo o nie zapytać — a to jest osobna
warstwa i osobna zdolność, tak jak `capital-access-control` jest osobna od `capital-trading`.

## Impact

**terminal**: nowy moduł tożsamości (MSAL, pobranie tokenu, obsługa wygaśnięcia) i jego
konfiguracja w `config.ts`; `http.ts` dokłada nagłówek do każdego żądania; `archive.ts` pobiera
bilet przed każdym zestawieniem połączenia strumieniowego; `socketHub.ts` w części rozstrzygającej
powód niepowodzenia; powłoka pokazuje stan „niezalogowany" obok stanów źródeł. Nowa zależność
`@azure/msal-browser`, `.env.example`, `README.md`, testy.

**market-data**: trasa wydająca bilety, magazyn biletów z wygasaniem, sprawdzenie biletu przy
handshake'u `/ws/candles`, odczyt tożsamości wstrzykniętej przez Easy Auth, konfiguracja CORS,
`config.py`, `.env.example`, `README.md`, testy. Kontrakt OpenAPI rośnie o jedną trasę, więc
`pnpm contract:generate` w terminalu wymaga przebiegu.

**infra**: `entra.tf`, `app-service.tf`, `outputs.tf`. **capital-gateway nietknięty** — nie
rozmawia z przeglądarką i nic z tej zmiany go nie dotyczy.

**Repozytorium**: `docs/terminal-market-data-auth.html` — dziś nieśledzony — wchodzi do repozytorium
jako zapis decyzji; `.github/workflows/deploy-terminal.yml`; zadanie 11.4 w
`openspec/changes/provision-azure-platform/tasks.md` zamykane po weryfikacji end-to-end.

**Zależność operatorska, nie implementacyjna**: rejestracja SPA i wystawiony zakres powstają
Terraformem, ale pierwsze logowanie operatora wymaga, żeby jego konto miało dostęp do dzierżawy,
w której obie rejestracje żyją. Konto gościa B2B loguje się innym UPN-em niż własny — ta sama
pułapka, którą opisano przy DBeaverze w zadaniu 11.3 `provision-azure-platform`.

**Poza zakresem**: wielu operatorów i role (dostęp ma nadal jedno konto), wymiana Static Web Apps
na cokolwiek innego (opcje A i D z dokumentu — odrzucone i nie wracają w tej zmianie), oraz
uwierzytelnianie konsumentów innych niż przeglądarka. Ci ostatni są już obsłużeni: Easy Auth
przyjmuje token tożsamości zarządzanej w nagłówku bez żadnej zmiany po naszej stronie.
