# Review: the-gateway-door-authenticates

Wdrożone 20 sierpnia 2026, w czterech krokach i dwóch `apply`. Poniżej to, czego nie widać w
diffach: co zmierzono, co poszło inaczej niż w planie i co zostało do sprawdzenia operatorowi.

## Co potwierdziło, że drzwi działają

Najmocniejszy pojedynczy dowód nie jest ekranem, tylko `trading-mcp`. Ten moduł nie otwiera portu,
dopóki gateway nie potwierdzi mu, że rachunek jest demonstracyjny. Po przestawieniu drzwi
zrestartowaliśmy go celowo: `/health` odpowiadało `200` przez cały czas obserwacji (osiem pomiarów
przez ~3 minuty). To znaczy, że sprawdzenie środowiska przeszło **przez uwierzytelniającą się
bramę**, czyli token tożsamości zarządzanej został przyjęty.

Drugi dowód: `market-data` woła `/instruments/{symbol}/history` i `/instruments/search` z
odpowiedzią `200` już po przestawieniu.

Trzeci: żądanie z zewnątrz z `Authorization: Bearer notatoken` odbija się teraz od platformy
(`WWW-Authenticate`), a nie od modułu. Przed zmianą docierało do `RequireGatewayKey` i dostawało
`{"detail":"missing or invalid caller key"}` — to była cała diagnoza tej zmiany, w jednym curlu.

**Ustawienie propaguje się z opóźnieniem.** Pierwszy pomiar zaraz po `apply` pokazał, że nieważny
token nadal dociera do modułu, mimo że control plane raportował już `requireAuthentication: true`.
Minutę później było poprawnie. Tak samo zachował się CORS tego samego dnia. Sprawdzenie zaraz po
`apply` daje fałszywy negatyw i nie należy na jego podstawie niczego cofać.

## Trzy rzeczy, które poszły inaczej niż w planie

**1. Odmowa startu przy braku tokenu była złym pomysłem i została wycofana przed wdrożeniem.**
Plan mówił: nie ma tokenu → moduł nie wstaje. Przy pisaniu okazało się, że to zamienia nieszkodliwy
środek wdrożenia w awarię: między krokiem 2 a 4 token nie jest jeszcze nikomu potrzebny, więc
zająknięcie katalogu zatrzymałoby archiwum z powodu poświadczenia, o które nikt nie prosi. Teraz
brak tokenu jest logowany, żądanie idzie na kluczu, a o tym, czy to wystarcza, odpowiada gateway.
Delta `trading-mcp-upstream-access` i `design.md` niosą poprawioną decyzję.

**2. `terraform apply` w trakcie wdrożenia cofnął obrazy obu modułów.** Zrobiliśmy merge i od razu
`apply`, podczas gdy workflow deploy jeszcze pracował. Terraform ma `ignore_changes` na
`docker_image_name`, więc *nie planuje* zmiany obrazu — ale przy PUT konfiguracji strony wysyła
wartość ze swojego stanu, a ta była sprzed wdrożenia. Efekt: obie aplikacje wróciły na poprzedni
obraz, obie sondy zgłosiły „is not serving", oba wdrożenia na czerwono. Naprawa to ponowne
uruchomienie workflowów po zakończeniu `apply`.

> **Reguła:** `apply` i deploy tego samego modułu nie mogą biec równolegle. Najpierw jedno,
> potem drugie. `ignore_changes` chroni plan, nie chroni zapisu.

**3. `trading-mcp` wyszedł na produkcję i natychmiast padł — brakowało `aiohttp`.**
`azure.identity.aio` buduje pipeline przy **pierwszym** `get_token` i dopiero wtedy importuje
transport. Brak `aiohttp` to więc `ImportError` w czasie pracy i cisza przy instalacji. Ten moduł
pyta o token jako pierwszą rzecz po starcie (sprawdzenie demo przed otwarciem portu), więc
kontener kończył się kodem 1 po 5 sekundach.

`market-data` i `tc-runtime` mają tę zależność od dawna, a `market-data/pyproject.toml` tłumaczy ją
trzema linijkami komentarza. Skopiowaliśmy wzorzec bez linijki pod spodem.

