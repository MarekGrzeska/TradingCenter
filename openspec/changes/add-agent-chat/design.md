## Context

Motywacja: `proposal.md`, sekcja Why. Wymagania: siedem plików w `specs/`.

Co zastane kształtuje ten projekt:

- Platforma Azure jest już postawiona i mieści się w darmowym grancie: jeden plan App
  Service **B1 z jednym workerem**, jeden serwer PostgreSQL **B1ms**, Static Web Apps na
  terminal, Key Vault, Application Insights. Agent jest pierwszą rzeczą, która wyjdzie
  poza ten grant — model płaci się za token, i to poza fakturą Azure.
- Terminal stoi pod innym adresem niż moduły i woła je międzydomenowo z tokenem Entra.
  CORS odpowiada **App Service, nie aplikacja** (`infra/app-service.tf`: dwie warstwy
  dokładające `Access-Control-Allow-Origin` dają nagłówek podwójny, a preflight bez
  poświadczenia i tak zderzyłby się z Easy Auth przed kontenerem).
- Static Web Apps **nie przeprowadzi strumienia** — dlatego terminal ma osobny adres
  HTTP i osobny WS dla archiwum, i dlatego agent dostanie własny adres, a nie ścieżkę pod
  adresem terminala.
- Wzorzec „`DATABASE_USER` ustawiony = tożsamość, nieustawiony = wyłącznie pętla zwrotna"
  jest w `market-data/config.py` i uratował już produkcję przed lokalnym `.env`.
  Powielamy go, nie współdzielimy.
- `capital-gateway` i `market-data` nie są w tej zmianie dotykane ani razu.

Ceny modeli, sprawdzone 11 sierpnia 2026 i **rozjechane między źródłami**: cennik OpenAI
(Sol 5/30, Terra 2/12, Luna 0,20/1,20 USD za 1M tokenów) różni się od stawek, które
użytkownicy widzą na fakturach Azure (Luna 1,10/6,60), Microsoft ogłosił parytet od
1 sierpnia 2026, a osobne stawki obowiązują dla kontekstu powyżej 272K tokenów. To nie
jest szczegół do doprecyzowania — to fakt, wokół którego projektuje się pomiar kosztu.

## Goals / Non-Goals

**Goals:**

- Moduł, który da się uruchomić, przetestować i usunąć samodzielnie, jak każdy inny tutaj.
- Transkrypt czytelny zwykłym SQL-em — lista rozmów i zakładka kosztów to zapytania, nie
  odtwarzanie stanu biblioteki.
- Koszt zgadzający się z fakturą po miesiącach i po zmianach cennika.
- Graf, do którego dołożenie narzędzia jest dołożeniem węzła, a nie przepisaniem modułu.

**Non-Goals:**

- Narzędzia agenta: świece, wskaźniki, pozycje, wyszukiwanie w sieci. Żadnego.
- Limity i budżety — zakładka kosztów pokazuje, nie hamuje. Zatrzymanie wydatku to osobna
  decyzja i osobna zmiana.
- Wielu operatorów. Tożsamość przy sesji jest po to, żeby model danych nie wymagał
  migracji, gdy drugi się pojawi — nie po to, żeby go dziś obsłużyć.
- Edycja i regeneracja wypowiedzi, załączniki, eksport transkryptu.
- Generowanie typów terminala z OpenAPI agenta — patrz decyzja o kontrakcie.

## Decisions

### Osobny moduł `modules/agent`, port 8030

Rozmowa z modelem to inna domena niż archiwum świec, z innym cyklem wdrożenia i innym
profilem awarii: model, który przestał odpowiadać, nie ma prawa zatrzymać zbierania świec.
Odrzucone: dołożenie tras do `market-data` — szybsze o cały dzień pracy (baza, migracje,
auth, deploy już są), ale odbiera modułowi prawo do samodzielnego usunięcia, a to jest cała
treść architektury tego repozytorium.

Cena decyzji jest realna i płacimy ją świadomie: czwarty job w CI, czwarty workflow
wdrożenia, czwarta aplikacja na planie z jednym workerem, powielone DTO.

### Własne tabele są prawdą, LangGraph nie trzyma transkryptu

