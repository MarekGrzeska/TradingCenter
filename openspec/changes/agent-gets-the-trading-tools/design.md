## Context

Motywacja jest w `proposal.md` — „Why". Tu tylko to, co kształtuje podejście.

Trzy fakty z kodu, które decydują o całej reszcie:

- **Agent ma już rejestr serwerów narzędzi.** `tools/registry.py` trzyma listę `ToolServer`,
  a `ToolServer(settings, prefix=…)` czyta triplet pól z `Settings` po nazwie prefiksu.
  Trzeci serwer to jedna linia w `from_settings` i trzy pola w `config.py`. Nic powyżej
  pakietu `tools` nie musi wiedzieć, że serwerów jest więcej.
- **Ślad wywołań zapada po turze, w jednej paczce.** `turn.py:207` woła
  `store.record_tool_calls` dopiero po `append_agent_message`, bo `tool_calls.message_id`
  jest `NOT NULL` z kluczem obcym na `messages` — a ta wypowiedź nie istnieje, dopóki tura
  się nie skończy (`migrations/versions/0002_tool_calls.py`, komentarz przy kolumnie mówi to
  wprost). Ścieżka wyjątku w `turn.py` ustawia `calls = []`, więc tura, która padła, nie
  zostawia po wywołaniach nic. Przy narzędziach czytających to strata zapisu; przy
  zapisujących to pozycja, o której nikt nie wie.
- **`outcome` ma trzy dopuszczalne wartości** — `ok`, `refused`, `unavailable`, pilnowane
  `CHECK`-iem. `unavailable` znaczy „serwer nie odpowiedział", co dla odczytu jest pełną
  informacją, a dla zapisu nie jest żadną.

Po stronie `teams` istnieje gotowy wzorzec obu rzeczy, których ta zmiana potrzebuje:
`teams/tools/client.py:236` czyta `tool.annotations.readOnlyHint` do pola `read_only: bool |
None`, a `teams/tools/assignment.py:244` traktuje `read_only is True` jako czytające, z
`None` jako „nieoznaczone". Kopiujemy kształt, nie kod — między modułami nie ma importów.

## Goals / Non-Goals

**Goals:**

- Trzeci serwer narzędzi w agencie, konfigurowany i psujący się niezależnie od dwóch
  istniejących.
- Ślad wywołania ruszającego rachunek, który przetrwa turę bez wypowiedzi, i skutek
  „nieznany" jako wartość, nie jako brak wiersza.
- Rozróżnienie „zapisujące / czytające" wzięte od serwera, nie wpisane w agenta.

**Non-Goals:**

- Ekran pozycji w terminalu. Operator nie ma dziś gdzie zobaczyć ani zamknąć pozycji poza
  rozmową; to jest prawdziwa luka, ale jest osobną zmianą i spec ją nazywa (`agent-tools`,
  akapit o odwracalności), zamiast udawać, że jej nie ma.
- Potwierdzanie zleceń i granice handlowe. Odrzucone świadomie przy proponowaniu zmiany.
- Zmiana czegokolwiek w `trading-mcp`. Ten moduł nie wie, ilu ma wołających, i nie ma się
  po tej stronie nic dowiedzieć.

## Decisions

### D1. Ślad przed wysłaniem: `message_id` staje się nullowalny, wiersz jest domykany na końcu tury

Wywołanie zapisujące dostaje wiersz **przed** wysłaniem, z `message_id = NULL` i skutkiem
`unknown`. Po powrocie odpowiedzi wiersz jest aktualizowany o skutek, tekst i czas trwania;
po `append_agent_message` — o `message_id`. W ścieżce szczęśliwej czytelnik nie widzi żadnej
różnicy: wiersz ma to samo `message_id`, co dziś, i tę samą kolejność. `NULL` zostaje
wyłącznie po turze, która nie doszła do wypowiedzi.

Wywołania czytające zostają na dotychczasowej ścieżce — jedna paczka po turze. Nie z
oszczędności, a dlatego że odczyt, który przepadł, nie zostawia po sobie niczego na
rachunku, więc dwufazowy zapis kupiłby tam tylko dwa zapytania na wywołanie.

Migracja: `ALTER COLUMN message_id DROP NOT NULL` i rozszerzenie `CHECK`-a na
`('ok','refused','unavailable','unknown')`. Indeks `ix_tool_calls_message` prowadzi po
`message_id` i przyjmuje `NULL` bez zmiany; osierocone wiersze czyta się indeksem
sesyjnym, który już jest.

Wiersze osierocone wychodzą **osobną trasą** (`GET /sessions/{id}/unclaimed-tool-calls`),
a nie nowym polem na odczycie transkryptu. Pierwotnie zapisano tu pole, i to była pomyłka
w jednym punkcie: `GET /sessions/{id}/messages` publikuje dzisiaj *listę*, więc dołożenie
pola znaczy zmianę odpowiedzi z listy na obiekt. Terminal jest wdrażany osobno (Static Web
App), więc w oknie między jednym wdrożeniem a drugim starszy build dostałby obiekt tam,
gdzie wywołuje `raw.map` — transkrypt przestałby się czytać, i to nie tylko dla rozmów,
które czegokolwiek dotknęły na rachunku. Osobna trasa nie ma tego okna: starszy terminal
jej nie zna i działa dalej, nowszy dokłada jedno żądanie równolegle z tym o wiadomości.

*Rozważone i odrzucone:*

