## Context

Motywacja jest w `proposal.md` — „Why". Tu tylko to, co ogranicza rozwiązanie.

Repozytorium ma już połowę tej maszyny. `agent/graph.py` to `StateGraph` LangGrapha z dwoma
węzłami (model ↔ narzędzia), ograniczeniem rund i trzema rozróżnionymi klasami porażek;
`agent/provider.py` streamuje z `/v1/responses` za protokołem `ModelProvider`;
`agent/tools/client.py` trzyma jedną sesję MCP z tożsamością zarządzaną. To jest pętla
**jednego** agenta i ona działa. Czego nie ma: żadnego pojęcia zespołu, żadnej definicji
trzymanej jako dane, żadnego przebiegu, który nie byłby rozmową.

Ograniczenia, których ta zmiana nie negocjuje: brak importów międzymodułowych i brak
biblioteki współdzielonej; migracje nie są robotą operatora; `market-mcp` nie zapisuje;
`terraform apply` jest robotą operatora. Dwa fakty z kodu, które wchodzą w decyzje niżej:
`scripts/contract.mjs` jest zaszyty na jedno źródło schematu, a terminal nie ma dziś ani
jednej linii kodu rysującego graf.

## Goals / Non-Goals

**Goals.** Definicja zespołu ma być danymi na tyle kompletnymi, żeby zbudować z nich
wykonanie bez pisania kodu per zespół. Dwa przebiegi tej samej rewizji mają być porównywalne.
Moduł ma dać się usunąć przez skasowanie katalogu i zasobów.

**Non-Goals na poziomie projektu** (poza tym, co `proposal.md` wyłącza z zakresu): nie budujemy
własnego silnika wykonania grafu ani własnego formatu promptów; nie budujemy edytora
przepływów ogólnego przeznaczenia — canvas obsługuje ten jeden kształt danych; nie
optymalizujemy czasu przebiegu, bo eksperyment mierzy jakość decyzji, nie opóźnienie.

## Decisions

### Osobny moduł, nie rozbudowa `agent`

Schemat `agent` jest zbudowany wokół jednej rozmowy: `sessions` z właścicielem, `messages`
w porządku jednej osi, jeden globalny `prompt_revisions`. Zespół ma inny cykl życia —
definicja żyje dłużej niż przebieg, przebieg nie ma właściciela-rozmówcy, a promptów jest
tyle, ile ról.