Transkrypt, sesje i zużycie mieszkają w tabelach tego modułu. Graf dostaje historię
rozmowy zbudowaną z nich przy każdej turze i nie ma własnego magazynu.

Odrzucone: `AsyncPostgresSaver` jako źródło prawdy. Trzy powody, w kolejności wagi:

1. Zakładka kosztów i lista rozmów to zapytania SQL po kolumnach, które sami wybraliśmy.
   Nad schematem checkpointera LangGraph — prywatnym, wersjonowanym przez bibliotekę i
   trzymającym stan jako blob — takich zapytań się nie pisze.
2. Aktualizacja biblioteki migrowałaby wtedy nasze archiwum rozmów. To jest dokładnie ta
   zależność, którą reszta repozytorium nazywa sprzęgnięciem bez kontraktu.
3. Transkrypt w dwóch miejscach rozjeżdża się w tym jednym przypadku, którego nikt nie
   testuje — przerwaniu w połowie.

Tracimy: darmowe „time travel", wznowienie grafu w środku i trwałe `interrupt`. Dziś graf
ma jeden węzeł, więc nie ma czego wznawiać. Gdy dojdą narzędzia i tura zacznie się składać
z kilku kroków, checkpointer MAY zostać dołożony **obok** — do stanu wykonania, nie do
transkryptu, który zostaje nasz.

### Odpowiedź strumieniem: `fetch` + `ReadableStream`, nie `EventSource`

Trasa odpowiada `text/event-stream` na `POST`. Terminal czyta ciało odpowiedzi przez
`fetch` i parsuje ramki SSE sam (kilkadziesiąt linii: bufor, podział po `\n\n`, pola
`event:`/`data:`).

`EventSource` odpada dwukrotnie: nie umie `POST`, a przede wszystkim nie umie nagłówka
`Authorization`. Odrzucone: bilet jednorazowy jak w `market-data` (`tickets.py`). Bilety
istnieją tam dlatego, że **uchwyt WebSocketu naprawdę nie może nieść nagłówka** — `fetch`
może, więc kopiowanie tamtej maszynerii byłoby tabelą, trasą i czasem ważności kupionymi
za nic.

Konsekwencja dla App Service: strumień MUST nieść komentarz utrzymujący (`: ping`) co
kilkanaście sekund. Bezczynne połączenie jest tam zrywane po 230 sekundach, a odpowiedź
modelu rozumującego potrafi zacząć się później niż po pierwszym tokenie.

### Tura modelu przeżywa rozłączenie wołającego

`agent-chat` wymaga, żeby odpowiedź zapisała się w całości także wtedy, gdy operator
zamknie panel w jej połowie. Wykonanie tury dzieje się więc w zadaniu niezwiązanym z cyklem
życia żądania; odpowiedź SSE tylko opróżnia kolejkę, którą to zadanie karmi. Rozłączenie
zamyka kolejkę, nie turę.

Odrzucone: przerywanie tury przy rozłączeniu (`request.is_disconnected`). Prostsze o jedną
warstwę, ale dostawca policzy tokeny, których nikt nie zobaczył, a operator wróci do
rozmowy uciętej w pół zdania.

### Cennik jest konfiguracją, stawka jest przepisywana na wiersz

Wiersz zużycia niesie tokeny **i** stawki, którymi policzono jego koszt, **i** policzony
koszt. Odczyt sumuje kolumnę kosztu i nigdy nie zagląda do bieżącego cennika.

Odrzucone: przeliczanie przy odczycie z tabeli stawek. Krótsze o kolumny i zawsze „spójne"
— dopóki cennik się nie zmieni, a wtedy koszt rozmowy sprzed miesiąca cicho się przesuwa i
przestaje zgadzać się z fakturą, po której ten pomiar w ogóle istnieje. Luna staniała o 80%
dwanaście dni przed tym zapisem; to nie jest ryzyko teoretyczne.

Koszt jest `NUMERIC`, nie `float`: pojedyncze wywołanie kosztuje ułamek centa i sumowanie
tysięcy takich we `float` gubi grosze dokładnie tam, gdzie ma się zgadzać.