- **Osobna tabela na wywołania ruszające rachunek**, jak wiersze zleceń w `teams`. Wtedy
  odczyt transkryptu musi łączyć dwie tabele, a wymaganie `agent-tools` („Odczyt transkryptu
  MUST zwracać wywołania przy wypowiedzi agenta, w kolejności, w jakiej padły") dostaje dwa
  źródła i kolejność do posklejania. `teams` ma osobną tabelę, bo tam wiersz niesie
  symbol, kierunek i wielkość jako kolumny, po których operator porównuje przebiegi —
  agent nie porównuje rozmów i nie ma po co rozbierać argumentów na kolumny.
- **Utworzenie wiersza wypowiedzi agenta na początku tury**, żeby `message_id` istniał od
  razu. Naprawiłoby to więcej — także turę, która pada bez wyjątku — ale zmienia to, co
  widzi czytelnik transkryptu w trakcie tury: pustą wypowiedź agenta. To jest zmiana w
  `agent-chat` („Odpowiedź płynie strumieniem"), której ta propozycja nie zgłasza, i wtedy
  osobna decyzja, nie skutek uboczny tej.
- **Zostawienie `unavailable` w roli „nieznany"**. Fizycznie to jedno zdarzenie, ale spec
  wymaga, żeby nieznany skutek nie czytał się jak nieudany, a model po nim nie ponawiał
  wywołania — a po `unavailable` ponowienie odczytu jest właśnie tym, co ma robić. Jedna
  wartość dla dwóch reguł byłaby regułą, której nie da się napisać.

### D2. Co jest wywołaniem ruszającym rachunek: `readOnlyHint` serwera, z ostrożnym domyślnym

`ToolDescriptor` w `agent/tools/client.py` dostaje pole `read_only: bool | None`, czytane z
`tool.annotations.readOnlyHint`. Wywołanie liczy się jako ruszające rachunek, gdy
`read_only is not True` **i** ogłosił je serwer, który potrafi zapisywać. Nieoznaczone
narzędzie z takiego serwera liczy się jako zapisujące — to jest domyślne, które w razie
pomyłki zapisuje wiersz za dużo, a nie o jeden za mało.

*Rozważone i odrzucone:* imienna lista czterech nazw w agencie. Wymaganie „Moduł nie trzyma
kopii tego, co ogłasza serwer narzędzi" zakazuje tego dosłownie, a piąte narzędzie
zapisujące dołożone w `trading-mcp` byłoby wtedy narzędziem bez śladu — i nic w agencie by
tego nie zauważyło.

### D3. `trading-mcp` nie dostaje tokenu operatora

Trzeci `ToolServer` powstaje bez `forwards_operator_token`. `teams-mcp` niesie poświadczenie
osoby, bo zespół, który powstał na tożsamości modułu, byłby zespołem tego modułu i
niewidocznym dla operatora. Rachunek jest jeden, wspólny, i nie ma nikogo, w czyim imieniu
można by go ruszyć inaczej — a `trading-mcp` żadnego takiego nagłówka nie czyta.

### D4. Sufit czasu: 35 s, ta sama liczba i to samo uzasadnienie, co w `teams`

`trading_mcp_request_timeout_seconds = 35.0`, bo `trading-mcp` czeka na gateway do 30 s
(`trading_mcp/config.py:47`). Sufit niższy niż tamten urwałby się po naszej stronie zapisu,
który już się wykonał — czyli w kształcie najgorszym z możliwych, bo model nie dowiedziałby
się o zleceniu, które istnieje. `teams` ma tu 35 s z dokładnie tym uzasadnieniem i nie ma
powodu, żeby agent liczył inaczej.

## Risks / Trade-offs

**Pozycji nie da się zamknąć bez agenta** → Terminal nie ma ekranu pozycji, a `trading-mcp`
przyjmuje tylko wołających z listy, więc przy niedostępnym agencie jedyną drogą jest interfejs
capital.com. Ograniczeniem skutku jest rachunek demonstracyjny wymuszony u gatewaya. Spec
mówi to wprost, zamiast to przemilczeć; ekran pozycji jest kandydatem na następną zmianę.

**Wiersz osierocony niesie argumenty zlecenia i żadnego kontekstu rozmowy** → `session_id`
jest w nim od początku, więc wiadomo, w której rozmowie padło; brakuje tylko wypowiedzi,
której nie było. Wychodzą osobną trasą i lądują na końcu transkryptu — jedna trasa i jedna
gałąź w terminalu, nie nowy widok.

**Kontrakt agenta nie jest generowany** → Jedyną kontrolą pairingu agent↔terminal są testy
terminala i jego ręcznie pisane DTO. Nowa wartość `outcome` i nowa lista muszą wejść do
`modules/terminal` w tej samej zmianie, bo nic tego nie złapie za nas.

**Narzędzia nie pojawią się po deployu obrazu** → Pojawią się po `terraform apply` ręką
operatora i po restarcie agenta, tak jak przy `market-mcp` i `teams-mcp` (CLAUDE.md, „The
agent's tools arrive at `apply`, not at deploy"). Wycofanie jest tą samą dźwignią: wyczyścić
`TRADING_MCP_URL`, zrestartować — wiersze w `tool_calls` zostają i mówią, co się działo,
kiedy narzędzia były.

**Dwa moduły wołają teraz `trading-mcp`** → Rachunek jest jeden, więc agent i przebieg
zespołu mogą sięgnąć po niego w tej samej chwili. Nic tego nie szereguje i ta zmiana tego
nie wprowadza: capital.com liczy swoje 10 żądań na sekundę przeciw rachunkowi, więc objawem
będzie spowolnienie, a nie sprzeczny stan. Zlecenia i tak rozlicza provider, nie ta
platforma.
