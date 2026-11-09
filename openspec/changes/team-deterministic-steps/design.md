## Context

Uzasadnienie zmiany jest w `proposal.md`, a pomiary w `docs/zespoly-kroki-deterministyczne.html`. Stan, od którego
zaczyna się projekt:

- **Graf.** `teams/runner/graph.py` kompiluje rewizję do `StateGraph` LangGraph. Węzeł to funkcja, która dostaje
  wypowiedzi poprzedników i zwraca tekst. `engine.py` uruchamia agenta przez `_StepRunner`, który trzyma haki
  wywołań:
  - wiersz `tool_calls`;
  - `TradeGuard` i wiersz `trades` przed wywołaniem zapisującym, rozliczony po odpowiedzi;
  - zużycie modelu i `CostGuard`.
- **Narzędzia.** `ToolPlan` rozwiązuje je raz na przebieg i wkleja konto rewizji. Tylko on wie, które wywołanie
  zmienia rachunek.
- **Sygnał.** `strategy_signal` (pakiet `strategies`, źródło w procesie) zwraca `action`, `order`, pozycję silnika,
  `sizing` dokumentu, `bar_closed_at` i `window_from`. Odmawia, gdy archiwum nie ma jeszcze ostatniej świecy.
- **Zapis.** `place_order` w `trading-mcp` zwraca `outcome`, `status`, `id` i `reference`. `size_for_margin` przelicza
  depozyt na wielkość.
- **Zestaw narzędzi.** `teams_tools` (`tc-team-tools`) zakłada i poprawia agentów. Sekcję `trading` przenosi bez
  zmian i nie umie jej ustawić.

## Goals / Non-Goals

**Goals:**
- Krok korzysta z tych samych haków co agent, żeby ślad, granice handlowe i konto nie miały drugiej implementacji.
- Logikę decyzji przepisu da się przetestować jako czystą funkcję tabelą przypadków, bez serwera narzędzi.

**Non-Goals:**
- Szybszy zegar zespołów.
- Wyzwalacz „świeca zamknięta”.
- Przepisy dla zleceń z limitem albo stopem.
- Generyczny formularz w terminalu dla dowolnego schematu JSON. Wystarczą typy, których używa pierwszy przepis.

## Decisions

**1. `steps` jako osobna lista w definicji, a nie `kind` w agencie ani wspólne `nodes`.**
Rewizje są niezmiennymi blobami JSONB. Osobna lista z domyślnym `[]` czyta stare rewizje bez migracji i zostawia w
spokoju walidatory `AgentDefinition` (model wymagany, narzędzia). Rozważone:
- `nodes` z polem `kind` wymagałoby przepisania kontraktu terminala i każdej rewizji;
- `kind` w agencie zrobiłoby `model_id` i `prompt` opcjonalnymi dla wszystkich.

Walidatory grafu w `TeamDefinition` (unikalne klucze, krawędzie, cykl, węzeł izolowany) liczą na sumie kluczy obu
list. Warunek „co najmniej jeden agent” staje się „co najmniej jeden węzeł”.

**2. Zamknięty katalog przepisów w kodzie `teams`.**
Przepis to klasa z modelem parametrów (Pydantic), listą potrzebnych narzędzi i opisem. Rozważone i odrzucone:
- ogólny potok wywołań z szablonami argumentów, czyli język programowania edytowany w formularzu, przy jednym
  przepisie w użyciu;
- kod pisany przez model przy każdym przebiegu, niedeterministyczny między przebiegami;
- `strategies` składające zlecenia, co łamie jego regułę „never an order” i granicę procesu.

Katalog jest ogłaszany przez `GET /teams/step-recipes`: nazwa, opis, parametry (nazwa, typ, wymagany, opis), narzędzia.
Czytają go terminal i `teams_tools`.

**3. Wspólna ścieżka wywołań dla agenta i kroku.**
Z `_StepRunner` wydzielamy obiekt per węzeł per przebieg (`NodeCalls`). Trzyma wiersz `run_steps`, wywołanie przez
`ToolPlan.call` z kluczem węzła, `tool_calls`, `TradeGuard` z wierszem `trades` przed wysłaniem oraz rozliczenie po
odpowiedzi. Agent dokłada do tego model i zużycie, krok tylko przepis. Kroku wołającego `ToolPlan` bezpośrednio nie
bierzemy: ominąłby wiersz zlecenia i granice, czyli dokładnie to, co `teams-trading` każe trzymać w module.
`plan_tools` dostaje narzędzia kroku z listy jego przepisu, pod kluczem kroku, więc ta sama zasada „wołasz tylko
przypisane” obowiązuje krok.

