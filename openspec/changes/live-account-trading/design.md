## Context

Stan dziś (zob. proposal.md — Why): jedna `capital-gateway` przypięta do hosta demo walidatorem ustawień, jedno
`trading-mcp`, które przed otwarciem portu pyta bramę o środowisko, a za nim czterech wołających: rozmowa i zespoły z
workbencha (klucz, sieć wewnętrzna), Claude Code operatora i agent z Telegrama (`/trading/mcp`, token dla API bramy,
rola `admin`). Brama służy też archiwum świec (katalog, historia, strumień). Granice handlowe są dziś świadomie nieobecne
w `agent-trading` i opcjonalne w `teams-trading`, bo ochroną było demo.

Fakty od dostawcy (open-api.capital.com, odczyt 7.11.2026): host realny `https://api-capital.backend-capital.com`, demo
`https://demo-api-capital.backend-capital.com`, jeden udokumentowany adres strumienia; klucz API generowany w
ustawieniach konta po włączeniu 2FA, z własnym hasłem i domyślną ważnością roku, tylko z uprawnieniem do handlu (brak
kluczy tylko do odczytu); 10 żądań/s „per user”, 1 logowanie/s na klucz, otwarcie pozycji co najmniej 0,1 s; tryb
hedgingu i dźwignie są preferencjami konta (`/accounts/preferences`); korekta salda tylko na demo. Dokumentacja nie mówi,
czy jeden klucz działa na oba środowiska.

## Goals / Non-Goals

**Goals:**
- Instancje demo zostają bajt w bajt tym, czym są: ich strażnicy się nie zmieniają, zmienia się tylko to, że mają brata.
- Każde zlecenie na koncie realnym, od kogokolwiek, przechodzi przez jedno miejsce, które zna granice.
- Bez włączenia przez operatora serwer po wdrożeniu wygląda i działa jak przed nim.

**Non-Goals:**
- Dzienna granica straty, łączna ekspozycja i liczba pozycji, zatwierdzanie zleceń przez człowieka w terminalu albo
  Telegramie (wybór operatora 7.11.2026: granice w bramie, bez osobnego kroku zatwierdzania).
- Rynek z konta realnego: świece i strumień zostają z demo.
- Osobna rola Entra dla handlu realnego.

## Decisions

### D1. Drugie procesy z tych samych obrazów, a nie tryb w istniejących

Brama konta realnego i serwer narzędzi konta realnego to dwie nowe usługi z obrazów `capital-gateway` i `trading-mcp`,
uruchomione z innym ustawieniem środowiska. Odrzucone: (a) jedna brama obsługująca oba hosty — złamałoby „jeden proces na
granicę bezpieczeństwa”, bo zapis na koncie realnym ma regułę, której demo nie ma (granice, jedno konto), a awaria
ścieżki realnej zabrałaby archiwum strumień; (b) jedno `trading-mcp` z dwoma upstreamami i parametrem środowiska w
narzędziu — wtedy o pieniądzach decydowałby argument, który podaje model. Osobny proces daje też osobną listę
wołających, osobny klucz i osobny log.

### D2. Środowisko jest ustawieniem, host tylko je potwierdza

`CAPITAL_ENVIRONMENT=demo|live` (domyślnie `demo`). Walidator demo zostaje dokładnie taki, jak jest; dochodzi drugi: w
`live` adres bazowy musi być dokładnie hostem realnym, a proces musi być wdrożeniem serwerowym (`GATEWAY_ENV=production`
i `SERVER_MODE`). Odrzucone: wnioskowanie trybu z adresu — wtedy literówka w adresie byłaby decyzją o pieniądzach.
Konsekwencja: konta realnego nie da się uruchomić na komputerze operatora; pierwsza próba odbywa się na serwerze, z
najmniejszą granicą.

`trading-mcp` dostaje `EXPECTED_ENVIRONMENT=demo|live` (domyślnie `demo`) i porównuje je z odpowiedzią bramy w obie
strony. Ustawienie nie przenosi niczego samo: bez bramy związanej z hostem realnym instancja realna nie wstaje.

### D3. Granica to wielkość w jednostkach instrumentu, a lista instrumentów to klucze tej samej mapy

`LIVE_ORDER_LIMITS='{"US100": "0.5"}'` — jedno ustawienie niesie oba wybrane przez operatora ograniczenia: brak klucza to
instrument niedozwolony, wartość to największa wielkość jednego zlecenia. Odrzucone: wartość kontraktu albo depozyt w
walucie konta — wymagałyby w chwili decyzji ceny i kursu walut, czyli drugiego źródła prawdy, którego awaria albo
opóźnienie przepuszczałoby lub odrzucało zlecenia błędnie. Wielkość jest dokładna i sprawdzalna bez żadnego odczytu;
przeliczenie depozytu na wielkość robi już `size_for_margin`. Granica jest sprawdzana w bramie, nie w `trading-mcp`, bo
brama jest jedynymi drzwiami: terminal i każdy przyszły wołający przechodzą przez nią, a nie przez narzędzia.

### D4. Jedno konto przypięte w konfiguracji

`LIVE_ACCOUNT_ID` wymagane; sesja domyślna stoi na nim, `X-Capital-Account` z innym identyfikatorem jest odmową.
Odrzucone: dowolne subkonto realne wybierane przez wołającego — przełączanie konta realnego przez model albo zespół to
ryzyko bez korzyści, a drugie konto realne, gdy będzie potrzebne, to druga para procesów.

### D5. Sieci: workbench nie widzi bramy konta realnego

