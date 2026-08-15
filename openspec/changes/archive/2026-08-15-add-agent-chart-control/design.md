## Context

Motywacja: `proposal.md`, „Why". Wymagania: delty w `specs/`.

Co ta zmiana zastaje:

- **Narzędzia agenta pochodzą wyłącznie z `market-mcp`.** `agent/tools/client.py` jest
  jedynym miejscem, gdzie importowany jest `mcp`, i jedynym źródłem `ToolDescriptor`.
  `graph.py` w węźle `run_tools` woła `tool_server.call(name, arguments)` — jeden serwer,
  jedno wywołanie, sufit tury na wspólnym liczniku.
- **`market-mcp` jest czytające z założenia** (CLAUDE.md, `market-mcp-tools`) i nic o
  terminalu nie wie. Zapis nie może iść tamtędy.
- **Terminal nic nie publikuje.** Nikt od niego nie zależy; to konsument gatewaya,
  market-data i agenta. Zmiana tego byłaby zmianą architektury, nie funkcji.
- **Slot siatki już jest trwały**: `gridStore` zapisuje symbol, interwał i wskaźniki do
  `localStorage` pod `terminal.grid.v1`, a `GridView` oddaje je wykresowi przy montowaniu.
- **Baza agenta jest osobna** (`agent`, własne migracje), a `alembic upgrade head` jest
  ręcznym krokiem operatora — deploy nie migruje.

## Goals / Non-Goals

**Goals:**

- Model ustawia zawartość aktywnego slotu jednym wywołaniem, deklaratywnie.
- Ustawienie przeżywa odświeżenie i restart, bez pytania terminala o zgodę.
- Granica zapisu nazwana w specyfikacji: wykres i nic więcej.

**Non-Goals:**

- Sterowanie slotem wskazanym po nazwie (s1–s6), układem siatki i zakładkami terminala.
- Zapisy poza wykresem: zbieranie par, kasowanie danych, zlecenia, konfiguracja.
- Narzędzia zapisujące w `market-mcp` — ten moduł zostaje czytający.
- Potwierdzanie zmian przez operatora i cofanie ich przyciskiem „cofnij" (operator cofa
  wybierakiem, tak jak każdą własną zmianę).
- Współdzielenie stanu wykresu między dwiema otwartymi kartami terminala.

## Decisions

### Narzędzie jest lokalne dla modułu `agent`, obok narzędzi serwera

`agent/tools/` dostaje drugie źródło: rejestr narzędzi własnych, z ręcznie napisanym
`ToolDescriptor` i `input_schema`. `graph.py` kieruje wywołanie do tego rejestru, jeśli
nazwa do niego należy, a do `tool_server` w przeciwnym razie. Sufit tury, ślad wywołania i
trzy wyniki (`ok` / `refused` / `unavailable`) zostają wspólne — z punktu widzenia modelu i
transkryptu to jest zwykłe narzędzie.

Rozważane i odrzucone: **narzędzie w `market-mcp`**. Kusi, bo pętla tury nie zmieniłaby się
wcale. Przegrywa na dwóch rzeczach naraz: `market-mcp` musiałby wiedzieć o terminalu (nie
wie i nie ma po co), i przestałby być czytający, co jest jego całą charakterystyką w
`market-mcp-tools`. Zapis wszedłby wtedy także agentom, które sięgają po market-mcp z
pulpitu, a to nie jest to, o co proszono.

Drugie odrzucone: **osobny serwer MCP terminala**. Uczciwe architektonicznie, ale to nowy
moduł, nowy deploy i nowa tożsamość w Entra dla jednego narzędzia.

### Polecenie jest deklaratywne i numerowane, a terminal trzyma kursor

Nowa tabela w bazie agenta (`chart_commands`): rosnący numer, znacznik czasu, sesja,
i treść polecenia — symbol, interwał, lista wskaźników. Kontrakt publikuje ostatnie
polecenie i pozwala zapytać „co nowszego niż N".

Terminal trzyma **numer ostatnio zastosowanego polecenia** u siebie, w `localStorage`,
obok konfiguracji siatki. Stosuje tylko polecenia nowsze i nigdy tego samego dwa razy.

Rozważane i odrzucone: **lustro stanu** — agent trzyma „stan wykresu", terminal go
odzwierciedla. Wtedy każda ręczna zmiana operatora musiałaby wracać do agenta, inaczej
kolejny odczyt cofałby ją w tył. To czyni agenta właścicielem stanu terminala i zmusza
terminal do publikowania — dwie rzeczy, których ta architektura nie robi. Polecenia
z kursorem dają to samo, czego operator chciał (przeżywa odświeżenie), bez tego kosztu:
trwałość niesie `gridStore`, który już ją ma, a agent niesie wyłącznie „co kazano".

