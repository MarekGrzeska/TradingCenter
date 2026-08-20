## Context

`capital-gateway` broni się dziś dwiema warstwami: sprawdzeniem `X-Gateway-Key` w kodzie
(`RequireGatewayKey`, middleware, bo sonda zdrowia jest jedynym wyjątkiem) i regułami
adresowymi w `infra/app-service.tf` — `ip_restriction_default_action = "Deny"` plus adresy
wyjściowe market-daty i trading-mcp, czytane z ich zasobów. Terminal nie jest żadnym z tych
adresów i nie może nieść klucza: sekret w pobranym kodzie jest sekretem opublikowanym.
Katalog instrumentów dociera do terminala przez market-datę właśnie dlatego.

`market-data` rozwiązała ten sam problem rok temu w mniejszej skali: Easy Auth wpuszcza
aplikację, a `caller_access.py` decyduje, która tożsamość ma którą trasę — z komentarzem
mówiącym, dlaczego jedno nie zastępuje drugiego. To jest wzorzec, który tu powtarzamy.

Motywacja: proposal.md. Wymagania: `specs/capital-access-control` i `specs/terminal-accounts`
w tej zmianie.

## Goals / Non-Goals

**Goals:**

- Terminal osiąga rachunek bezpośrednio, bez pośrednika udającego, że rachunek jest jego.
- Otwarcie dotyczy rachunku i tylko rachunku — po tych samych drzwiach nie da się złożyć
  zlecenia.
- Klucz współdzielony zostaje tam, gdzie działa: między modułami.

**Non-Goals:**

- Zmiana drogi market-daty i trading-mcp do gatewaya. Wołają kluczem i tak zostaje.
- Handel z ekranu. Zlecenia składa agent albo platforma dostawcy; ten ekran pokazuje stan
  i przesuwa pieniądze demo.
- Pozycje wszystkich kont naraz. Powód w `specs/terminal-accounts`.
- Strumień stanu rachunku. Dostawca go nie ma; odświeżanie jest cykliczne.

## Decisions

### D1. Easy Auth przed gatewayem, ale bez wymuszania na każdym

`auth_settings_v2` z `unauthenticated_action = "AllowAnonymous"`: platforma **waliduje token,
jeżeli jest**, i nie odrzuca żądania, w którym go nie ma. Bez tego market-data i trading-mcp
— które wołają kluczem i żadnego tokenu nie mają — przestałyby działać w chwili apply,
a to jest zmiana, której ta zmiana nie chce robić.

Odrzucone: wymuszenie uwierzytelnienia na wszystkich i przerobienie obu modułów na tożsamość
zarządzaną. Kształt docelowo czystszy — jedna postać poświadczenia zamiast dwóch — ale
przerabia trzy moduły naraz po to, żeby dodać ekran, a droga kluczem jest tą, którą
`capital-access-control` opisuje i którą testy tych modułów sprawdzają.

### D2. Reguły adresowe przestają być drzwiami

Adres przeglądarki jest dowolny, więc `Deny` z listą dwóch aplikacji nie może zostać.
Zostaje zdjęty, a to jest **cena tej zmiany zapisana wprost**: gateway staje się osiągalny z
internetu, a jedyne, co go broni, to sprawdzenie poświadczenia w kodzie modułu — dotąd
druga warstwa, teraz jedyna.

Co to znaczy naprawdę: klucz, który wyciekł, był dotąd bezużyteczny spoza planu; po tej
zmianie wystarczy sam. Rotacja klucza przestaje być formalnością i staje się jedyną reakcją
na jego wyciek. Zostaje za to nietknięte to, co ogranicza szkodę: moduł odmawia startu z
hostem innym niż demo (`capital-session`), więc nie ma tu konta, na którym są prawdziwe
pieniądze.

Odrzucone: `ip_restriction` z zakresami Static Web Apps. Żądania idą z przeglądarki
operatora, nie z SWA — SWA serwuje pliki, nie proxuje tego wywołania.

### D3. Poświadczenie w dwóch postaciach, sprawdzane w module

`RequireGatewayKey` przestaje być „klucz albo 401" i staje się „klucz **albo** rozpoznana
aplikacja". Aplikacja czytana jest z oświadczenia `azp`/`appid` tokenu przekazanego przez
Easy Auth — nie z nagłówka `X-MS-CLIENT-PRINCIPAL-ID`, który dla tokenu delegowanego nazywa
osobę przy klawiaturze. To jest ten sam błąd, który `market-data` popełniła i zmierzyła na
produkcji 19 sierpnia 2026, wdrażając odwrotne założenie i wycofując je tego samego dnia.

