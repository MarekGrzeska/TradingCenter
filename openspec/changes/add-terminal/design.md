## Context

Zobacz `proposal.md — Why`. Tu liczy się to, z czym terminal się styka.

`capital-gateway` publikuje HTTP z OpenAPI oraz `/ws/stream?symbol=&resolution=`. Trzy jego
własności kształtują ten projekt:

- **Szew czasu jest celowy.** REST oddaje `Candle.ts` jako łańcuch ISO, WebSocket oddaje
  `candle.time` jako sekundy od epoki na początku okresu. Biblioteka wykresu indeksuje po
  sekundach, więc konwersja musi się wydarzyć w terminalu, w jednym miejscu.
- **Subskrypcja jest w adresie, nie w protokole.** Para symbol plus rozdzielczość siedzi w
  query stringu połączenia. Nie ma wiadomości „subscribe", więc jedno gniazdo nie obsłuży dwóch
  par — sześć różnych par w siatce `3x2` to sześć gniazd z przeglądarki.
- **Świeca w budowie jest składana po stronie gatewaya.** `ohlc.event` przyszedł zero razy w
  ciągu 60 s na `MINUTE_5`, kwotowanie 296 razy. Bez świecy w budowie wykres stoi pięć minut.
  Ta świeca repaintuje i po restarcie gatewaya zaniża maksimum i minimum.

Gateway **nie wystawia CORS** — nie ma na to powodu, dopóki jego konsumentem jest inna usługa.
Przeglądarka na innym porcie to zmienia, a rozwiązanie nie może polegać na zmianie gatewaya.

Gateway **nie przechowuje niczego**. `MINUTE_5` sięga około dwóch lat wstecz i nic nie odzyska
tego, co dalej. Baza świec to osobny moduł, którego jeszcze nie ma.

## Goals / Non-Goals

**Goals:**

- Warstwa danych, którą da się podmienić na bazę świec bez dotykania wykresu, siatki ani
  wyszukiwarki.
- Wykres, który przy sześciu slotach i ~30 wiadomościach na sekundę nie przerysowuje Reacta.
- Zero zależności od cudzego design systemu — tokeny i komponenty własne.
- Moduł stojący samodzielnie: `pnpm install && pnpm dev` po skopiowaniu katalogu.

**Non-Goals:**

- Uwierzytelnianie i wielu użytkowników. Terminal chodzi lokalnie, obok gatewaya w trybie demo.
- Wskaźniki, narzędzia rysunkowe, zapisywane workspace'y — po jednym slocie na instrument.
- Layout mobilny. Terminal jest desktopowy z założenia.
- Składanie zleceń. `Positions`, `Orders`, `Account` to wpisy w rejestrze zakładek i nic więcej.
- Własne cache'owanie historii między sesjami. Trwałe jest ustawienie slotu, nie jego dane.
- Wdrożenie do Azure. Kierunek jest znany — Static Web Apps dla terminala — ale ta zmiana buduje
  i uruchamia lokalnie. Pliki wdrożeniowe powstają wtedy, gdy będzie co wdrażać.

## Decisions

### Vite + React + TypeScript, bez frameworka aplikacyjnego

Terminal to SPA rozmawiająca z lokalną usługą. SSR nie ma czego renderować po stronie serwera,
bo dane są z gniazda, a nie z bazy. Vite daje proxy w developmencie, którego i tak potrzebujemy
na CORS. Odrzucone: Next.js — wnosi serwer, którego nikt tu nie obsługuje, i drugi runtime do
utrzymania obok gatewaya.

Docelowo terminal ma stanąć na **Azure Static Web Apps**, a to jest hosting plików statycznych —
co potwierdza wybór: build daje katalog `dist`, nie proces. Odwrotnie niż przy Next.js, gdzie
Static Web Apps musiałyby uruchomić runtime i wybór frameworka wracałby jako koszt wdrożenia.

### CORS obchodzimy proxy Vite, nie zmianą gatewaya

Dev server proxuje `/api/*` na `http://localhost:8010` i `/ws/*` na `ws://localhost:8010`, więc
przeglądarka widzi jedno pochodzenie. Odrzucone: dołożenie CORS do `capital-gateway` — to zmiana
zachowania modułu wymuszona wygodą jego konsumenta, a zaczyna się od listy dozwolonych pochodzeń,
której nikt później nie pilnuje.