**4. Przepis to trzy fazy: odczyty, czysta decyzja, zapis.**
`strategy_execute` czyta `strategy_signal`, `list_accounts`, `get_positions`, `get_working_orders`, `get_balance` i
własne wiersze `trades` zespołu. Odczyty niezależne od siebie idą równolegle. Potem `decide(...)`, czysta funkcja bez
I/O, zwraca jedną akcję: wejście z depozytem, zamknięcie id, albo brak z powodem. Zapis to `size_for_margin` →
`place_order` albo `close_position`, a po nim `get_positions` jako potwierdzenie. Tabela przypadków `decide` to test
na najniższej warstwie (CLAUDE.md, reguła 1). Wyżej wystarczy jeden test, że wynik i zlecenie trafiają do śladu.

**5. Własna pozycja z wierszy `trades`, nie z pamięci zespołu.**
Własna pozycja to wiersz `place_order` tego zespołu (przez `runs` → `team_revisions.team_id` i właściciela), rozliczony
jako wykonany, którego `provider_order_id` albo `reference` odpowiada pozycji z `get_positions`. Notatki
ATTEMPT/OPEN w pamięci tekstowej zostają dla agentów. Przepis ich nie czyta, bo pamięć jest tekstem pisanym przez
model. Zgodność `id` z `place_order` z id pozycji u capital.com sprawdzamy na demo przed użyciem (zadanie 8.2). Gdy
się nie zgadza, dopasowanie idzie przez `reference` i potwierdzenie bramy.

**6. Jedna próba na świecę: kolumna `trades.attempt_key` z częściowym indeksem unikalnym.**
Klucz `"{team_id}:{step_key}:{strategy_id}:{revision}:{bar_closed_at}:{enter|exit}"` trafia do wiersza `trades`
zapisywanego przed wywołaniem. Naruszenie unikalności oznacza, że próba już była: krok kończy się pominięciem, a
wywołanie nie wychodzi. Rozważone: osobna tabela prób (drugi zapis i druga transakcja na tę samą informację) oraz
blokada doradcza na czas przebiegu, która nie chroni przed przebiegiem następnym. Wiersz pominiętej próby nie
powstaje, więc dobowy licznik zleceń liczy dalej tylko wysłane.

**7. Czekanie na świecę: ponawianie każdej odmowy sygnału co 1 s do terminu.**
Domyślny termin to 30 s. Przepis nie rozróżnia treści odmowy, bo tekst należy do `strategies` i wiązanie się z nim
byłoby sprzężeniem przez komunikat. Odmowa trwała, na przykład nieistniejąca rewizja, kończy się więc pominięciem po
30 s z ostatnią treścią odmowy jako powodem. Koszt dla bazy to najwyżej 30 wywołań po około 130 ms, dwa razy dziennie
na zespół, klasa C0/C1. Przed scaleniem trzeba to potwierdzić skillem `db-cost-check`.

**8. Wyjście idzie za silnikiem, nie za zegarem.**
Przepis nie ma parametru „zamknij o 14:00”. Zamyka własną pozycję, gdy silnik mówi `exit`, nie ma pozycji albo ma
przeciwną. Reguła wyjścia żyje więc w dokumencie strategii, tak jak w backteście, a harmonogram 14:00 ET tylko budzi
zespół. Pozycji starszej niż `window_from` przepis nie rusza i zwraca wynik nieznany (spec). Alternatywa z parametrem
czasu w kroku dawałaby drugie źródło prawdy o wyjściu, rozjeżdżające się przy pierwszej zmianie dokumentu.

**9. Powiadomienie zapasowe ma stały format, bez języka szablonów.**
`fallback_notice = {destination, bot, prefix}` na agencie. Tekst wiadomości składa się z:
- prefiksu;
- linii `summary` każdego kroku-poprzednika;
- linii „model nie odpowiedział: <powód>”.

