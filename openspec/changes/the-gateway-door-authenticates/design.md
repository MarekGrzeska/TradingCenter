## Context

Powód jest w `proposal.md` — "Why". Tu tylko to, co kształtuje rozwiązanie, i co zmierzono
20 sierpnia 2026.

- Easy Auth przed gatewayem stoi z `require_authentication = false` i `AllowAnonymous`, bo
  `market-data` i `trading-mcp` wołają ten moduł kluczem i bez tokenu. Przy tym ustawieniu moduł
  uwierzytelniający **nie waliduje tokenu i nie wstawia nagłówka z oświadczeniami**. Sprawdzone
  z zewnątrz: `Authorization: Bearer notatoken` dotarł do middleware gatewaya i tam dostał
  `401 {"detail":"missing or invalid caller key"}`, a to samo żądanie do `market-data` odbiła
  platforma, `401` z `WWW-Authenticate` i pustym ciałem.
- Konfiguracja Entry po stronie gatewaya jest już poprawna i nic w niej nie brakuje:
  `allowedAudiences` zawiera `api://tradingcenter-market-data`, `allowedApplications` zawiera
  identyfikator terminala, a `BROWSER_CALLER_APPLICATION_IDS` w ustawieniach aplikacji to ta sama
  wartość. Nie działa jedno: nikt nie każe platformie sprawdzić tokenu.
- **Żadna aplikacja w grupie zasobów nie ma ograniczenia adresowego.** `ip_restriction` nie
  występuje w `infra/` ani razu. Klucz współdzielony jest całą obroną gatewaya, a nie drugą
  warstwą za listą adresów, jak opisywały to trzy pliki do 20 sierpnia.
- `/ws/stream` i `/` są wyłączone z Easy Auth i **muszą takie zostać**. Moduł uwierzytelniający
  przechwytuje upgrade WebSocketa i nigdy go nie kończy — zmierzone tego samego dnia, gdy feed
  świec padł na godzinę.
- Praca lokalna nie ma Entry. `dev.py` porównuje `GATEWAY_API_KEY` z `CAPITAL_GATEWAY_API_KEY` i
  odmawia startu przy rozjeździe; to zostaje.

## Goals / Non-Goals

**Goals:**

- Token wołającego jest sprawdzany przez kogoś, zanim gateway uwierzy jego oświadczeniom.
- Zakładka Konta w terminalu czyta rachunek na produkcji, bez zmiany w kodzie terminala.
- Poświadczenie modułu wołającego przestaje być sekretem, który dwie aplikacje trzymają w
  identycznym pliku.

**Non-Goals:**

- Otwarcie przeglądarce czegokolwiek poza rejestrem tras rachunku. `caller_access.py` zostaje
  dokładnie tym, czym jest.
- Zdjęcie klucza z pracy lokalnej. Lokalnie nie ma tożsamości do przedstawienia.
- Zdjęcie klucza ze strumienia. `/ws/stream` zostaje poza Easy Auth, więc sprawdzenie w uchwycie
  WebSocketa jest tam jedyne, jakie działa.
- Zwijanie `trading-mcp` do gatewaya. To osobna decyzja, zmierzona 20 sierpnia i stojąca na dwóch
  z trzech pierwotnych powodów (`docs/architecture.md`).

## Decisions

### Platforma uwierzytelnia, moduły przedstawiają token własnej tożsamości

Rozważono trzy drogi.

**(A) Wybrana.** `require_authentication = true` i `Return401` na gatewayu, wyliczona lista
aplikacji, a `market-data` i `trading-mcp` wołają go tokenem swojej tożsamości zarządzanej.
Uwierzytelnianie robi ta sama warstwa, która robi je dla `market-data`, workbencha i
`trading-mcp` — trzech aplikacji, w których to działa. Poświadczenie modułu przestaje być
wartością do skopiowania, a lista wołających staje się listą nazwanych aplikacji zamiast wiedzy o
jednym sekrecie.

**(B) Konta przez proxy `market-data`.** Katalog instrumentów już tak chodzi
(`routers/instruments.py`), więc trasy rachunku dopisałyby się tanio i ekran zadziałałby dziś.
Odrzucone: to obejście działającego mechanizmu przez moduł, który z rachunkiem nie ma nic
wspólnego. Archiwum świec stałoby się drogą, którą operator sięga po saldo, a każda kolejna trasa
gatewaya potrzebna przeglądarce byłaby kolejnym wpisem w cudzym module. Zostawia też przyczynę
nietkniętą: drzwi gatewaya dalej nie sprawdzałyby nikogo.

**(C) Gateway sam waliduje token** — JWKS Entry, podpis, wystawca, audiencja, wewnątrz aplikacji.
Odrzucone: to napisany ręcznie kod bezpieczeństwa, duplikat tego, co platforma robi obok, w
module, w którym błąd oznacza cudzy dostęp do składania zleceń. Wracamy do niego tylko, gdyby
platforma okazała się nie do nagięcia — nie okazała się.