Adres HTTP i adres WebSocketa są konfigurowalne **osobno** — `VITE_GATEWAY_HTTP` i
`VITE_GATEWAY_WS` — a każdy przyjmuje zarówno ścieżkę względną, jak i pełny URL. Lokalnie oba są
względne (`/api`, `/ws`) i idą przez proxy Vite. Dlaczego osobno, a nie jeden wspólny adres —
niżej.

### Azure Static Web Apps poda statyki, ale nie przeprowadzi strumienia

Kierunek wdrożenia to Static Web Apps dla terminala. SWA **nie może** przy tym stać między
terminalem a gatewayem, i przesądzają to trzy rzeczy:

- Proxy `/api` w SWA obsługuje wyłącznie HTTP. WebSocket nie jest wspierany — wprost
  w dokumentacji, nie przez przeoczenie.
- Żądanie przez to proxy ma sufit **45 s**. Zmierzony głęboki odczyt — `OIL_CRUDE` `MINUTE_5`
  × 20 000 → 30 żądań, 26,2 s — mieści się w nim ledwo, a głębszy już nie.
- `staticwebapp.config.json` nie przepisuje na zewnętrzny adres. `rewrite` celuje w plik
  w aplikacji albo w `/api`, bez wildcardów w celu.

Stąd rozdzielone adresy. Wariant, w którym statyki idą z SWA, a HTTP i strumień wprost na hosta
gatewaya, MUST dać się skonfigurować bez dotykania kodu. Wariant z prawdziwym reverse proxy przed
obydwoma — Front Door albo Application Gateway — wraca do dwóch adresów względnych i działa tak
samo. Rozstrzygnięcie należy do zmiany zajmującej się infrastrukturą; ta buduje i uruchamia
lokalnie.

Do zapisania, żeby nie zaskoczyło później: `capital-gateway` nie ma własnego uwierzytelnienia,
trzyma poświadczenia providera i wystawia `POST /orders`. Wariant z gatewayem osiągalnym wprost
z przeglądarki wymaga postawienia przed nim czegoś, co pyta o tożsamość. To nie jest problem tej
zmiany, ale jest problem.

### `MarketDataSource` — jeden interfejs, trzy przyszłe implementacje

```ts
type Bar = {
  time: number          // sekundy od epoki, początek okresu — jedna postać dla REST i streamu
  open: number; high: number; low: number; close: number
  volume: number | null // null znaczy "źródło nie podaje", nie "zero"
  forming: boolean
}

interface MarketDataSource {
  readonly id: 'gateway' | 'mock'
  searchInstruments(query: string, signal: AbortSignal): Promise<Instrument[]>
  listInstruments(signal: AbortSignal): Promise<InstrumentPage>
  history(req: { symbol: string; resolution: Resolution; count: number },
          signal: AbortSignal): Promise<Bar[]>
  subscribe(symbol: string, resolution: Resolution,
            sink: (event: StreamEvent) => void): () => void
}
```

`Bar` jest normalizowany na wejściu do terminala, nie na wyjściu do wykresu — konwersja ISO na
sekundy dzieje się raz, w adapterze, i tylko adapter wie, że gateway ma dwie konwencje. Baza
świec wejdzie jako trzecia implementacja tego samego interfejsu.

Odrzucone: oddawanie DTO gatewaya wprost do komponentów. Wtedy każdy komponent zna szew czasu,
a dołożenie bazy oznacza przejście po wszystkich.

### Ref-counted hub gniazd, klucz `symbol|resolution`

Hub trzyma mapę `klucz → { socket, sinks: Set, refCount }`. Pierwszy odbiorca otwiera gniazdo,
kolejni dostają to samo, ostatni odchodzący je zamyka. Dwa sloty na `US100 MINUTE_5` to jedno
gniazdo. Sześć różnych par to sześć gniazd — i to jest sufit, bo więcej slotów niż sześć siatka
nie ma.

Odrzucone: jedno gniazdo multipleksowane po wszystkich parach. Wymagałoby protokołu subskrypcji
po stronie gatewaya, którego kontrakt nie ma; to zmiana w cudzym module dla wygody tego.

### Wznawianie: rosnący odstęp plus dociągnięcie luki

