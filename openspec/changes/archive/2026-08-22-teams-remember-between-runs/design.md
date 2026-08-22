## Context

Motywacja: `proposal.md` — Why. Wymagania: delty w `specs/`.

Trzy fakty o dzisiejszym kodzie kształtują całe podejście.

**Rejestr narzędzi zna wyłącznie serwery sieciowe.** `ToolServerRegistry.from_settings` buduje
dokładnie dwa `ToolServer`, każdy czytający swój prefiks ustawień. Trzy ścieżki budują rejestr
niezależnie: przebieg (długo żyjący, z `app.state`), `announced_snapshot(settings)` przy zapisie
rewizji i `announced_tools_by_server(settings)` przy `GET /tools` — obie ostatnie jednorazowe, bo
sesja streamable-http otwarta w zadaniu żądania psuje stos zakresów anyio. Nazwa nieogłoszona przez
żadną z tych trzech ścieżek jest nazwą, której nie da się ani zapisać w rewizji, ani wybrać
w terminalu.

**`ToolPlan.call` nie wie, który agent woła.** `server_by_name` to słownik **wszystkich** ogłoszonych
nazw, a `loop.py` woła `call_tool(request.name, ...)` bez klucza agenta. Dobór narzędzi
(`for_agent`) jest dziś jedyną granicą i działa wyłącznie przez to, czego modelowi nie podano.

**Wykonanie przebiegu nie zna zespołu ani właściciela.** `start_run_on_revision` ma oba,
`execute_run` dostaje `run_id` i definicję.

## Goals / Non-Goals

**Goals:**
- Pamięć jako zwykłe narzędzia w istniejącym mechanizmie doboru — bez drugiego systemu uprawnień.
- Ogłoszenie nazw pamięci na wszystkich trzech ścieżkach rejestru, w tym dwóch bezstanowych.
- Przypisanie egzekwowane przy wywołaniu, dla wszystkich źródeł naraz.

**Non-Goals:**
- Nie zmieniamy `Briefing` ani `tc-openai`. Pamięć nie jest historią i nie wchodzi do briefingu.
- Nie ruszamy `teams_tools/` — pamięć nie wchodzi w tej zmianie do rozmowy operatora z modelem.
- Żadnego wygasania wpisów, żadnego wyszukiwania po treści, żadnego zawężania odczytu do wybranych
  autorów. Sufit i ręka operatora są całą polityką v1.

## Decisions

### Uprawnienia to przypisane narzędzia, nie nowe pole definicji

`AgentDefinition.tools` już nazywa narzędzia per agent, walidacja przy zapisie już sprawdza, że
nazwa jest ogłaszana, a `ToolPlan.for_agent` już podaje modelowi dokładnie to, co nazwała definicja.
Uprawnienia do pamięci = przypisanie `memory_read` i/lub `memory_write`.

Rozważone i odrzucone:
- **Typowane pole `memory: none | read | write` na `AgentDefinition`.** Czytelniejsze w edytorze
  zespołu, ale zakłada drugi mechanizm uprawnień obok istniejącego, wymaga zmiany kontraktu
  definicji, regeneracji kontraktu terminala i osobnej ścieżki egzekwowania — trzy koszty za zdanie,
  które `tools` już wypowiada. Dochodzi koszt ukryty: dwa mechanizmy uprawnień rozjeżdżają się przy
  pierwszej poprawce jednego z nich.
- **Wstrzykiwanie pamięci do briefingu każdego agenta.** Odczyt przestaje być decyzją i przestaje
  być widoczny w śladzie, a każdy agent płaci za całą pamięć w każdej turze — niezależnie od tego,
  czy jej potrzebował.

### Rejestr buduje źródło pamięci sam, a ogłoszenie nie dotyka bazy

`ToolServerRegistry.from_settings(settings, *, pool=None)` konstruuje `MemoryToolSource` obok dwóch
serwerów. Deskryptory obu narzędzi są **stałą modułu**, więc `list_tools()` nie potrzebuje puli —
i dzięki temu `announced_snapshot` oraz `announced_tools_by_server`, które budują rejestr z samych
ustawień, ogłaszają nazwy pamięci bez żadnej zmiany w swoich sygnaturach i bez połączenia do bazy.
Pula jest potrzebna dopiero przy `call()`, gdzie zawsze jest — bo tam stoi przebieg.

Rozważone i odrzucone: **`local_sources` wstrzykiwane z `workbench/`**, wzorem `LocalTeamsTools`
w rozmowie. Tam było konieczne, bo źródłem jest aplikacja ASGI, której `teams` nie może znać. Tutaj
źródłem jest własny store modułu, a `teams` wolno go czytać — wstrzykiwanie oznaczałoby przewleczenie
tego samego argumentu przez trzy niezależne miejsca budujące rejestr, z których dwa są w routerach,
i cichą utratę nazw pamięci w tym z nich, o którym ktoś zapomni.

### Odmowa nieprzypisanej nazwy jest wynikiem wywołania, nie wyjątkiem

