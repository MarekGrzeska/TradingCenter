# Review — market-mcp jako trasa w market-data

Napisany, bo ta zmiana jest ryzykowna w jednym konkretnym miejscu (autoryzacja per trasa
zastępuje prohibicję, która dotąd trzymała się konstrukcyjnie) i bo trzy rzeczy w trakcie
wyszły inaczej, niż mówił kosztorys.

## Co zostało sprawdzone

| Co | Jak | Wynik |
|---|---|---|
| Powierzchnia narzędzi bez zmian | `list_tools()` w sesji MCP przez `create_connected_server_and_client_session` | te same 11 nazw co w osobnym procesie (`test_mcp_mount.py`) |
| Sufit powierzchni | pomiar serializacji `list_tools()` | 18 844 znaki wobec zapisanych 19 700 — wartość sufitu przeniesiona bez zmiany |
| Zestaw testów market-data | `uv run pytest` | 1 110 przechodzi, 7 pomijanych (`live`); przed zmianą 963 |
| Konsumenci nietknięci | `uv run pytest` w `agent` i `teams` | 365 i 395 przechodzi — żadna linia kodu tych modułów się nie zmieniła, tylko `.env.example` |
| Runner dev | `uv run pytest` w `scripts` | 162 przechodzą; tabela usług, porty i doradady zaktualizowane wraz z testami |
| Infrastruktura | `terraform fmt -check -recursive` i `validate` na obu rootach | czysto |
| Delty specyfikacji | `openspec validate --strict` | valid |

Czego **nie** sprawdzono i co zostaje operatorowi: zadanie 5.3 — uruchomienie całego stosu
lokalnie i potwierdzenie, że agent widzi narzędzia bez `market-mcp`. Stos jest operatora,
nie tej sesji.

## Trzy rzeczy, których plan nie przewidział