Po zerwaniu hub ponawia z odstępem `min(30 s, 2^n × 500 ms)` z rozrzutem, a po powrocie każdy
odbiorca dociąga ostatnie świece przez `history()` i scala je po znaczniku czasu. Bez tego
przerwa zostaje w serii jako dziura, której nic później nie zasypie — gateway nie przechowuje
niczego, ale REST wciąż sięga do providera.

### Wykres pisze do canvasu, nie do stanu Reacta

Sześć slotów przy ~5 kwotowaniach na sekundę na parę to ~30 zdarzeń na sekundę. Trzymanie serii
w `useState` to 30 przerysowań drzewa na sekundę. Zamiast tego: wykres tworzony raz w
`useLayoutEffect` na `ref`ie, historia przez `series.setData()`, każda kolejna świeca przez
`series.update()`. React trzyma tylko to, co zmienia się rzadko: symbol, rozdzielczość, stan
(ładowanie / błąd / pusto) i wartości spod kursora, te ostatnie dławione do jednej klatki.

Efekty muszą znieść podwójne wywołanie w `StrictMode` — sprzątanie kończy subskrypcję i woła
`chart.remove()`, a tworzenie nie zakłada pustego kontenera. `ResizeObserver` odpowiada za
rozmiar; slot nie przekazuje wymiarów w propsach.

Wersja biblioteki wykresu zostaje **przypięta**, a API czytamy z jej deklaracji typów, nie z
tutoriali — v5 zmieniła sposób dodawania serii względem v4 i połowa materiałów w sieci opisuje
starą.

### Wyścigi rozstrzyga licznik generacji, nie tylko `AbortController`

Przy szybkim przełączaniu rozdzielczości `AbortController` przerywa żądanie, ale odpowiedź już
odebrana potrafi dojść. Każdy odczyt dostaje numer generacji; wynik z generacji innej niż bieżąca
jest odrzucany, zanim dotknie serii. Ten sam licznik chroni wyszukiwarkę, gdzie zapytania idą po
dławieniu 250 ms.

### Stan aplikacji na `useSyncExternalStore`, bez biblioteki

Do utrzymania są trzy rzeczy: konfiguracja siatki, wybrane źródło danych, stan połączeń. Hub
gniazd już jest zewnętrznym źródłem prawdy, a `useSyncExternalStore` jest po to, żeby takie
źródło podpiąć. Odrzucone: Zustand lub Redux — zależność za coś, co mieści się w kilkudziesięciu
liniach i tak samo się testuje.

### Sloty są trwałe i mają stabilną tożsamość

Konfiguracja to sześć slotów z własnymi identyfikatorami; układ decyduje wyłącznie o tym, ile
z nich jest widocznych. Dzięki temu zejście z `3x2` na `2x2` nie kasuje ustawień dwóch ostatnich,
a klucz Reacta na identyfikatorze slotu — a nie na indeksie — nie każe wykresowi przemontować się
przy zmianie układu.

Zapis w `localStorage` pod kluczem z wersją (`terminal.grid.v1`). Odczyt przechodzi przez własny
strażnik typu; cokolwiek nie przejdzie, ląduje w koszu i terminal startuje z domyślnym układem.
Odrzucone: `zod` — jedna funkcja walidująca jeden kształt nie jest wart zależności.

### Źródło mock jest deterministyczne

Generator z ziarnem wyprowadzonym z symbolu (`mulberry32`), błądzenie losowe po cenie, świece
składane tą samą arytmetyką okresu co adapter gatewaya. Ten sam symbol daje ten sam wykres przy
każdym uruchomieniu, więc test może się do niego odwołać, a zrzut ekranu z wczoraj wygląda tak
samo dzisiaj.

### Tailwind v4 z tokenami w `@theme`

Kolory żyją jako CSS variables i są czytane zarówno przez klasy Tailwinda, jak i przez opcje
wykresu. Jedno miejsce ustawia kolor wzrostu, więc świeca i etykieta obok niej nie rozjeżdżają
się. Odrzucone: shadcn/ui — kilkanaście plików cudzego kodu w repo za komponenty, których tu
potrzeba pięć.

### Testy tam, gdzie da się coś stwierdzić