> **Dlaczego testy tego nie złapały:** wszystkie podmieniają `DefaultAzureCredential` na dublera,
> więc żaden nigdy nie zbudował transportu. `test_the_async_transport_is_installed` używa prawdziwego
> poświadczenia i akceptuje dowolny `AzureError` — odmowa dowodzi, że pipeline powstał. Bez
> zależności ten test pada z `ImportError`.

## Czego nie dało się sprawdzić przed wdrożeniem, a wyszło dobrze

Czy Entra wyda tożsamości zarządzanej token dla audiencji gatewaya **bez przypisanej roli
aplikacji**. `design.md` założył, że tak, i kolejność kroków była ułożona tak, żeby pomyłka
kosztowała jedynie dopisanie roli. Produkcja odpowiedziała: `GET /msi/token` udane w telemetrii
`market-data`, zero ostrzeżeń `no token for …` w obu modułach.

## Strumień świec

Restart gatewaya przy `apply` zrywa wszystkie feedy — to znane i widoczne: 29 wyjątków
`ConnectionClosedError` w jednej minucie, `feed ended, retrying in 1s` dla każdej pary, potem cisza
i uzupełnianie luk przez REST („asked for 9 candles, wrote 9"). Cisza po retry jest tu dowodem:
nieudane ponowienia byłyby głośne. Przy okazji capital.com odpowiedziało
`error.too-many.requests` — wszystkie pary spadły na REST naraz i zjadły budżet 10/s. To też jest
znane i przechodzi samo.

## Czwarta rzecz, która poszła inaczej: audiencja

Po przestawieniu drzwi ekran Kont nadal odmawiał — ale inaczej, i to „inaczej" było całą
diagnozą. W telemetrii gatewaya **zniknęły żądania na `/accounts`**: przed przestawieniem każde
pojawiało się jako `401` aplikacji, po przestawieniu nie było żadnego. Żądanie, którego nie widać
w logach modułu, to żądanie odrzucone przez platformę.

Gateway miał w `allowed_audiences` trzy pozycje. Workbench — druga aplikacja, do której trafia
token terminala — nosi cztery, a czwartą jest **client id market-daty**. Potwierdzone u źródła, nie
przez porównanie: rejestracja market-daty ma `requestedAccessTokenVersion: 2`, a token v2 niesie
jako `aud` client id zasobu, nie jego `api://`. Token operatora niósł więc `3612647a…`, czyli
dokładnie tę pozycję, której brakowało.

Dlaczego nie wyszło to wcześniej: przy `require_authentication = false` audiencja nie była
sprawdzana w ogóle. Lista trzech wpisów wyglądała na poprawną tak długo, jak długo nikt do niej nie
zaglądał. To ten sam kształt co reszta tej zmiany — **sprawdzenie, które nie działa, nie może być
błędne, dopóki nie zacznie działać** — i drugi raz tego samego wieczoru.

Poprawka (`#197`) dokłada czwartą audiencję. `apply` poszedł przed pull requestem, bo produkcja
odmawiała operatorowi jego własnego ekranu; `terraform plan` z `main` po mergu wraca czysty.

## Ślad po odmowie

Trzy różne usterki dały w dwa dni identyczny, cichy `401`: niepasujący klucz, platforma nie
wstawiająca principala, i nieuwzględniona audiencja. Moduł nie zapisywał przy tym nic, więc jedynym
dowodem był **brak** wiersza w `AppRequests` — rzecz, którą da się zauważyć tylko, jeśli już się jej
podejrzewa. `RequireGatewayKey` loguje teraz, czym odmówił: ścieżka, obecność klucza, obecność
nagłówka principala i odczytana aplikacja. Bez sekretów — identyfikator aplikacji jest publiczny,
klucz i token nie trafiają do linii, i jest na to test.

## Co zostaje operatorowi

Trzy rzeczy wymagają sesji w przeglądarce i nikt inny ich nie sprawdzi:

1. zakładka Konta czyta konta i pozycje (`tasks.md` 6.2),
2. terminal nadal dostaje odmowę na trasie spoza rejestru `caller_access.py` (6.3),
3. wykres pokazuje świece na żywo, a nie tylko dociągnięte (6.4 — od strony logów wygląda dobrze).

Rollback, gdyby coś z tego nie działało, to jeden `apply` wstecz: `require_authentication = false`
i `AllowAnonymous`. Wraca stan sprzed zmiany, w którym moduły przechodzą kluczem, a ekran Kont nie
działa.