Stawka za długi kontekst (powyżej 272K tokenów) **nie jest modelowana** — jedna stawka na
model, wejście i wyjście. Wiersz niesie użyte stawki, więc gdy okaże się, że trzeba je
rozbić, dawne wiersze zostają czytelne i poprawne bez migracji danych.

### Katalog modeli jest konfiguracją, nie kodem

Trzy modele — `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol` — wchodzą jako konfiguracja:
nazwa u dostawcy, nazwa do pokazania, porządek kosztu, stawki. Moduł publikuje z tego
katalog, a terminal buduje z katalogu wybierak i nie zna żadnej z tych nazw.

To ten sam chwyt, co `market-data-indicators` („Katalog wystarcza do zbudowania
wybieraka"), i z tego samego powodu: czwarty model ma być wpisem, nie zmianą w dwóch
modułach i regeneracją kontraktu.

Model bez stawki zatrzymuje start modułu. Alternatywa — koszt zerowy albo pominięty wiersz
— daje zakładkę kosztów, która kłamie, i nikt się o tym nie dowie.

### Wobec OpenAI: klucz, i tylko klucz

Modele bierze się wprost z OpenAI, nie przez Azure OpenAI. Powód jest zmierzony, nie
preferencyjny: 12 sierpnia 2026 `gpt-5.6-luna/terra/sol` miały quotę **0 we wszystkich 28
regionach**, które ta subskrypcja widzi — Poland Central i Sweden Central tak samo — a
`az cognitiveservices usage list` pokazuje niezerowy przydział tylko na warianty „mini".
Azure nie odmawia tych modeli, po prostu ich jeszcze nie przydziela; odblokowuje je wniosek
o quotę i cudzy kalendarz. Konto OpenAI daje je od ręki, a moduł nie ma powodu wiedzieć,
przez którą bramę mówi.

Ceną jest jedyne poświadczenie na tej platformie, którego nie da się zastąpić tożsamością:
**OpenAI nie ma odpowiednika w Entra**, więc nie ma komu przedstawić tokenu tożsamości
zarządzanej. Zostaje klucz. Lokalnie niesie go `.env`, na produkcji ten sam klucz siedzi w
Key Vault (`openai-api-key`) i aplikacja czyta go referencją `@Microsoft.KeyVault(...)` —
wartość nie przechodzi przez stan Terraforma ani przez log wdrożenia, tak samo jak
poświadczenia capital.com.

Nie ma więc wyboru trybu, jaki jest przy bazie: klucz MUST być ustawiony, bo nie ma czego
użyć zamiast niego. Moduł bez niego nie wstaje — inaczej przyjąłby turę i przewrócił się
na wywołaniu, już po zapisaniu wypowiedzi operatora.

Co to kosztuje w stosunku do poprzedniego wariantu, zapisane wprost: klucz do rotacji i
do wycieku, rachunek poza fakturą Azure, i ruch wychodzący poza subskrypcję. Wraca to
w chwili, w której quota na te modele w Azure przestanie być zerowa — wtedy zmiana dotyczy
`provider.py` i `infra/`, a nie kontraktu ani terminala.

Testy nie dotykają klucza: podstawiają fałszywy model. Sprawdzian z prawdziwym modelem stoi
za markerem `live`, jak w pozostałych modułach, i nie chodzi w CI.

### Baza: druga baza logiczna, jeden serwer

Produkcja: baza `agent` obok `market_data` na `psql-tradingcenter`, osobna rola Entra dla
tożsamości aplikacji agenta, bez dostępu do bazy archiwum. Darmowy grant to 750 godzin
**jednego** B1ms i to jest cały powód, dla którego serwer jest jeden — decyzja z
`provision-azure-platform`, nie nowa.

Lokalnie: ta sama baza w kontenerze `tradingcenter-db`. **Nie** przez skrypt w
`docker-entrypoint-initdb.d` — ten wykonuje się tylko przy pierwszym starcie pustego
wolumenu, więc u każdego, kto ma już `tradingcenter-db-data`, nie wykonałby się nigdy, a
„naprawą" byłoby `down -v`. Zamiast tego bazę zakładają skrypty `dev.sh`/`dev.ps1`, jeśli
jej nie ma. Jedno miejsce, działa na wolumenie zastanym i na świeżym.

`healthcheck` w `compose.yaml` zostaje przy `market_data`: sprawdza, czy serwer wstał, a
nie czy jest w nim komplet baz.

### Kontrakt terminala pisany ręcznie, bez generatora

`pnpm contract:generate` jest wpięty w schemat `market-data` i jego jeden kontrakt.
Podpięcie drugiego źródła to zmiana w generatorze, w `contract:check` i w regule CI, która
uruchamia job terminala przy dotknięciu `contract.py` — czyli osobna zmiana o własnej
wadze. Tutaj DTO agenta są w terminalu napisane ręcznie, tak jak repozytorium i tak
przewiduje powielanie kształtów między modułami.

### Ta zmiana zostaje jedna, etapy są w `tasks.md`

Rozbicie na „moduł i czat", potem „koszty" wygląda kusząco, ale pomiar zużycia dołożony po
fakcie to migracja danych i drugie przejście przez ten sam kod — a rozmowy prowadzone w
międzyczasie nie mają skąd odzyskać swoich tokenów. Etapy są w `tasks.md` i każdy kończy
się czymś, co da się uruchomić.

## Risks / Trade-offs

**Rachunek rośnie bez hamulca** → Zakładka kosztów jest widocznością, nie limitem. Domyślny
model to najtańszy (Luna); najdroższy wybiera się świadomie, z widoczną różnicą stawki.
Twardy limit — dzienny albo miesięczny — jest odłożony do osobnej zmiany i zapisany tutaj
jako świadomy dług, nie przeoczenie.

**Rachunek za model jest poza fakturą Azure** → Kredyt Azure i konto OpenAI to dwa
oddzielne rachunki, więc startowe 200 USD nie płaci ani jednej tury. Zakładka kosztów
liczy z własnych stawek w konfiguracji, a nie z niczyjej faktury — przy turze rzędu
3 tys. tokenów wejścia i 700 wyjścia stawki z sierpnia dają około 25 tys. tur na Lunie i
5 tys. na Solu za 100 USD. Trzeba pilnować dwóch miejsc zamiast jednego; alert kosztowy po
stronie OpenAI należy do operatora i nie da się go postawić Terraformem z tego roota.

*(Poprzednie brzmienie tego ryzyka — „Subskrypcja Free Trial ma zerową quotę" — okazało
się trafne co do skutku i chybione co do przyczyny. Subskrypcja jest Pay-As-You-Go, a
quota i tak wynosiła 0: nie z powodu rodzaju subskrypcji, tylko dlatego, że te modele
dopiero wchodzą. Zmierzone, zapisane wyżej.)*

**Klucz OpenAI to poświadczenie bez tożsamości za plecami** → Jedyne miejsce na tej
platformie, gdzie nie da się użyć tożsamości zarządzanej, więc jedyne, które trzeba
rotować ręcznie i które może wyciec. Mitygacja jest ta sama, co przy capital.com: wartość
tylko w Key Vault, w ustawieniu aplikacji sama referencja, nigdy w stanie Terraforma ani w
logu wdrożenia. Rotacja dopisuje się do `docs/rotacja-poswiadczen.html` obok tokenu GHCR —
drugi wpis w tej samej tabeli, nie nowy mechanizm.

**Nazwa modelu nie jest przez nic sprawdzana** → Katalog to konfiguracja, a `model` jest w
niej zwykłym napisem: ani Terraform, ani moduł nie potwierdzą, że OpenAI taki model
serwuje. Objawia się dopiero na pierwszej turze, nie przy starcie — bo katalogu nie da się
zweryfikować bez wywołania, które kosztuje. Operator sprawdza `GET /v1/models` przed
wdrożeniem; to samo, co poprzednio robił `az cognitiveservices account list-models`.

**Czwarta aplikacja na B1 z jednym workerem** → 1 rdzeń i 1,75 GB dzielone teraz przez
cztery kontenery. Moduł agenta jest w większości czekaniem na sieć, więc rdzeń boli mniej
niż pamięć. Alert pamięciowy już istnieje (`alert-on-dead-backend`); jeśli zacznie krzyczeć,
odpowiedzią jest większy plan, nie drugi worker — komentarz przy `worker_count = 1`
tłumaczy, dlaczego ta liczba nie jest pokrętłem.

**SSE przez App Service** → Ryzyko buforowania i zerwania po 230 sekundach bezczynności.
Mitygacja: komentarze utrzymujące w strumieniu i sprawdzenie na wdrożonej aplikacji, nie
tylko lokalnie. Terminal woła agenta pod jego własnym adresem, nie przez Static Web Apps —
SWA nie przeprowadza strumienia i nie ma powodu sprawdzać, czy tym razem przeprowadzi.

**Zużycie przy strumieniowaniu bywa niepodane** → Przy odpowiedzi strumieniowanej dostawca
podaje zużycie tylko wtedy, gdy się o nie poprosi, i nie w każdej sytuacji błędu.
`agent-usage` wymaga oznaczenia „nieznane" odróżnialnego od zera właśnie dlatego; brakujące
zużycie MUST być widoczne w zakładce, bo inaczej różnica między pomiarem a fakturą nie ma
gdzie się pokazać.

**Prompt systemowy jako jedyna bariera** → Agent nie ma narzędzi, więc nie może nic zrobić
poza mówieniem — ale mówić o rynku będzie. Prompt nazywa granice; to nie jest zabezpieczenie
techniczne i nie udaje nim być. Dopóki agent nie handluje, koszt pomyłki to zła rada, którą
operator czyta jako radę modelu, a nie jako sygnał z terminala.

**Baza `agent` w produkcji zakładana ręcznie** → Terraform tworzy bazę, ale rola Entra i jej
uprawnienia powstają w sesji `psql` operatora, jak przy `market-data`. Krok pominięty daje
aplikację, która startuje i odmawia na pierwszym połączeniu. Należy do listy w
`tasks.md`, nie do pamięci.

## Migration Plan

Nic nie migruje — nie ma czego. Makieta w terminalu trzymała transkrypt w pamięci karty i
nie ma stanu do przeniesienia; `STORAGE_KEY` (`terminal.agentChat.v1`) zostaje przy stanie
zwinięcia panelu.

Kolejność wdrożenia, wymuszona zależnościami:

0. Konto OpenAI i klucz — sprawdzenie, że katalog naprawdę serwuje trzy modele z
   `var.agent_models` (`GET /v1/models`). Napis, którego nie ma po tamtej stronie,
   przechodzi przez `apply` bez słowa i przewraca się na pierwszej turze.
1. `terraform apply -target=azurerm_linux_web_app.agent`, potem apply bez `-target` —
   ta sama dwufazowość co przy `market-data`: adresy wychodzące aplikacji nie są znane
   przed jej powstaniem, a reguła firewalla bazy ich potrzebuje.
2. `az keyvault secret set --name openai-api-key` — przed pierwszym startem kontenera.
   Aplikacja czyta go referencją i bez wartości nie wstaje.
3. Operator zakłada rolę Entra w bazie `agent` i nadaje jej uprawnienia (sesja `psql`).
4. Wdrożenie obrazu (`deploy-agent.yml`), migracje, sprawdzenie zdrowia.
5. Terminal z ustawionym `VITE_AGENT_HTTP`.

Wycofanie: usunięcie zakładki i panelu z terminala jest zmianą w terminalu i nic poza nim
nie psuje. Moduł zatrzymuje się bez skutków dla `market-data` i `capital-gateway` — nic go
nie woła. Po stronie modelu nie ma nic do rozbierania: klucz się kasuje, a nieużywany nie
kosztuje.

## Open Questions

- Czy tytuł sesji nadaje model (jedno tanie wywołanie po pierwszej wymianie), czy pierwsze
  słowa wypowiedzi operatora? Spec wymaga tylko, żeby tytuł powstał z pierwszej wiadomości
  i był stabilny. Wersja ze skróconą wypowiedzią jest darmowa i wchodzi pierwsza; model
  MAY ją zastąpić później, bez zmiany wymagania.
- Ile tur historii wchodzi do promptu, zanim rozmowa zacznie być podsumowywana. Do
  zmierzenia na prawdziwych rozmowach; do tego czasu wchodzi cała, a koszt tego widać w
  zakładce, która właśnie po to powstaje.