Warstwa danych jako testy jednostkowe: normalizacja czasu, scalanie świecy po znaczniku, liczenie
referencji w hubie, strażnik zapisanej konfiguracji, harmonogram wznawiania. Adapter gatewaya
przeciw `msw` na utrwalonych odpowiedziach. Komponenty przez `@testing-library/react` z zaślepioną
biblioteką wykresu — canvas nie jest asercją. Świadomie nie testujemy tego, jak wygląda wykres.

## Risks / Trade-offs

- **Strefa czasu w `ts` z REST-u.** Jeżeli łańcuch ISO nie niesie strefy, `Date.parse` weźmie go
  jako czas lokalny i historia przesunie się względem streamu o offset przeglądarki → parsujemy
  jawnie, a test na utrwalonej odpowiedzi z działającego gatewaya sprawdza konkretny symbol i
  konkretną godzinę. To pierwsza rzecz do potwierdzenia w implementacji.
- **Świeca w budowie kłamie o zakresie po restarcie gatewaya.** Maksimum i minimum obejmują tylko
  kwotowania widziane od jego startu → oznaczamy ją na ekranie i nie liczymy na niej niczego;
  zamknięta świeca od providera ją nadpisuje.
- **`DAY` i `WEEK` nie mają stałej długości okresu.** Gateway celowo nie zgaduje granicy dnia,
  bo zaczyna się ona na otwarciu sesji, a nie o północy UTC → terminal MUST NOT wyliczać granicy
  okresu sam; przy tych rozdzielczościach przyjmuje znacznik czasu od źródła takim, jaki przyszedł.
- **Sześć gniazd i ~30 wiadomości na sekundę.** Przy złym podejściu to 30 przerysowań drzewa
  Reacta → zapis idzie imperatywnie do serii, a dławienie zbiera wartości spod kursora do jednej
  klatki. Do zmierzenia, nie do założenia.
- **API biblioteki wykresu zmieniło się między wersjami.** Materiały w sieci opisują starsze →
  wersja przypięta, API czytane z deklaracji typów w paczce.
- **Brak volume na streamie.** Świeca ze strumienia ma `volume: null` → panel wolumenu pokazuje
  brak danej zamiast zera; wolumen jest tylko na świecach z historii.
- **Kod pisany pod jeden adres bazowy nie przeżyje wdrożenia.** Static Web Apps nie przeprowadzi
  WebSocketa, więc któryś wariant produkcyjny rozjedzie HTTP i strumień na dwa różne pochodzenia →
  dwa niezależne adresy w konfiguracji od pierwszego dnia, każdy przyjmujący ścieżkę względną albo
  pełny URL, i test na obu kształtach. Lokalnie nic z tego nie widać, bo proxy Vite podnosi jedno
  i drugie — dlatego to trzeba mieć w kodzie zanim zaboli.
- **Zapisany symbol może zniknąć.** Zmiana źródła danych albo katalogu providera unieważnia
  slot → slot mówi, że tego instrumentu nie ma w tym źródle, i pozwala wybrać inny; reszta
  siatki działa dalej.

## Migration Plan

Nowy moduł, nie ma czego migrować. `modules/terminal/` powstaje obok istniejących, nic poza nim
nie zmienia zachowania. Wycofanie to usunięcie katalogu — jeżeli coś przez to przestaje działać,
sięgało poza kontrakt.

Poza kodem modułu zmiana dotyka dwóch miejsc dokumentacji: tabeli modułów w `README.md` oraz
rysunku w `docs/architecture.md`, gdzie dziś stoi „terminal (later)".

## Open Questions

- Jak wygląda topologia w Azure: gateway osiągalny wprost z przeglądarki, czy oba za wspólnym
  reverse proxy — i co pyta o tożsamość, zanim ktoś dojdzie do `POST /orders`. Rozstrzygnięte jest
  tylko to, że terminal stanie na Static Web Apps. Reszta należy do zmiany zajmującej się
  infrastrukturą; tu wystarczy, że oba adresy są konfigurowalne niezależnie i znoszą obie postacie.
- Czy po powstaniu bazy świec historia będzie czytana wyłącznie z niej, czy gateway zostanie jako
  źródło ostatniego odcinka. Interfejs `MarketDataSource` znosi oba warianty, więc rozstrzygnięcie
  należy do zmiany wprowadzającej bazę.
