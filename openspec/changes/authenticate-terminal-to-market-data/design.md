## Context

Stan wyjściowy, uzasadnienie wyboru i odrzucone drogi: `proposal.md` oraz
`docs/terminal-market-data-auth.html`. Tu tylko to, co kształtuje rozwiązanie.

Cztery ograniczenia, z których wszystko dalej wynika:

1. **Terminal i archiwum stoją pod różnymi adresami.** `swa-tradingcenter-terminal` na
   `*.azurestaticapps.net`, `app-tradingcenter-market-data` na `*.azurewebsites.net`. Ciasteczko
   Easy Auth jest wystawione dla tego drugiego i przeglądarka nie dołoży go do żądania z pierwszego.
2. **Przeglądarkowe `WebSocket` nie przyjmuje nagłówków.** Nie ma tam gdzie włożyć tokenu — ani
   `Authorization`, ani żadnego innego.
3. **Easy Auth stoi przed całą aplikacją z `unauthenticated_action = "Return401"`** i wyłącza się
   ze ścieżek wyłącznie po ścieżce (`excluded_paths`), nie po metodzie. Wersja providera w `infra/`
   `excluded_paths` obsługuje — sprawdzone przy pisaniu dokumentu decyzyjnego.
4. **Plan `B1`, `worker_count = 1`, ~80% pamięci zajęte.** Jedna instancja `market-data`, bez
   autoskalowania. To, co przybywa po stronie serwera, musi być małe.

Do tego stan, którego się nie zmienia: `capital-gateway` jest niepubliczny i nie rozmawia
z przeglądarką; katalog instrumentów terminal czyta przez archiwum, tym samym adresem co świece
(`marketData.ts`), więc jedno miejsce wpięcia poświadczenia wystarcza na obie rzeczy. Terminal jest
dziś serwowany bez żadnego logowania — nie ma `staticwebapp.config.json`, więc wbudowane logowanie
Static Web Apps jest dostępne, ale nieegzekwowane.

## Goals / Non-Goals

**Goals:**

- Wykres pokazuje świece z wdrożonego archiwum, a operator dostaje się do niego kontem organizacji.
- `market-data` zostaje czystym API chronionym tokenem — konsument niebędący przeglądarką podłącza
  się do niego bez żadnej zmiany po naszej stronie.
- Kod decydujący o dostępie powstaje w dokładnie jednym miejscu i jest tam mały: wydanie
  poświadczenia jednorazowego i sprawdzenie go przy handshake'u.
- Nie przybywa żaden przechowywany sekret ani żadna wartość do rotacji.

**Non-Goals:**

- Autoryzacja: kto może co. Konto jest jedno i wszystko mu wolno; ta zmiana rozstrzyga wyłącznie
  „czy to ty", nie „czy wolno ci to".
- Ochrona samych plików terminala. Nie niosą danych, a druga bramka oznaczałaby drugie logowanie
  dla jednego operatora — patrz decyzja niżej.
- Zmiana topologii wdrożenia. Static Web Apps zostaje, `capital-gateway` zostaje niepubliczny,
  opcje A i D z dokumentu decyzyjnego nie wracają.

## Decisions

### Bilet jednorazowy zamiast tokenu w adresie

Token Entra w query stringu połączenia byłby najkrótszą drogą, ale adresy trafiają do logów App
Service i Application Insights, a token jest ważny kilkadziesiąt minut i otwiera całe API. Zamiast
niego archiwum wydaje **bilet**: losową wartość ważną kilkadziesiąt sekund i unieważnianą w chwili
pierwszego użycia. Bilet, który wyciekł z logu, jest już zużyty; bilet, który nie zdążył zostać
użyty, przeterminowuje się szybciej, niż ktokolwiek zdąży log przeczytać.

Wydanie biletu jest zwykłym żądaniem HTTP, więc niesie `Authorization` i przechodzi przez Easy
Auth. To jest cała sztuczka: **tożsamość sprawdza się tam, gdzie nagłówki działają, a do miejsca,
gdzie nie działają, przenosi się jej jednorazowy ślad.**

*Alternatywa odrzucona: token w podprotokole* (`new WebSocket(url, [token])` ląduje
w `Sec-WebSocket-Protocol`, czyli w nagłówku, nie w adresie). Działa i omija logi, ale nadużywa
pola przeznaczonego do negocjacji protokołu, wymaga od serwera odesłania wybranego podprotokołu,
bo inaczej przeglądarka zamyka połączenie, i psuje się o każdy pośrednik filtrujący nieznane
podprotokoły. Przy bilecie jednorazowym argument o logach znika, a query string jest zwyczajny.