Rozważone: **rozbudowa `agent`** — odrzucona, bo zespół wszedłby w tabele zaprojektowane pod
rozmowę i każdy eksperyment ryzykowałby czatem operatora, który ma być stabilny.
**Biblioteka współdzielona** dla pętli agenta — odrzucona wprost przez architekturę repozytorium
(`docs/architecture.md`, „Why no shared library"); `db.py`, `migrate.py`, `schema_version.py`,
`auth.py`, `provider.py` i `tools/client.py` są kopiowane jako świadome bliźniaki, tak jak
zrobiły to `agent` i `market-data` między sobą.

### LangGraph, nie OpenAI Agents SDK

Rozważone: **OpenAI Agents SDK** (Agent/Runner/Handoffs) — lżejszy i dobrze pasuje do prostych
przekazań, ale topologia siedzi w kodzie, a my potrzebujemy jej w bazie. **LangGraph** wygrywa
dwoma rzeczami: jest już w repozytorium, więc nie dokładamy drugiego frameworka obok
istniejącego, i jego model — jawne węzły i krawędzie — odwzorowuje się jeden do jednego na
definicję w JSONB oraz na diagram w terminalu. Trzeci wariant, **własny orkiestrator**,
odrzucony: to przepisanie działającej pętli po to, żeby nie mieć zależności, którą już mamy.

### Definicja zespołu jest daną, a rewizje są niezmienne

Definicja to graf w JSONB: węzły z rolą, promptem, wytycznymi, `model_id` i podzbiorem
narzędzi, plus krawędzie. Zapis nie modyfikuje rewizji, tylko dokłada następną — wzorzec
`prompt_revisions` z `agent`, gdzie ta własność już się sprawdziła.

Rozważone: **mutowalna definicja** — odrzucona, bo eksperyment, którego definicja zmienia się
pod spodem, nie daje się porównać z własnym wynikiem sprzed tygodnia; przebieg wskazujący
rewizję jest jedynym sposobem, żeby ślad znaczył cokolwiek później. **Definicja jako kod**
(klasa albo plik per zespół) — odrzucona, bo wtedy „zdefiniuj zespół na froncie" znaczy
„wygeneruj i wdroż kod", a to jest inna funkcjonalność niż zamówiona.

Walidacja przy zapisie, nie przy uruchomieniu: acykliczność, osiągalność każdego węzła,
istnienie modeli i narzędzi. Powód jest ten sam, dla którego `agent` waliduje katalog modeli
w `Settings()` — rewizja, którą da się zapisać, a nie da uruchomić, to pułapka zastawiona na
operatora w najgorszym momencie.

### Węzeł grafu to cała pętla agenta, nie pojedyncze wywołanie modelu

Każdy węzeł zespołu opakowuje dzisiejszą pętlę model ↔ narzędzia wraz z jej ograniczeniem
rund. Graf zespołu jest więc grafem **agentów**, a nie grafem wywołań.

Rozważone: **jeden płaski graf**, w którym węzły narzędziowe każdego agenta są węzłami grafu
zespołu — odrzucone, bo miesza dwa poziomy, których operator nie miesza: na canvasie ma
widzieć role i zależności między nimi, a nie rundy narzędziowe. Zagnieżdżenie zachowuje też
bez zmian rzecz przetestowaną produkcyjnie — ograniczenie rund i trzy klasy porażek zostają
tam, gdzie już są.

### Następnik widzi wypowiedzi poprzedników, nie całą historię

Stan współdzielony niesie wyniki węzłów; węzeł dostaje w kontekście wypowiedzi tych, od
których prowadzi do niego krawędź.

Rozważone: **pełna historia dla każdego** — odrzucona z dwóch powodów naraz. Koszt rośnie
kwadratowo z liczbą agentów, a rozdzielenie ról przestaje cokolwiek znaczyć, jeśli każdy widzi
wszystko — wtedy zespół jest jednym agentem z kilkoma promptami. Krawędź ma być nośnikiem
informacji, i to jest dokładnie ta informacja, którą niesie.

### Kontrakt generowany; `scripts/contract.mjs` przestaje być jednoźródłowy

Terminal dostaje typy modułu z jego własnego dokumentu OpenAPI, tak jak dostaje je od
`market-data`. Wymaga to uogólnienia skryptu na N źródeł, każde ze swoim plikiem wyjściowym.
Moduł potrzebuje własnego `openapi.py` — bliźniaka tego z `market-data`, razem
z `require_response_fields`, bez którego generator wypuszcza pola odpowiedzi jako opcjonalne.

Rozważone: **ręcznie pisane DTO**, ścieżka `agent` — odrzucona, bo powierzchnia tego modułu
(grafy, rewizje, przebiegi, kroki) jest szersza i zmienia się częściej niż wąskie DTO czatu,
a ręczne typy psują się cicho. **Zatwierdzony snapshot OpenAPI**, ścieżka `market-mcp` —
odrzucona, bo to rozwiązanie dla konsumenta w innym języku; terminal umie czytać schemat
wprost. Ryzyko uogólnienia skryptu jest wymierne i pokryte: wyjście dla `market-data` MUST
zostać bajt w bajt takie samo, a `contract:check` w CI jest tym, co to sprawdza.

### React Flow na canvas zespołu

`@xyflow/react` (MIT). Węzły są zwykłymi komponentami Reacta, więc wchodzą w Tailwind i tokeny
terminala bez obcego systemu renderowania; ta sama biblioteka niesie canvasy Langflow, Flowise
i Dify, więc kształt zastosowania jest przetarty.

Rozważone: **JointJS+/GoJS** — dojrzałe, ale komercyjne i z własnym modelem renderowania obok
Reacta. **Rete.js / AntV X6** — zdolne, słabsza integracja z Reactem. **Własne SVG** —
odrzucone nie z powodu rysowania, tylko edycji: przeciąganie krawędzi, zaznaczanie i zoom to
kilkaset linii, których nikt tu nie chce utrzymywać. **Mermaid** — tylko odczyt, a canvas ma
być edytorem.

### Rozmieszczenie agentów obok rewizji, nie w niej

Operator przesuwa agentów, a moduł to pamięta — w **osobnej tabeli `team_layouts`**, kluczowanej
zespołem i kluczem agenta, nadpisywanej w miejscu. Nie w definicji.

Rozważone i odrzucone: **współrzędne w `TeamDefinition`**, czyli w JSONB rewizji. Kusi, bo nie
wymaga ani migracji, ani trasy — i psuje dokładnie tę rzecz, dla której rewizje są
niezmienne: przeciągnięcie węzła mintowałoby rewizję, a katalog, w którym „v7 vs v8" znaczy
czasem inny zespół, a czasem ten sam zespół przesunięty o piksel, przestaje odpowiadać na
pytanie, po co powstał (`teams-catalogue`, „Rewizja raz zapisana się nie zmienia";
`teams-runs`, „Przebieg odbywa się na rewizji"). Odrzucone też **trzymanie układu
w przeglądarce** (`localStorage`): zespół jest w bazie, więc jego obraz na drugiej maszynie
byłby innym zespołem, a operator dowiedziałby się o tym po fakcie.

Konsekwencja przyjęta świadomie: układ jest wspólny dla wszystkich rewizji zespołu, także tych
sprzed przesunięcia. Agent, którego układ nie zna — dołożony później albo obecny tylko
w starszej rewizji, na której biegnie oglądany przebieg — dostaje miejsce z `layout()`,
liczonego z zależności. Układ jest więc podpowiedzią zapisaną w bazie, nie kontraktem o tym,
gdzie coś stoi.

### Faza 1 nie składa zleceń

Zespół kończy pracę rekomendacją w śladzie. Narzędzia tradingowe wchodzą fazą 2.

Rozważone: **trading od razu** — odrzucony, bo pierwsza rzecz, którą trzeba sprawdzić, to czy
definiowalny na froncie zespół w ogóle produkuje sensowne i powtarzalne przebiegi; dokładanie
do tego pytania nieodwracalnych skutków po stronie rachunku odpowiada na dwa pytania naraz
i nie daje odpowiedzi na żadne. Stan bez narzędzi zapisujących nie jest przy tym prowizorką —
`agent` bez `MARKET_MCP_URL` jest wspieranym stanem i ma własne testy; tu obowiązuje ta sama
zasada.

## Risks / Trade-offs

- **Koszt tokenów rośnie z liczbą agentów, nie z liczbą przebiegów** → limity kosztu na
  przebieg i dzienne na zespół, egzekwowane w kodzie przed wywołaniem modelu, nie w prompcie;
  stawka kopiowana na wiersz zużycia, żeby rachunek dało się odtworzyć po zmianie cennika.
- **Przebieg może nie skończyć się sam** (długa debata, wolne narzędzie) → acykliczność
  wymuszona przy zapisie, ograniczenie rund w węźle, twardy limit czasu przebiegu.
- **Uogólnienie `contract.mjs` dotyka działającego kontraktu `market-data`** → wymóg
  bajt-w-bajt identycznego wyjścia i `contract:check`, który już stoi przed testami terminala.
- **`@xyflow/react` to pierwsza ciężka zależność widoku w terminalu** → ładowana w obrębie
  swojej zakładki; terminal bez tej zakładki zostaje tym, czym jest.
- **Fazy 2 i 3 mają iść równolegle po tej** → obie dopiszą modele do `contract.py` i po jednej
  rewizji Alembica; to są dwa znane punkty styku, a nie odkrycie przy merge'u.
- **Rewizje append-only rosną w nieskończoność** → przyjęte świadomie: katalog zespołów jest
  mały, to nie jest tabela świec, a możliwość porównania z rewizją sprzed miesiąca jest celem,
  nie efektem ubocznym.

## Migration Plan

Nie ma danych do migracji — baza jest nowa. Kolejność wdrożenia wynika z tego, że zapora bazy
czyta adresy wyjściowe aplikacji, która musi już istnieć:

1. Operator: `terraform apply -target` na App Service i rejestrację Entra, potem pełny `apply`
   z bazą, regułami zapory, sekretem i polityką dostępu do Key Vault.
2. Operator, raz na tę bazę: `scripts/grant-schema-ownership.sql`.
3. `deploy-teams.yml` buduje obraz i wdraża; moduł migruje się sam w `lifespan` pod advisory
   lockiem, a smoke check pyta `/health`, czyli sięga procesu, a nie płaszczyzny sterowania.

**Rollback.** Nic nie zależy od tego modułu, więc wycofanie nie dotyka pozostałych czterech.
Wycofanie obrazu cofa kod, ale nie schemat — to znana asymetria, którą `schema_version` ma
wykrywać. Wyłączenie samych narzędzi to wyczyszczenie `MARKET_MCP_URL` i restart; moduł zostaje
wtedy tym, czym był bez nich, a ślad przebiegów zostaje w bazie.

## Open Questions

- Czy zespoły będą potrzebowały pamięci **między** przebiegami (tablica ogłoszeń, wnioski
  z poprzednich prób), czy stan współdzielony w obrębie jednego przebiegu wystarcza. Odpowiedź
  wymaga zobaczenia kilku prawdziwych przebiegów i nie zmienia niczego w tej fazie: doszłaby
  jako osobna tabela i osobne wymaganie, bez ruszania definicji ani śladu.