Cena (A) jest w kolejności wdrożenia i jest opisana niżej. Jest to cena jednorazowa.

### Klucz zostaje w kodzie, przestaje być drogą wejścia na produkcji

Po przestawieniu platformy żądanie REST z samym kluczem i bez tokenu nie dojdzie do aplikacji —
odbije się o `Return401`. Klucz nie znika jednak z kodu ani z konfiguracji, i to jest decyzja, nie
zaniedbanie:

- `/ws/stream` jest poza Easy Auth, więc strumień `market-data` uwierzytelnia się **wyłącznie**
  kluczem sprawdzanym w uchwycie WebSocketa. Zdjęcie klucza zdjęłoby jedyną obronę tej trasy.
- Praca lokalna nie ma czym go zastąpić.

Skutek do zapamiętania: po tej zmianie klucz i token bronią różnych tras tej samej aplikacji.
`capital-access-control` mówi o tym jako o dwóch postaciach poświadczenia i to zostaje prawdą.

### Lista aplikacji zamiast ról aplikacji

Entra wystawi tożsamości zarządzanej token dla `api://tradingcenter-capital-gateway` bez
przypisanej roli aplikacji; `allowed_applications` w Easy Auth sprawdza `azp`/`appid`, więc rola
niczego by nie dodała poza czwartym obiektem `azuread_*` do utrzymania. Rola byłaby potrzebna
dopiero, gdyby gateway miał rozróżniać uprawnienia po niej zamiast po własnym rejestrze tras — a
rejestr jest tu celowo w module, nie w katalogu.

## Risks / Trade-offs

- **Przestawienie platformy przed wypuszczeniem modułów z tokenami odcina oba w chwili `apply`** →
  kolejność w "Migration Plan" jest odwrotna: najpierw moduły umieją oba, dopiero potem drzwi
  zaczynają wymagać. Między krokiem 2 a 4 system działa w obu konfiguracjach.
- **Zmiana dotyka `azuread_*`, więc `terraform-apply.yml` odmówi** → `apply` jest lokalny,
  operatora. To znany kształt i jest opisany w CLAUDE.md.
- **Token trzeba uzyskać, a to wywołanie sieciowe** → biblioteka tożsamości cachuje token do
  wygaśnięcia; koszt ponosi pierwsze żądanie po starcie. `trading-mcp` sprawdza demo przed
  otwarciem portu, więc jego start wydłuży się o to jedno wywołanie.
- **Nieudane uzyskanie tokenu wygląda jak awaria upstreamu** → `market-data` ma już wymaganie
  odróżniające odmowę dostępu od braku danych; `trading-mcp` odmawia startu, co delta rozszerza
  na brak tokenu.
- **`/ws/stream` zostaje poza uwierzytelnianiem platformy** → to nie jest regres, tylko stan
  dzisiejszy, ale po tej zmianie będzie jedyną taką trasą i warto, żeby było to widoczne w
  komentarzu przy `excluded_paths`.
- **Rollback jest jednym `apply`** → powrót do `AllowAnonymous` przywraca dzisiejszy stan, w
  którym moduły przechodzą kluczem, a ekran Konta znów nie działa.

## Migration Plan

1. **Terraform, `apply` operatora**: zakres gatewaya jako odbiorcy tokenów dla obu tożsamości
   zarządzanych; `allowed_applications` gatewaya rozszerzone o `market-data` i `trading-mcp`.
   Drzwi jeszcze nie wymagają — nic się nie psuje.
2. **Kod, dwa wdrożenia**: `market-data` i `trading-mcp` dołączają token do żądań REST, obok
   klucza. Oba działają zarówno przed, jak i po kroku 4.
3. **Sprawdzenie**: w logach gatewaya żądania z obu modułów niosą rozpoznaną aplikację.
4. **Terraform, `apply` operatora**: `require_authentication = true`, `Return401`,
   `excluded_paths` bez zmian.
5. **Sprawdzenie**: zakładka Konta czyta rachunek; strumień świec żyje; `trading-mcp` wstaje i
   jego sonda odpowiada `200`; żądanie z nieważnym tokenem odbija się od platformy z
   `WWW-Authenticate`, a nie od modułu.
6. **Rollback**: krok 4 wstecz, jednym `apply`.

## Open Questions

- Czy terminal ma z czasem prosić o token po imieniu gatewaya (`api://tradingcenter-capital-gateway`)
  zamiast używać tokenu wystawionego dla `market-data`. Zakres jest zarejestrowany i
  pre-autoryzowany, więc to zmiana jednego pliku w terminalu i nie zmienia niczego tutaj.
- Czy po kroku 5 warto przestać wysyłać klucz w żądaniach REST obu modułów. Nie zmienia to
  wymagań ani zadań; zmienia liczbę rzeczy, które mogą się rozjechać.