*Alternatywa odrzucona: bilet podpisany, bez stanu* (HMAC z czasem wygaśnięcia). Znosi magazyn, ale
nie da się unieważnić po jednym użyciu bez zapamiętania, że został użyty — a jednorazowość jest tu
głównym zabezpieczeniem, nie dodatkiem.

### Bilety żyją w pamięci procesu

Słownik `bilet → (tożsamość, moment wygaśnięcia)`, zdejmowany przy użyciu, przeglądany przy okazji.
Jedna instancja, `always_on`, `worker_count = 1` — bilet wydany przez ten proces jest przez ten sam
proces sprawdzany.

Restart archiwum unieważnia bilety w locie. Kosztuje to najwyżej jeden nieudany handshake, po
którym terminal pobiera nowy bilet i ponawia — czyli dokładnie to, co robi po każdym zerwaniu.

Ograniczenie jest realne i trzeba je nieść dalej: **`worker_count > 1` albo druga instancja psuje
bilety w sposób wyglądający jak losowe odmowy strumienia.** Wpięcie tego w magazyn dzielony
(Postgres, tabela z TTL) jest wtedy zmianą jednego modułu, ale musi być świadome. Komentarz w kodzie
mówi o tym wprost.

*Alternatywa odrzucona: od razu tabela w bazie.* Zapis i usunięcie na każdy socket, dla wartości
żyjącej trzydzieści sekund, przy jednej instancji, która i tak nie może się rozmnożyć.

### Bilet ważny 30 sekund

Tyle, żeby powolna sieć zdążyła zestawić połączenie zaraz po jego otrzymaniu, i nie więcej.
Jednorazowość i tak jest mocniejszym ograniczeniem niż czas — czas jest tu na wypadek biletu, który
nigdy nie został użyty.

### Bilet zapamiętuje, komu został wydany

Nie jest to dziś potrzebne — konto jest jedno — ale czyni z biletu poświadczenie **czyjeś**, a nie
anonimową wartość na okaziciela, i pozwala zalogować odmowę sensownie. Kosztuje jedno pole.

### Ścieżka strumienia wychodzi spod Easy Auth, a nie spod ochrony

`excluded_paths` obejmuje dokładnie jedną ścieżkę — tę, na której stoi strumień. Wszystko inne
zostaje za Easy Auth bez zmian. Ścieżka zwolniona z Easy Auth **nie jest** ścieżką bez ochrony:
przejmuje ją sprawdzenie biletu w module. To jedyne miejsce w platformie, gdzie o dostępie decyduje
nasz kod, i dlatego jest małe oraz pokryte testami.

Kolejność wdrożenia wynika z tego wprost i jest nieprzestawialna — patrz Migration Plan.

### CORS konfigurowany na App Service, nie w aplikacji

Nagłówek `Authorization` w wywołaniu międzydomenowym wymusza zapytanie wstępne (`OPTIONS`), które
**z definicji nie niesie żadnego poświadczenia**. Easy Auth z `Return401` odpowiedziałby na nie
`401`, zanim aplikacja je zobaczy — i żadne wywołanie z przeglądarki nie doszłoby do skutku,
niezależnie od poprawności tokenu. Wbudowany CORS App Service obsługuje zapytanie wstępne przed
Easy Auth i po to tu jest.

Wynika z tego zakaz, który łatwo złamać przez nieuwagę: **`CORSMiddleware` w aplikacji MUST NOT
dojść**, dopóki CORS stoi na App Service. Dwie warstwy dokładające `Access-Control-Allow-Origin`
dają nagłówek podwójny, a przeglądarka odrzuca odpowiedź z dwoma. Lokalnie problem nie istnieje —
Vite proxuje archiwum pod adresem strony, więc wywołanie jest tej samej domeny.

*Ryzyko z tym związane i jego odwrót: patrz Risks.*

### Dwie rejestracje Entra: klient i API

Terminal dostaje własną rejestrację typu SPA, rejestracja `market-data` zyskuje wystawiony zakres
(`api://…/access_as_user`) i wpis autoryzujący klienta z góry. Terminal prosi o token **dla
archiwum**, nie dla siebie, a Easy Auth uznaje go, bo audytorium się zgadza.

Wpis autoryzujący klienta z góry (`known_clients` / pre-authorized application) usuwa ekran zgody:
bez niego operator dostaje pytanie, czy zgadza się dać dostęp do własnego API, przy pierwszym
wejściu i po każdej zmianie zakresu.