Lista rozpoznawanych aplikacji jest ustawieniem (`BROWSER_CALLER_APPLICATION_IDS`), pustym
lokalnie. Pusta lista znaczy „nikt tą drogą", nie „każdy".

### D4. Rejestr tras, nie jedna brama

Wołający rozpoznany jako przeglądarka sięga wyłącznie po `/accounts`, `/accounts/active`,
`/accounts/top-up`, `/positions` i `/working-orders`. Wszystko inne — zlecenia, zamykanie,
stopy, strumień — jest dla niego odmową. Rejestr jest listą **dozwolonych**, więc trasa
dopisana za miesiąc jest domyślnie niedostępna, i to jest cała jego wartość
(`market_data/caller_access.py` mówi to samo o sobie).

Wołający z kluczem zachowuje pełny dostęp: to moduły, a nie przeglądarka.

### D5. Terminal w dev: proxy Vite, nie klucz w bundlu

Lokalnie gateway też żąda klucza, a przeglądarka nie może go dostać. Dev serwer Vite proxuje
`/gateway/*` na `127.0.0.1:8010` i dokłada nagłówek po swojej stronie — klucz zostaje w
procesie deweloperskim. Na produkcji tej ścieżki nie ma: tam jedzie token, a adres gatewaya
jest pełnym URL-em.

To jest ta sama asymetria, którą terminal ma już dla archiwum (`.env.example`: ścieżka
względna proxowana w dev albo pełny URL), więc nie wprowadza nowego pojęcia.

### D6. Odświeżanie: jedno odpytanie na wszystko, co pokazuje ekran

Konta i pozycje czytane są w jednym takcie, co kilka sekund, i tylko gdy zakładka jest na
wierzchu. Dostawca liczy 10 żądań na sekundę **na konto**, wspólnie dla wszystkiego, co ten
system robi — ekran, który odpytuje dwa razy na sekundę, zabiera przepustowość zbieraniu
świec i temu, czym handluje agent.

Ostatni udany odczyt jest pokazany, bo bez niego nieudany odczyt wygląda jak rachunek, który
się nie zmienia.

## Risks / Trade-offs

- **Gateway staje się osiągalny z internetu** → jedyna obrona to poświadczenie sprawdzane w
  kodzie (D2, D3). Ograniczenie szkody: wyłącznie środowisko demo, wymuszone przy starcie i
  niezmienne z konfiguracji.
- **Wyciek klucza waży więcej niż dotąd** → rotacja jest reakcją, a nie formalnością;
  `docs/rotacja-poswiadczen.html` opisuje jak. Warto rozważyć osobno przejście modułów na
  tożsamość zarządzaną (D1, odrzucone tutaj) — wtedy klucz znika zupełnie.
- **Ekran wdrożony przed apply nie działa** → i to jest stan wspierany, nie awaria: terminal
  mówi, że rachunek jest nieosiągalny, tak jak mówi o archiwum. Kolejność jest jednak
  ważna: apply przed obrazem, nie po.
- **Odpytywanie kosztuje budżet dostawcy** → jeden takt, tylko widoczna zakładka (D6).
- **Operator przełącza konto w środku zbierania świec** → ekran ostrzega przed wykonaniem
  (`specs/terminal-accounts`), a przerwa jest widoczna po stronie market-daty jako
  `reconnecting`.

## Migration Plan

1. Merge i deploy obrazu gatewaya z warstwą dostępu — działa bez zmian, bo lista aplikacji
   przeglądarki jest pusta i nikt nie przychodzi bez klucza.
2. `terraform apply` **lokalnie, przez operatora**: rejestracja Easy Auth (`azuread_*`, więc
   CI odmówi), wpuszczenie terminala, zdjęcie reguł adresowych, ustawienie
   `BROWSER_CALLER_APPLICATION_IDS`.
3. Deploy terminala z zakładką.

Wycofanie jest jednym ruchem w każdą stronę: pusta lista aplikacji przeglądarki zamyka tę
drogę, nie ruszając niczego innego; przywrócenie reguł adresowych zamyka ją na poziomie
platformy. Żaden z tych ruchów nie dotyka drogi market-daty ani trading-mcp.