**Router wskaźników musiał pójść do warstwy serwisowej.** `compute` trzymało 170 linii
decyzji — sufit, rozszerzenie okna o rozgrzewkę, odczyty wyższych ram czasowych — których
narzędzie nie mogło ominąć i nie mogło powtórzyć. Plan zakładał, że wystarczy `store` i
katalog; to jest dokładnie ten rodzaj kosztu, który D1 nazwał („tam, gdzie router robi coś
ponad odczyt, narzędzie musi wziąć to samo"), tylko większy.

**`cap_by_freshness` zostało skasowane, a nie przeniesione.** Indeksowało swoje elementy
jak słowniki. To była prawda, dopóki przyjeżdżały jako JSON z drutu, i przestała nią być,
gdy zaczęły przyjeżdżać jako modele. Funkcja nie miała testu, więc nic tego nie powiedziało
— znalazło się przy czytaniu, nie przy uruchamianiu.

**Realna regresja, złapana przy przenoszeniu testu.** Odwrócony zakres był dotąd odrzucany
przez 422 archiwum i przepisywany dla modelu. W jednym procesie nie ma czego odrzucić:
kwerenda po prostu nic nie dopasowuje, więc odpowiedź brzmiałaby „brak świec" — czyli ta
jedna pewna zła odpowiedź, przed którą ten moduł broni się całą swoją strukturą. To samo z
nieznaną rozdzielczością, którą FastAPI odrzucało przed wejściem w handler. Oba odrzucenia
mają teraz miejsce w narzędziu i własne testy (`test_tools_refusals.py`), a plik ma na
górze napisane, dlaczego zmienił się bardziej niż jakikolwiek inny.

## Ryzyka, jakie zostają

**Zapis autoryzacji jest jedyną rzeczą między agentem a `DELETE /pairs/{symbol}`.**
Trzymają go: odmowa domyślna dla trasy nieznanej zapisowi, test odmowy dla każdej pary
„tożsamość — powierzchnia, do której nie ma prawa", i test trzymający zapis wobec
opublikowanego dokumentu, żeby nowa trasa REST nie stała się ani otwarta, ani nieosiągalna
po cichu.

**Zmierzone 19.08.2026, po wdrożeniu — i pomiar obalił założenie.**
`X-MS-CLIENT-PRINCIPAL-ID` przy tokenie delegowanym niesie object id **zalogowanej osoby**,
nie aplikacji: produkcja odmówiła terminalowi każdego żądania REST
(`request refused: e6b7d7ba-… has no access to /stream-tickets`), obraz został cofnięty w
około minutę, a moduł czyta teraz claim `azp`/`appid` z blobu `X-MS-CLIENT-PRINCIPAL` —
jedyne miejsce, w którym wołająca aplikacja występuje przy obu rodzajach tokenu. Wpisanie
dwóch pisowni identyfikatora nie mogło tego uratować i nie uratowało; to była hipoteza
zamiast pomiaru i tak też się skończyła.

Druga rzecz, której ta awaria nauczyła: **ustawienia muszą dojechać przed obrazem, który je
egzekwuje.** Zapis pusty przy włączonym wymogu tożsamości to odmowa wszystkiego, więc
`apply` po deployu jest przerwą w działaniu, a nie tylko inną kolejnością. Kolejność z D6
(kod przed prawami wejścia) zostaje w mocy dla `allowed_applications`; same listy wołających
są nieszkodliwe dla starego obrazu i mają iść pierwsze.

**Brak ustawień jest odmową, nie przepuszczeniem.** Trzy fikstury testowe serwowały gołą
aplikację bez `app.state.settings`; dostały je, bo proces, który serwuje, ustawienia ma.
Alternatywa — „nie było ustawień, więc wszystko wolno" — jest dokładnie tym czytaniem,
którego ten plik nie może dopuścić.

**Kolejność wdrożenia jest własnością bezpieczeństwa (D6).** Kod wchodzi merge'em, prawa
wejścia — `terraform apply`, który jest operatora. Między jednym a drugim nie istnieje
chwila, w której `agent` i `teams` mają wstęp do archiwum, a zapis tras jeszcze ich nie
ogranicza. Ta zmiana niesie też krok 3 (usunięcie modułu), więc po `apply` wycofaniem jest
rewert, nie przywrócenie dwóch ustawień.

## Cztery awarie po merge'u, i co je łączy

Wszystkie po zielonym CI, wszystkie tego samego dnia. Warte zapisania nie z powodu liczby,
tylko dlatego, że trzy z czterech dzieli jedna przyczyna: **testy dotykały rzeczy obok tej,
która jedzie na produkcję**.

**1. Obraz nie miał pakietu, który moduł wziął.** `pyproject.toml` i lock mówiły
`tc-mcp-kit`, `Dockerfile` kopiował tylko `tc-runtime`. Build padł na `main`
(`Distribution not found at: file:///app/packages/tc-mcp-kit`) — głośno, jak obiecuje
komentarz w tym Dockerfile, i później, niż trzeba, bo **żaden job w `checks.yml` nie buduje
obrazu**. Nic się nie wdrożyło, produkcja stała na starym obrazie. Zamknięte dwoma testami w
`scripts/`, które trzymają jedną listę w trzech miejscach: pyproject, Dockerfile, filtr
ścieżek deploya.

**2. Tożsamością nie jest ten nagłówek.** Opisane wyżej: `X-MS-CLIENT-PRINCIPAL-ID` przy
tokenie delegowanym niesie osobę. Testy ustawiały ten nagłówek same, więc dowodziły
nagłówka, na którym ten moduł nie ma prawa decydować.

**3. Montaż `/mcp` był zepsuty na trzy sposoby naraz.** Agent docierał i był wpuszczany
(`request on /mcp from application 126d11d3…`), a dostawał nic:

- `streamable_http_app()` serwuje pod `settings.streamable_http_path`, czyli `/mcp` —
  zamontowany pod `/mcp` dał endpoint `/mcp/mcp`, więc publikowany adres odpowiadał 307 → 404;
- lifespan zamontowanej aplikacji nigdy nie startuje, więc grupa zadań menedżera sesji nie
  istniała: `RuntimeError: Task group is not initialized`;
- FastMCP włącza ochronę anty-DNS-rebinding, gdy jego `host` jest pętlą zwrotną — a jest nią
  domyślnie — i odpowiada `421 Invalid Host header` każdemu realnemu hostowi.

Żadnego z tych trzech nie mógł zobaczyć pakiet testów, który woła narzędzia jako obiekty:
`FastMCP.call_tool` albo sesja w pamięci. Jedno żądanie frontowymi drzwiami łapie wszystkie
trzy, i tym jest teraz test w `test_mcp_mount.py` — handshake plus `tools/list` po
transporcie, adresowany prawdziwą nazwą hosta zamiast `testserver`. Każdą usterkę
przywrócono po kolei, żeby zobaczyć, jak pada.

**4. Plik planu Terraforma trafił do repozytorium.** `git add -A` wciągnął
`infra/tfplan.out`; `.gitignore` znał `*.tfplan` i `tfplan`, a `-out=` bierze nazwę, którą
ktoś wpisze. W pliku były realne wartości — klucz instrumentacji App Insights i siedem haseł
aplikacji Easy Auth. Plik usunięty, wzorzec poszerzony na katalog zamiast rozszerzenia, ale
blob zostaje w historii: **rotacja tych sekretów jest zadaniem operatora i nie zamyka jej
żaden commit** (PR #172 niesie polecenia).

Wniosek dla następnej zmiany tego kształtu — A(teams) jest dokładnie taka: **jeden test
przez prawdziwą drogę wejścia jest wart dziesięciu przez seam**. Wszystkie trzy usterki
montażu i obie awarie wdrożeniowe leżały poza zasięgiem testów, które przeszły.

## Świadomie poza zakresem

Komentarze w `agent` i `teams` nadal mówią „market-mcp" o serwerze narzędzi. Ustawienie
zachowuje nazwę (`MARKET_MCP_URL`) — zmienił się adres, nie relacja — a przepisywanie
czterdziestu komentarzy w modułach, których zachowanie się nie zmienia, jest churnem, przed
którym `CLAUDE.md` ostrzega wprost.