`ToolPlan.call(name, arguments, *, agent_key)` sprawdza przynależność nazwy do
`per_agent[agent_key]` i przy braku oddaje `ToolOutcome(REFUSED, …)`. `_StepRunner` podaje związany
`call_tool`, więc sygnatura w `loop.py` się nie zmienia.

`REFUSED` zamiast wyjątku, bo tak samo zachowuje się odmowa `TradeGuard`: model dostaje zdanie,
z którym może zrobić coś sensownego, wpis ląduje w `tool_calls`, a przebieg pracuje dalej. Model,
który zgadł nazwę, popełnił błąd wart poprawienia, a nie przewrócenia eksperymentu.

### Pamięć jest kluczowana zespołem, a wpisy są niezmienne

Tabela `team_memories` obok rewizji, wzorem `team_layouts`: `team_id` z kluczem obcym, właściciel
osiągany złączeniem z `teams`, więc filtr właściciela zostaje w zdaniu SQL. Kolumny
`author_agent_key` i `run_id` są czytelnością, nie uprawnieniem; `run_id` dopuszcza `NULL`, co
zostawia miejsce na wpis ręczny operatora, którego v1 nie dodaje.

Rozważone i odrzucone: **pamięć na rewizji** (każda notatka wymuszałaby nową definicję, więc dwa
przebiegi „tej samej" rewizji przestałyby być porównywalne) i **pamięć na operatorze, wspólna dla
zespołów** (wiedza jednego eksperymentu wyciekałaby do drugiego, a wtedy porównanie dwóch zespołów
porównuje dwa nieznane stany).

### Trzy sufity jako stałe modułu

`MEMORY_ENTRY_MAX_CHARS`, `MEMORY_READ_LIMIT`, `MEMORY_WRITES_PER_RUN` — obok `ROUND_CEILING`,
świadomie nie ustawienia. Reguła podziału stoi w `docs/architecture.md`: liczba, którą operator ma
prawo ustawić, jest jego budżetem i mieszka w rewizji; te trzy nie chronią jego pieniędzy, tylko
kształt, w jakim moduł podaje cokolwiek modelowi. Sufit znaków jest powtórzony CHECK-iem w bazie,
bo jest jedyną z tych trzech granic, której złamanie zostaje na dysku.

### Ustawienie mówiące, że pamięci nie ma — nie istnieje

Źródło pamięci jest zawsze skonfigurowane, dopóki moduł odpowiada. Zespół nieprzypisujący narzędzi
pamięci jej nie widzi i to jest cała jej „wyłączalność"; osobne ustawienie tworzyłoby drugi stan,
w którym zapisana rewizja przestaje dać się uruchomić po restarcie procesu.

Konsekwencja wymaga poprawki w `plan_tools`: dzisiejsza odmowa „no tool server is configured" pada
z `not registry.configured()`, a rejestr od tej zmiany nigdy nie jest pusty. Warunek musi pytać
o serwery **sieciowe**, żeby przebieg zespołu z narzędziami archiwum przy nieskonfigurowanym
`MARKET_MCP_URL` nadal odmawiał komunikatem nazywającym ten serwer, a nie zdaniem o nazwie, której
nikt nie ogłasza.

## Risks / Trade-offs

- **Zespół uczy się nieprawdy i powtarza ją w każdym przebiegu, płacąc za to za każdym razem.** →
  Operator widzi pamięć w terminalu i usuwa wpis; wpisy są niezmienne, więc widać też, kiedy zespół
  sam się sprostował. Żadne narzędzie agenta nie kasuje — inaczej model mógłby wymazać własny błąd.
- **Pamięć rośnie i zaczyna dominować kontekst agenta.** → Sufit odczytu z jawnym „jest tego
  więcej"; sufit zapisów na przebieg zatrzymuje zespół, który postanowił notować wszystko.
- **Egzekwowanie przypisania przy wywołaniu zmienia zachowanie istniejących zespołów.** → Zmienia je
  tylko dla wywołania nazwy, której agent nie dostał, a to dziś oznacza model wołający coś, czego mu
  nie podano. Ryzyko jest realne i akceptowane: lepiej odmówić, niż wykonać.
- **Pamięć zapisana przy uruchomieniu z harmonogramu wymaga właściciela harmonogramu.** → Ten sam
  warunek co przy koszcie dobowym; test przebiegu z zegara sprawdza, że wpis należy do właściciela
  harmonogramu, a nie do procesu.

## Migration Plan

Migracja `0008` dokłada tabelę i niczego nie zmienia w istniejących — wdrożenie stosuje ją samo, pod
blokadą doradczą modułu, przed podaniem obrazu (`CLAUDE.md`, „Migrations are never the operator's
job"). Żadna zapisana rewizja nie wymaga przepisania, bo definicja nie zyskuje pola.

Cofnięcie: `downgrade` usuwa tabelę. Zespół, którego rewizja przypisuje narzędzia pamięci, przestaje
się wtedy uruchamiać z odmową nazywającą nazwę — świadomie, bo cofnięcie zabiera narzędzie, na które
rewizja się powołuje. To ta sama odmowa co przy narzędziu zniknięciem po stronie serwera.
