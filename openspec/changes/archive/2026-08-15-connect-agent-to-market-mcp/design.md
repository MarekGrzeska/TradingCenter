## Context

Zobacz `proposal.md` — Why. Tu tylko to, co kształtuje rozwiązanie.

Po stronie agenta stoi graf LangGraph z **jednym** węzłem (`graph.py`: „Room is left
here, not filled: a tool node is what a later change adds"). Historia jest odbudowywana
z bazy przy każdej turze — graf nie trzyma transkryptu i nie ma checkpointera.
`provider.py` jest jedynym miejscem, w którym istnieją klasy wiadomości langchaina;
wszędzie indziej tura to pary `(rola, treść)` we własnym słowniku modułu
(`"operator"`/`"agent"`). `turn.py` pisze dokładnie jedną wiadomość agenta i jeden
wiersz zużycia na turę, zawsze — także gdy dostawca padł w połowie.

Po stronie `market-mcp` stoi gotowy serwer: dziesięć czytających narzędzi, dwa
transporty z jednej rejestracji, sufit i streszczenie w każdej odpowiedzi, jeden kształt
odmowy niosącej zdanie „co zrobić inaczej". Easy Auth przed nim wymaga tożsamości
wołającego, a jego `allowed_applications` trzyma dziś zaślepkę: własny client id, przez
który nic realnego nie przejdzie.

Ograniczenie, które trzeba mieć z tyłu głowy przez cały ten dokument: plan App Service
jest B1 z jednym workerem i pięcioma aplikacjami, a tura z narzędziem to teraz łańcuch
`agent → market-mcp → market-data`, w którym każde ogniwo czeka na następne.

## Goals / Non-Goals

**Goals:**

- Model może sięgnąć po dane archiwum w trakcie odpowiadania i mówić dalej z tym, co
  dostał.
- Koszt tury z narzędziami jest widoczny w zakładce kosztów tak samo dokładnie jak
  koszt tury bez nich.
- Po każdym wywołaniu zostaje zapis wystarczający, żeby następna zmiana mogła go
  pokazać, bez zgadywania, czego wtedy zabrakło.
- Niedostępny `market-mcp` degraduje agenta do tego, czym jest dziś, a nie do milczenia.

**Non-Goals (na poziomie projektu, ponad to, co wyklucza proposal):**

- Checkpointer LangGraph i stan grafu przeżywający turę. Prawdą pozostają własne tabele.
- Równoległe wywołania narzędzi w jednym obrocie pętli. Sekwencyjnie — łańcuch i tak
  kończy się na jednym workerze B1, a równoległość kupiłaby tu czas, płacąc
  nieodtwarzalną kolejnością w zapisie.
- Własny sufit na rozmiar wyniku narzędzia po stronie agenta. Sufit jest po stronie
  `market-mcp` i jest jego wymaganiem — druga kopia w drugim module to druga liczba do
  rozjechania.

## Decisions

### Transport: streamable http, nie stdio

Agent stoi w innym kontenerze i to jest dokładnie przypadek, dla którego `market-mcp` ma
transport sieciowy. Alternatywa — uruchamianie `market-mcp` jako podprocesu w obrazie
agenta przez stdio — wymagałaby wstawienia drugiego modułu do cudzego obrazu razem z
jego konfiguracją dostępu do archiwum, czyli dwóch instancji tego samego modułu o dwóch
różnych tożsamościach. Odrzucone. stdio zostaje tym, czym jest: drogą klienta na biurku
operatora.

### Zestaw narzędzi odkrywany przy starcie sesji, bez snapshotu

To jedyny kontrakt między modułami w tym repozytorium, który opisuje sam siebie: klient
MCP pyta `tools/list` i dostaje nazwy, opisy i schematy parametrów. Nie ma czego
commitować i nie ma czego sprawdzać `contract:check`-iem — kontrakt jedzie w tej samej
sesji, w której jest używany, więc nie ma jak się rozjechać.

Konsekwencja, którą trzeba przyjąć świadomie: nowe narzędzie po stronie `market-mcp`
staje się dostępne agentowi **bez żadnej zmiany tutaj i bez żadnego przeglądu tutaj**.
Bezpieczne dlatego, że `market-mcp` ma w swojej specyfikacji zakaz publikowania
narzędzia zapisującego — nie jako konwencję, tylko jako wymaganie z testem powierzchni.
Gdyby ten zakaz kiedyś padł, ta decyzja wymaga ponownego przemyślenia, i to zdanie jest
jedynym miejscem, w którym to zostanie zapisane.

Odkrywanie jest per sesja z serwerem, nie per tura: lista jest pobierana raz i trzymana
w procesie, tak samo jak `market-mcp` trzyma katalog wskaźników („kolejna zmiana
przychodzi z restartem modułu, nie z odpytywania w kółko").

### Pętla jako drugi węzeł grafu, nie jako pętla w `provider.py`

Kanoniczny kształt LangGraph: węzeł `model`, węzeł `tools`, krawędź warunkowa z
`model` — do `tools`, jeśli model poprosił o narzędzia, do `END`, jeśli odpowiedział — i
krawędź z `tools` z powrotem do `model`. To jest miejsce zostawione w `graph.py` i to
jest kształt, dla którego `langgraph` w ogóle jest w zależnościach.

Alternatywa (pętla `while` w `provider.py`, graf dalej jednowęzłowy) byłaby mniejszą
zmianą i schowałaby sterowanie w module, którego zadaniem jest rozmowa z dostawcą.
Odrzucone: sufit wywołań, licznik obrotów i zapis wywołań to sterowanie turą, nie
szczegół protokołu OpenAI.

Granica słownika zostaje tam, gdzie była. `provider.py` dalej jest jedynym miejscem, w
którym istnieją klasy langchaina; dochodzą do niego dwa własne kształty — żądanie
wywołania i jego wynik — obok istniejących `TextDelta` i `UsageReport`.

### Wynik narzędzia żyje jedną turę

Wywołania i ich wyniki są w stanie grafu przez czas trwania tury i **nie wracają do
promptu w turze następnej**. Historia następnej tury to dalej pary `(rola, treść)` z
bazy: pytania operatora i wypowiedzi agenta.

Cena: model, który potrzebuje tej samej ceny dwie tury później, zawoła narzędzie drugi
raz. Zapłacone świadomie. Alternatywa — doklejanie wyników narzędzi do historii — rośnie
bez ograniczenia w rozmowie, w której padło dwadzieścia pytań o rynek, a rośnie w
najdroższym miejscu, bo cała historia jedzie do dostawcy przy każdym wywołaniu. Do tego
świece sprzed dwóch tur są po prostu starsze niż te, które model dostanie, wołając
jeszcze raz, a to jest moduł, w którym wiek liczby jest częścią odpowiedzi.

### Ślad wywołania w osobnej tabeli, nie w transkrypcie

`messages` jest tym, co czyta terminal. Ta zmiana terminala nie rusza, więc wywołania
nie mogą być wiadomościami — inaczej panel dostałby wiersze o rolach, których nie zna,
albo trzeba by je filtrować po stronie odczytu, co jest kontraktem udawanym przez
zapytanie.

Osobna tabela: sesja, wiadomość agenta, do której należy wywołanie, numer obrotu w
turze, nazwa narzędzia, argumenty, czy się powiodło, treść wyniku albo odmowy, czas
trwania. Pisana po `append_agent_message`, w tym samym miejscu co wiersze zużycia i z
tego samego powodu — identyfikator wiadomości powstaje dopiero na końcu tury.

To jest zapis, który następna zmiana (podgląd wywołań w terminalu) odczyta i opublikuje.
Pisanie go teraz kosztuje jedną migrację i oszczędza rozmowę „czego wtedy nie
zapisaliśmy".

### Zużycie: wiersz na wywołanie modelu, wszystkie pod jedną wiadomością

`usage.message_id` nie ma unikalności — sprawdzone — więc trzy wywołania modelu w jednej
turze to trzy wiersze wskazujące tę samą wypowiedź agenta. Zgodne z wymaganiem, jakie
`agent-usage` już ma („Każde wywołanie modelu MUST zapisać osobny wiersz"), tyle że
napisanym, gdy wywołanie na turę było jedno; delta nazywa ten przypadek wprost, bo
scenariusz czyta się dziś jak „jeden wiersz na wiadomość".

Suma kosztu tury to suma jej wierszy i nic w zakładce kosztów nie wymaga zmiany:
agregaty i tak sumują wiersze, nie wiadomości.

### Odmowa narzędzia wraca do modelu, awaria dostawcy kończy turę

Dwie różne rzeczy, które łatwo wrzucić do jednego `except`.

Odmowa narzędzia — nieznany symbol, zakres ponad sufit, nieznany wskaźnik — jest
**wynikiem** wywołania. `market-mcp` pisze w niej, co zmienić, właśnie po to, żeby model
mógł poprawić żądanie; przerwanie tury odbiera tę możliwość i zamienia poprawialny błąd
w awarię widzianą przez operatora.

Awaria dostępu do `market-mcp` — nie odpowiada, odmawia tożsamości, nie da się z nim
nawiązać sesji — nie jest wynikiem narzędzia i nie jest awarią tury. Model dostaje
narzędzia oznaczone jako niedostępne i odpowiada tym, co ma, a że prompt każe mu nie
udawać danych, których nie widział, jest to odpowiedź „nie mam teraz dostępu do
archiwum", nie zmyślona cena.

Awaria dostawcy modelu zostaje tym, czym jest dziś: `graph.py` łapie ją w węźle, częściowy
tekst zostaje zapisany, tura kończy się oznaczona jako niepełna.

### Sufit: liczba w kodzie, osiem obrotów

Ten sam wybór, jaki zrobił `market-mcp` dla swoich sufitów — liczba w kodzie, nie
ustawienie. Ustawienie sufitu bezpieczeństwa jest zaproszeniem do podniesienia go w
chwili, w której właśnie przeszkadza.

Osiem, bo realna tura analityczna to pokrycie, świece, wskaźniki i poziomy — cztery do
pięciu wywołań — a osiem zostawia zapas i dalej ogranicza koszt cyklu do znanej
wielokrotności. Po osiągnięciu sufitu model dostaje to jako wynik i ma jeszcze jeden
obrót na odpowiedź operatorowi; tura nie urywa się w pół zdania.

### Tryb dostępu wybrany jednoznacznie, trzeci raz ten sam wzór

`market_mcp_url` plus `market_mcp_scope`, z tą samą regułą co w `market-mcp/config.py`
wobec archiwum i w `market-data/config.py` wobec bazy: adres spoza pętli zwrotnej bez
scope'u to odmowa startu, scope przy pętli zwrotnej to też odmowa. Wzór jest tu czwartą
kopią i to jest w porządku — trzy moduły, cztery seamy, żadnego wspólnego kodu, zgodnie
z „Why no shared library".

## Risks / Trade-offs

- **Koszt tury rośnie wielokrotnie, nie o procenty.** Tura z jednym narzędziem to dwa
  wywołania modelu, a wynik pierwszego jedzie w prompcie drugiego. → Sufit ogranicza
  najgorszy przypadek, zużycie liczone per wywołanie pokazuje realny, a sufity i
  streszczenia `market-mcp` istnieją właśnie po to, żeby wynik narzędzia nie był
  tysiącami tokenów świec.
- **Operator patrzy w ciszę, kiedy narzędzie pracuje.** Strumień niesie dziś tylko
  fragmenty tekstu; między wywołaniami modelu nie leci nic, a wywołanie narzędzia to
  do dziesięciu sekund po stronie `market-mcp` plus jego własne oczekiwanie na archiwum.
  → Ograniczone przez sufit i przez limit czasu, ale realnie znika dopiero razem z
  podglądem wywołań w terminalu — czyli w następnej zmianie, i to jest jeden z jej
  powodów.
- **Łańcuch czterech modułów na jednym workerze B1.** `agent → market-mcp → market-data
  → (gateway)`, każdy czekający na następny, wszystkie na jednym planie. → Do zmierzenia
  po wdrożeniu, nie do przewidzenia teraz; ta zmiana nie dokłada aplikacji, tylko ruch.
- **Nowe narzędzie po tamtej stronie wchodzi tu bez przeglądu.** Wprost przyjęte wyżej;
  broni tego zakaz narzędzi zapisujących w specyfikacji `market-mcp` i jego test
  powierzchni. Ryzyko jest realne dokładnie w dniu, w którym ten zakaz by padł.
- **Prompt `v3` unieważnia porównania z transkryptami `v2`.** → Po to jest wersja przy
  wiadomości; stare rozmowy dalej mówią, na co odpowiadały.
- **Model może wywnioskować z narzędzi więcej, niż one mówią.** Pusta seria to nie cisza
  rynku, a `market-mcp` pisze to zdaniem w treści odpowiedzi. → Prompt `v3` powtarza tę
  granicę po swojej stronie; jedno i drugie, bo żadne samo nie wystarcza.

## Migration Plan

Migracja bazy dokłada jedną tabelę i niczego nie przepisuje — wdrożenie jest zwykłym
`alembic upgrade head`, jak przy każdej zmianie schematu tego modułu.

Kolejność, bo połowa tej zmiany jest w Entra i jej nie robi CI:

1. Kod agenta wchodzi na `main` z `market_mcp_url` nieustawionym w produkcji. Agent
   startuje, nie ma narzędzi, zachowuje się jak dziś — to jest ta sama ścieżka co
   „`market-mcp` niedostępny", więc nie jest to stan nieprzetestowany.
2. Operator robi `terraform apply` lokalnie: tożsamość agenta wchodzi w
   `allowed_applications` `market-mcp`, aplikacja agenta dostaje `MARKET_MCP_URL` i
   `MARKET_MCP_SCOPE`.
3. Restart agenta podnosi sesję z `market-mcp` i narzędzia pojawiają się same.

Wycofanie: skasowanie `MARKET_MCP_URL` z ustawień aplikacji i restart. Agent wraca do
zachowania z punktu 1 bez wycofywania kodu i bez ruszania bazy — wiersze wywołań, które
zdążyły powstać, zostają, bo są zapisem tego, co się wydarzyło.