`trading-mcp` pokazuje bramie i żąda od wołających tego samego klucza, więc workbench, który woła serwer narzędzi konta
realnego, trzyma też klucz bramy konta realnego. To, że go nie użyje bezpośrednio, trzymają sieci Compose: `live-core`
(brama konta realnego, serwer narzędzi konta realnego, Caddy) i `live-tools` (serwer narzędzi konta realnego,
workbench). Odrzucone: osobny klucz na każdym odcinku — zmiana kontraktu `trading-mcp` z wołającymi dla obu instancji,
większa niż potrzeba, skoro sieć daje to samo.

### D6. Zespoły: środowisko w rewizji, te same nazwy narzędzi

`trading.environment` obok `trading.account_id`; zespół realny dostaje narzędzia rachunku z drugiego klienta MCP
(`TEAMS_LIVE_TRADING_MCP_URL`, `TEAMS_LIVE_TRADING_MCP_API_KEY`). Odrzucone: osobne nazwy (`place_order_live`) —
przeniesienie zespołu z demo na konto realne wymagałoby przepisania list narzędzi i promptów, a porównanie tego samego
zespołu na obu kontach przestałoby być porównaniem tego samego.

### D7. Rozmowa poza kontem realnym, trzymana przez pakiet, nie przez proces

Ustawienia serwera konta realnego czyta wyłącznie `teams/config.py`; test warstw dostaje regułę, że `agent` ich nie
czyta. To jest ustępstwo: rozmowa i zespoły dzielą proces, więc klucz jest w pamięci procesu, który obsługuje też
rozmowę. Przyjęte, bo tak samo dzielą dziś klucz demo, a rozdział pakietów trzymany testem jest w tym repozytorium
zasadą wewnątrz procesu. Wyjęcie zespołów z workbencha to zmiana wielokrotnie większa niż ta.

### D8. Krawędź i tożsamość bez zmian w Entra

`/trading-live/*` na hoście API prowadzi do serwera narzędzi konta realnego (lista wołających z zewnątrz: Claude Code i
agent), `/live/*` na hoście bramy — do bramy konta realnego (terminal: odczyt i zamknięcie wszystkiego). Ta sama
publiczność API bramy i rola `admin`. Odrzucone teraz: osobna rola „handel realny” — wymaga `terraform apply` przed
merge, a jedynym `admin` jest operator; to dobry następny krok, gdy pojawi się drugi człowiek.

### D9. Włącznik wdrożenia

Usługi realne w profilu Compose `live`, włączanym przez `LIVE_TRADING=on` w środowisku `vps`. Przy `on`
`assemble_env.py` wymaga kompletu sekretów konta realnego i odmawia, gdy klucz bramy realnej równa się kluczowi demo; przy
braku `on` nie wymaga niczego i nic nie startuje. `deploy.sh` czeka na zdrowie wszystkich uruchomionych kontenerów, więc
zepsuta konfiguracja realna cofa wdrożenie jak każda inna.

### D10. Osobny klucz API dostawcy dla konta realnego

Operator generuje dla bramy konta realnego własny klucz, nawet jeśli jeden klucz działa na oba środowiska: daje się go
wstrzymać w ustawieniach dostawcy bez ruszania demo, ma własny limit logowań i własną datę ważności.

## Risks / Trade-offs

- [Budżet 10 żądań/s „per user” może być wspólny dla demo i konta realnego, a archiwum zużywa demo przez cały dzień] →
  brama konta realnego robi niewiele żądań; zadanie pomiaru w próbie na serwerze, a 429 na zapisie jest odmową nazwaną,
  nigdy ponowieniem zlecenia.
- [Klucz demo może działać na koncie realnym] → strażnik hosta w procesie demo zostaje nienaruszony; sprawdzenie w
  próbie i zapis wyniku w README bramy.
- [Tryb hedgingu albo dźwignia konta realnego inne niż na demo — zlecenie przeciwne zamyka zamiast otwierać] → odczyt
  preferencji obu kont w próbie, przed pierwszym zleceniem; strategie i zespoły zakładają to, co pokaże odczyt.
- [Zespół na harmonogramie handluje realnymi pieniędzmi bez człowieka] → granice bramy obowiązują każdego; włączenie
  zespołu realnego to zapis rewizji, widoczny w terminalu; „zamknij wszystko” jest jednym kliknięciem.
- [Klucz serwera narzędzi konta realnego w procesie workbencha] → D5 i D7.
- [Wygaśnięcie klucza dostawcy po roku] → data ważności zapisana w README bramy; odmowa logowania na koncie realnym jest
  głośna (kontener niezdrowy przy starcie).

## Migration Plan

1. Merge z `LIVE_TRADING` nieustawionym: wdrożenie nie uruchamia nic nowego, instancje demo bez zmian.
2. Operator: klucz API na koncie realnym (2FA), identyfikator konta, `LIVE_ORDER_LIMITS` z najmniejszą sensowną
   wielkością, sekrety w `vps`, `LIVE_TRADING=on`, ponowne wdrożenie, `deploy-watch`.
3. Próba: terminal pokazuje konto realne; Claude Code czyta pozycje przez `/trading-live/mcp`; odczyt preferencji konta;
   jedno zlecenie o najmniejszej wielkości z Claude Code; zamknięcie z terminala przez „zamknij wszystko”; wiersze logu
   bramy przed i po.
4. Dopiero potem zespół realny i przełącznik agenta z Telegrama.

Wycofanie: `LIVE_TRADING` usunięte i ponowne wdrożenie zdejmuje obie usługi. Wyłącznik natychmiastowy, bez wdrożenia:
wstrzymanie klucza API konta realnego w ustawieniach dostawcy.