Odrzucone też: **kursor po stronie agenta** („zastosowane / niezastosowane"). Wymagałby,
żeby terminal ogłaszał, co zrobił, i psułby się przy dwóch otwartych kartach.

### Odmowa jest po stronie agenta, nie terminala

Narzędzie sprawdza polecenie **zanim** je zapisze: identyfikatory i granice parametrów
przeciw katalogowi wskaźników, symbol i interwał przeciw zbieranym parom. Oba odczyty idą
istniejącą drogą — przez `market-mcp` — więc moduł nie dokłada sobie połączenia do
market-data.

Sprawdzenie w agencie, a nie w terminalu, bo odmowa ma trafić **do modelu**, w tej samej
turze, ze zdaniem, co poprawić (`agent-tools`, „Odmowa narzędzia jest wynikiem"). Odmowa,
która dociera do terminala, dociera nie do tego, kto może ją naprawić.

Polecenie jest zapisywane **w całości albo wcale**: trzy wskaźniki, z których jeden jest
nieznany, to odmowa, a nie dwa narysowane.

### Aktywny slot, nie slot wskazany po nazwie

Polecenie nie niesie identyfikatora slotu; terminal stosuje je do aktywnego. Model nie zna
układu siatki i nie ma po co go poznawać w pierwszej wersji, a „aktywny" jest jedynym
slotem, o którym operator myśli, mówiąc „pokaż".

Konsekwencja, którą trzeba znać: operator, który zmieni aktywny slot między turą a
odczytem, dostanie zmianę w innym slocie niż ten, na który patrzył. Dlatego panel mówi,
co zostało zmienione, zamiast zmieniać po cichu.

### Migawka wykresu jedzie w żądaniu tury, nie w osobnym odczycie

Model musi wiedzieć, co jest na ekranie, żeby „dołóż jeszcze wolniejszą średnią" miało
sens. Migawka (symbol, interwał, wskaźniki) jedzie jako opcjonalne pole żądania tury i
trafia do promptu jako kontekst — nie do transkryptu i nie do bazy.

Rozważane i odrzucone: **narzędzie czytające stan wykresu**. Kosztuje obrót tury i pieniądze
za coś, co nadawca żądania i tak wie, a przy okazji wymagałoby, żeby terminal to
opublikował.

### Prompt systemowy musi nazwać to narzędzie

Prompt agenta jest wersjonowany w bazie (`prompt_revisions`) i to on decyduje, kiedy model
sięga po co. Narzędzie nienazwane w prompcie istnieje, ale bywa nieużywane — to zadanie,
nie przypis.

## Risks / Trade-offs

- **Agent zmienia wykres, na który operator właśnie patrzy** → zmiana zawsze zostawia zdanie
  w panelu, a cofnięcie jest tym samym ruchem co własna zmiana operatora. Bez potwierdzania,
  zgodnie z decyzją operatora.
- **Dwie karty terminala** → każda ma własny kursor, więc obie zastosują to samo polecenie
  u siebie. To jest zachowanie zamierzone; wspólny stan między kartami jest Non-Goal.
- **Sprawdzenie w agencie może rozjechać się z katalogiem archiwum** → sprawdzenie czyta
  katalog przez `market-mcp` przy wywołaniu, zamiast trzymać kopię (`agent-tool-access`,
  „Moduł nie trzyma kopii tego, co ogłasza serwer narzędzi").
- **Agent bez serwera narzędzi** — konfiguracja wspierana (`MARKET_MCP_URL` bywa pusty) —
  **nie ma jak sprawdzić symbolu ani wskaźnika**. Wtedy narzędzie własne pozostaje
  dostępne, ale odmawia z powodu „nie mam jak sprawdzić, czy to jest zbierane", zamiast
  zapisywać polecenie na ślepo.
- **Migracja bazy agenta jest ręczna** → wdrożenie kodu bez `alembic upgrade head` da moduł,
  który wstaje i odmawia zapisu polecenia. Zadanie wdrożeniowe, nie zapomniany krok.
- **Sufit tury dzielony z narzędziami archiwum** → model, który zużyje obroty na odczyty,
  może nie zdążyć ustawić wykresu. Zostawione: sufit istnieje po to, żeby tura się kończyła.

## Open Questions

- Czy panel ma pokazywać **historię** poleceń agenta (co i kiedy ustawił), czy wystarczy
  zdanie o ostatnim. Nie zmienia kontraktu ani zakresu zadań — tabela już to niesie.