Wysyłka idzie przez `send_telegram_message` tego agenta, więc zostaje w jego śladzie. Rozważone: szablon z polami
wyniku (kolejny język do walidacji) oraz osobny krok `notify` (wymagałby rozgałęzień warunkowych w grafie, których dziś
nie ma).

**10. Wyczerpana granica dobowa a kroki.**
`start_run_on_revision` dla rewizji z krokami nie rzuca `DailyCostLimitReached`. Przekazuje przebiegowi znacznik
„granica dobowa wyczerpana”. `CostGuard` agentów rusza od razu jako wyczerpany z powodem dobowym: pierwszy
`before_model_call` rzuca, węzeł agenta wysyła ewentualne powiadomienie zapasowe, a przebieg kończy się statusem
nazywającym granicę dobową. Kroki biegną zwyczajnie.

**11. Konto realne poza zestawem narzędzi rozstrzyga się w `teams_tools`, nie w REST `teams`.**
`create_team` i `revise_team` przyjmują `trading` z `environment` wyłącznie `demo` i odmawiają zmiany sekcji `trading`
rewizji, która jest `live`. REST `teams` zostaje bez zmian, bo terminal dalej ustawia konto realne. Z zewnątrz
Claude Code dosięga wyłącznie `/team-tools/mcp`, nie REST-u zespołów, więc to jedyne miejsce, gdzie ten zakaz trzeba
postawić.

**12. Terminal: formularz parametrów z katalogu, nie z kodu przepisu.**
Edytor kroku rysuje pola z listy parametrów ogłoszonej przez katalog: liczba całkowita, liczba dziesiętna jako tekst,
tekst, wybór strategii. Dzięki temu terminal nie ma kodu per przepis. Pole `sizing` dostaje etykietę „z dokumentu
strategii”, gdy jest puste. Wynik kroku w `run_steps.output` to JSON, a terminal pokazuje `decision` i `summary` nad
pełną treścią.

## Risks / Trade-offs

- [Id z `place_order` nie odpowiada id pozycji u capital.com] → każde wyjście kończy się wynikiem nieznanym i pozycja
  zostaje. Mitygacja: zadanie 8.2 sprawdza to na demo przed pierwszym zespołem. Wynik nieznany idzie do reportera,
  powiadomienia zapasowego i zdarzenia „przebieg zakończony”.
- [Archiwum z dziurą w świecach minutowych] → `strategy_signal` odmawia (`bars_without_minutes`), wyjście przepada.
  Mitygacja: dwa harmonogramy wyjścia (14:00 i 14:10 ET). Klucz próby jest per świeca, więc drugi nie zdubluje
  pierwszego.
- [Błąd w przepisie to prawdziwe pieniądze] → tabela przypadków `decide`, tydzień na demo równolegle z teamem 8 na
  innym koncie demo, a dopiero potem decyzja operatora o koncie realnym. Do tego `review.md`.
- [Zegar co 15 s] → wejście 0–15 s po świecy. Świadomie poza zakresem: dziś zysk to 98 s → około 10 s. Precyzja zegara
  to następna zmiana.
- [Powierzchnia `tc-team-tools` rośnie] → świadoma korekta sufitu w teście powierzchni z liczbą zmierzoną w CI.
- [Rewizja z krokami na starszym kodzie po wycofaniu] → Pydantic zignoruje `steps` i zostanie sam reporter. Mitygacja:
  wycofanie zaczyna się od wstrzymania harmonogramów zespołów z krokami.

## Migration Plan

1. Merge. Migracja łańcucha `teams` dokłada kolumnę i indeks przy starcie, pod blokadą. Żaden zespół się nie zmienia.
2. Operator zakłada z Telegrama albo z terminala zespół demo: krok `strategy_execute` (strategia 5, rewizja 1) i
   reporter z powiadomieniem zapasowym, na koncie demo innym niż konto teamu 8. Harmonogramy 9:35, 14:00 i 14:10 ET.
3. Tydzień porównania z teamem 8: czas od świecy do zlecenia, poślizg względem `vs_backtest`, rozjazd pozycji.
4. Konto realne dla takiego zespołu ustawia operator w terminalu, kiedy uzna próbę za udaną.

Wycofanie: wstrzymać harmonogramy zespołów z krokami, potem cofnąć kod. Kolumna `attempt_key` może zostać, bo nic
poza krokami jej nie czyta.