*Alternatywa odrzucona: jedna rejestracja pełniąca obie role.* Da się — SPA prosi o zakres
wystawiony przez samą siebie — i oszczędza jeden zasób. Ale zaciera, kto jest klientem, a kto
zasobem, w miejscu, gdzie ta różnica jest całą treścią: `market-data` jest API dla wielu przyszłych
konsumentów, a terminal jest jednym z nich.

### MSAL bez warstwy reactowej

`@azure/msal-browser`, opakowany cienkim modułem w `src/auth/`. Token jest potrzebny przede
wszystkim w `data/http.ts`, czyli w kodzie, który nie jest komponentem i nie ma jak wejść w hooka.
`@azure/msal-react` dokłada zależność i kontekst po to, żeby obsłużyć jedno miejsce, gdzie stan
logowania rzeczywiście dotyka widoku — wskaźnik w powłoce. To jedno miejsce weźmie stan przez zwykły
subskrybowalny store, tak jak reszta terminala bierze stan źródeł.

### Przepływ przekierowaniem, nie oknem

`loginRedirect` zamiast `loginPopup`: nie ginie pod blokadą wyskakujących okien i nie wymaga od
operatora niczego poza tym, co już zna z portalu Azure. Kosztuje pełne przeładowanie strony, ale
układ siatki i tak leży w `localStorage` (`gridStore.ts`), a MSAL wraca pod adres, z którego
wyszedł — więc operator wraca do widoku, na którym był.

Rozstrzygnięcie przekierowania (`handleRedirectPromise`) musi się dokonać **zanim** cokolwiek
zacznie wołać archiwum, bo pierwszy render już subskrybuje świece.

### Pamięć podręczna MSAL w `sessionStorage`

Pamięć procesu gubiłaby konto przy każdym przeładowaniu strony i kazała logować się od nowa.
`localStorage` trzymałby je po zamknięciu karty. `sessionStorage` przeżywa przeładowanie i ginie
z kartą — to jest właściwy kompromis dla terminala operatorskiego.

### Poświadczenie dokłada wspólny klient, nie wywołanie

`jsonClient` w `data/http.ts` dostaje dostawcę tokenu i dokłada nagłówek sam. Ani `archive.ts`, ani
`gatewaySource.ts` nie dowiadują się o istnieniu tokenu — a trasa dopisana w przyszłości niesie
poświadczenie, bo nie ma jak go nie nieść. Tam też mieszka jedna ponowna próba po odmowie
z powodu tożsamości, ze strażnikiem przed pętlą „odmowa → odnowienie → odmowa".

### Terminal zostaje serwowany bez logowania

Nie dochodzi `staticwebapp.config.json` z regułą wymagającą zalogowania. Pliki terminala nie niosą
danych, a druga bramka oznaczałaby dwa logowania dla jednego operatora: raz do Static Web Apps, raz
do MSAL. Tożsamość ustala MSAL, egzekwuje ją archiwum — i to jest ta warstwa, w której leżą dane.

### Brak konfiguracji tożsamości oznacza tryb lokalny, nie awarię

Terminal bez `VITE_ENTRA_*` nie dokłada tokenu i nie prowadzi przez logowanie. Archiwum
bez ustawienia wymagającego tożsamości platformowej wydaje bilety każdemu. **Bilet jest wymagany
zawsze**, także lokalnie — jedna ścieżka kodu w obu środowiskach, testowana tak samo, zamiast
gałęzi „na produkcji inaczej", która ujawnia się dopiero po wdrożeniu.

Symetrycznie do `capital-access-control`: archiwum skonfigurowane jako stojące za Easy Auth
**odmawia wydania biletu bez tożsamości**, zamiast zakładać, że warstwa przed nim działa. Jedna
błędna linia w Terraformie zostawiłaby inaczej otwartą wytwórnię biletów, czyli otwarty strumień.

## Risks / Trade-offs

**Easy Auth mimo wszystko przechwytuje zapytanie wstępne** → Zapytanie `OPTIONS` bez poświadczenia
dostałoby `401` i żadne wywołanie z przeglądarki by nie przeszło. Mitygacja: sprawdzenie jednym
`curl -X OPTIONS` **zaraz po zastosowaniu konfiguracji infrastruktury, przed pracą po stronie
terminala** — to jest najtańszy możliwy moment na odkrycie tego. Odwrót, jeśli sprawdzenie wypadnie
źle: zdjąć `require_authentication` na poziomie platformy i weryfikować token Entra w aplikacji
(FastAPI, biblioteka JWT z kluczami publicznymi dzierżawy). Kosztuje więcej kodu decydującego
o dostępie i dlatego nie jest wyborem pierwszym — ale nie zmienia ani specyfikacji, ani reszty
zadań, bo obserwowalne zachowanie zostaje to samo.

**Bilety w pamięci a druga instancja** → Zwiększenie `worker_count` albo dołożenie instancji
zamienia bilety w losowe odmowy strumienia — awaria, która wygląda jak problem z siecią. Mitygacja:
komentarz w kodzie przy magazynie biletów i wzmianka w `README.md` modułu; przeniesienie do
Postgresa jest wtedy zmianą lokalną.

**Okno między wdrożeniem infrastruktury a wdrożeniem modułu** → Ścieżka strumienia zwolniona
z Easy Auth, zanim moduł sprawdza bilety, to otwarty WebSocket w internecie. Mitygacja: kolejność
wdrożenia jest odwrotna i nieprzestawialna — najpierw moduł ze sprawdzaniem biletu (wtedy jeszcze
za Easy Auth, więc nieosiągalny), potem zwolnienie ścieżki. Ta sama zasada, która porządkowała
`provision-azure-platform`: nic nie staje w internecie, zanim nie wymaga uwierzytelnienia.

**Środowiska podglądowe Static Web Apps** → Wdrożenie z pull requesta dostaje własny adres, którego
nie ma ani na liście CORS, ani wśród adresów powrotnych rejestracji SPA. Podgląd będzie się
otwierał i nie dostanie danych. Akceptowane: podgląd służy dziś do obejrzenia interfejsu, nie do
pracy z danymi.

**Konto gościa B2B** → Loguje się UPN-em innym niż własny adres i łatwo o pomyłkę przy pierwszym
logowaniu. Ta sama pułapka, którą odkryto przy DBeaverze (zadanie 11.3 `provision-azure-platform`).
Mitygacja: wzmianka w `README.md` terminala.

**Rozmiar paczki terminala** → `@azure/msal-browser` to około stu kilobajtów po kompresji. Static
Web Apps w warstwie Free, jeden operator — bez znaczenia. Po stronie serwera nie przybywa nic poza
słownikiem biletów.

## Migration Plan

Kolejność wynika z jednego zdania: **ścieżka strumienia nie może wyjść spod Easy Auth, zanim moduł
nie zacznie sprawdzać biletów.**

1. **`market-data`**: trasa wydająca bilety, magazyn, sprawdzenie przy handshake'u, ustawienie
   wymagające tożsamości platformowej. Testy. Wdrożenie. Strumień stoi wtedy nadal za Easy Auth,
   więc z przeglądarki jest nieosiągalny tak samo jak dziś — nic się nie psuje i nic nie staje
   otworem.
2. **`infra`**: zakres na rejestracji `market-data`, rejestracja SPA terminala, `excluded_paths`
   dla ścieżki strumienia, CORS, adres terminala. `apply`. **Zaraz po nim sprawdzenie zapytania
   wstępnego** — od jego wyniku zależy, czy dalej idzie się drogą główną, czy odwrotem opisanym
   w Risks.
3. **`terminal`**: MSAL, nagłówek we wspólnym kliencie, bilet przed każdym zestawieniem strumienia,
   wskaźnik stanu zalogowania. Testy. Build z `VITE_ENTRA_*`. Wdrożenie.
4. **Weryfikacja end-to-end** i zamknięcie zadania 11.4 w `provision-azure-platform`.

**Rollback**: każdy krok cofa się osobno. Cofnięcie kroku 2 przywraca Easy Auth na ścieżce strumienia
— czyli stan dzisiejszy, w którym terminal nie widzi danych, ale nic nie jest wystawione. Cofnięcie
kroku 3 zostawia wdrożone archiwum, które nadal działa dla konsumenta z tokenem. Kroku 1 nie trzeba
cofać w żadnym z tych scenariuszy: sprawdzanie biletu na ścieżce chronionej Easy Auth nikomu nie
przeszkadza.

## Open Questions

- Czy środowiska podglądowe Static Web Apps mają kiedyś dostać własne wpisy CORS i adresy powrotne.
  Dotyczy wyłącznie wygody przeglądania pull requestów; nie zmienia ani specyfikacji, ani podziału
  zadań, a wpisy są rozszerzalne w każdej chwili.
