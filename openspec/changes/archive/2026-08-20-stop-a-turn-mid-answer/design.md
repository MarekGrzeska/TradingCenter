## Context

Tura żyje dziś w zadaniu `asyncio`, które celowo przeżywa wołającego: `send_message`
tworzy je, wkłada do `app.state.agent.background_tasks` i oddaje `StreamingResponse`
czytający kolejkę (`agent/routers/sessions.py`). Zadanie nie ma nazwy poza tym zbiorem, a
zbiór nie wie, do której rozmowy które zadanie należy — nikt dotąd nie potrzebował tego
wiedzieć. Sam bieg tury to graf o dwóch węzłach (`agent/graph.py`): `model` streamuje
odpowiedź modelu, `tools` rozstrzyga wywołania, krawędź `tools → model` zamyka rundę.
Zapis — jedna wypowiedź, wiersze zużycia, wywołania — dzieje się raz, po grafie, w
`run_turn`.

Motywacja: proposal.md, "Why". Wymagania: `specs/agent-chat` i `specs/terminal-agent-chat`
w tej zmianie.

## Goals / Non-Goals

**Goals:**

- Zatrzymanie jako trzecie zakończenie tury, równoprawne z domknięciem i błędem — jedna
  ścieżka zapisu dla wszystkich trzech.
- Granica zatrzymania zdefiniowana tak, by żadne wysłane wywołanie narzędzia nie zostało
  bez zapisu.
- Odróżnienie w transkrypcie „operator przerwał" od „model padł", trwałe, nie tylko na
  ekranie.

**Non-Goals:**

- Zatrzymywanie przebiegów zespołów (`teams/`). Tam bieg trwa minutami i ma własny model
  zatrzymania; ta zmiana go nie dotyka.
- Wznawianie tury po zatrzymaniu. Zatrzymana jest skończona; następne pytanie zaczyna
  następną turę.
- Zatrzymywanie z drugiego okna terminala tej samej rozmowy w czasie rzeczywistym: żądanie
  zadziała, ale drugie okno dowie się o tym dopiero z transkryptu, nie osobnym zdarzeniem.

## Decisions

### D1. Zatrzymanie jest żądaniem do modułu, nie przerwaniem `fetch`

Terminal umie już porzucić strumień i to nic nie daje: `run_turn` nie zależy od tego, czy
ktoś czyta kolejkę (`turn.py`, docstring), a `agent-chat` wymaga, żeby porzucona tura
dokończyła się i zapisała w całości. Zatrzymanie musi więc powiedzieć modułowi coś, czego
rozłączenie nie mówi.

Trasa: `POST /sessions/{session_id}/stop`, filtr właściciela w zapytaniu jak wszędzie
indziej. `404` dla cudzej i nieistniejącej rozmowy — nieodróżnialnie. `204` gdy nic nie
biegnie: żądanie zatrzymania czegoś, co właśnie się skończyło, jest wyścigiem, nie błędem,
i operator nie ma z takiego błędu co zrobić.

Odrzucone: `DELETE /sessions/{id}/turn`. Kształt ładniejszy, ale tura nie jest zasobem,
który to REST-owe czytanie by obiecywało — nie da się jej odczytać ani wskazać
identyfikatorem.

### D2. Rejestr trwających tur w procesie, świadomie

`app.state.agent.turns: dict[int, TurnHandle]` — rozmowa → uchwyt zatrzymania, wpisywany
przy starcie tury, usuwany w `done_callback` tego samego zadania, które już jest podpięte.

Działa, bo plan App Service ma **jednego workera**, i jest to reguła zapisana w
`infra/app-service.tf`, nie przypadek. Gdy przestanie być prawdziwa, zatrzymanie zaczyna
trafiać w instancję, która tury nie trzyma, i cicho nic nie robi — dlatego kod nazwie to
założenie w komentarzu przy rejestrze, a nie tylko tutaj.

Odrzucone: sygnał przez bazę (kolumna `stop_requested` albo `LISTEN/NOTIFY`). Odporne na
drugiego workera, ale kupuje odporność, której dziś nie ma czego chronić, i wprowadza
odpytywanie w pętli tury po to, żeby usłyszeć klik. Wraca na stół razem z drugim workerem
— jednym ruchem, bo granica zatrzymania (D3) jest już wtedy na miejscu.

### D3. Granica zatrzymania: między fragmentem a fragmentem, i między rundą a rundą — nigdy w środku wysłanego wywołania

`TurnHandle` niesie `asyncio.Event`. Sprawdzany w dwóch miejscach:

1. w pętli `async for chunk in provider.stream(...)` w `call_model` — przerwanie pętli
   zamyka strumień dostawcy i zwraca to, co się nazbierało, z `stopped: True`;
2. na wejściu `call_model` — runda po narzędziach nie startuje nowego wywołania modelu.

`run_tools` **nie sprawdza nic**: wywołanie, które poszło, dochodzi do końca i zapisuje
się tak samo jak zawsze. To jest cała treść wymagania o granicy, i po tej stronie stoją
narzędzia, które piszą.

Odrzucone: `task.cancel()`. Przerywa też to, czego nie wolno przerwać — zapis wypowiedzi,
zapis zużycia, rozstrzygnięcie trwającego wywołania — a ratowanie ich `asyncio.shield`
kończy się tym, że połowa tury jest osłonięta, a granica i tak jest umowna. Flaga i dwa
sprawdzenia mówią dokładnie, gdzie tura może się skończyć.

### D4. `stopped` obok `incomplete`, nie zamiast

`messages` ma dziś `incomplete`, znaczące „ta wypowiedź nie jest całością". Dla tury
zatrzymanej to nadal prawda. Czego brakuje, to **kto ją uciął** — i to jest nowa kolumna
`stopped boolean not null default false`, a nie przepisanie znaczenia starej.

Odrzucone: zamiana obu na jedną kolumnę `ending` (`complete` | `failed` | `stopped`).
Czystsze na czysto, ale przepisuje znaczenie wierszy zapisanych wcześniej i zmienia
kontrakt, który terminal już czyta — za dużo jak na jedno pole, które i tak da się dodać
obok.

Wypowiedź zatrzymana zanim padł pierwszy fragment zapisuje się jako pusta, z
`stopped = true` — tak samo jak dziś zapisuje się pusta wypowiedź tury, która padła przed
pierwszym fragmentem. Wiersz mówi wtedy: pytanie poszło, kosztowało tyle, odpowiedzi nie
było.

### D5. Zdarzenie `stopped` w strumieniu, domykające

Po `Complete` i `Failed` dochodzi `Stopped`; router wysyła `event: stopped` i kończy
generator. Terminal, który zdarzenia nie zna, pomija je — a wtedy strumień po prostu się
kończy, co jest zachowaniem, które `stream.ts` już obsługuje.

### D6. Zapis idzie tą samą ścieżką co zawsze

`run_turn` nie dostaje drugiej gałęzi zapisu: graf zwraca `stopped` obok `failed`, a
`append_agent_message` dostaje oba znaczniki. Wiersze zużycia i wywołania zapisują się
tak, jak się zapisują — nic tu nie jest wyjątkiem, bo wyjątek jest dokładnie tym, co po
miesiącu rozjeżdża się z resztą.

### D7. Terminal: przycisk zamiast wysyłania, stan tury z modułu

Composer w czasie tury jest `disabled` (`AgentChat.tsx`), więc miejsce po przycisku
wysyłania jest wolne — tam staje Stop. `agentChatStore` dostaje `stop()`, które woła
trasę i **nie oznacza niczego samo**: oznaczenie przychodzi zdarzeniem `stopped` ze
strumienia, a po nim, jak po każdej turze, następuje przeładowanie transkryptu z modułu.
Odmowa trasy idzie w toast i nie zmienia stanu tury — panel, który sam sobie napisze
„zatrzymano", podczas gdy odpowiedź płynie dalej, jest gorszy niż brak przycisku
(`terminal-agent-chat` w tej zmianie).

## Risks / Trade-offs

- **Drugi worker odbiera zatrzymaniu skutek, po cichu** → rejestr dostaje komentarz
  nazywający regułę z `infra/app-service.tf`; D2 opisuje wymianę na sygnał w bazie jako
  jeden ruch. Testu na to nie ma i nie da się go napisać w jednym procesie — jest za to
  napisane, gdzie patrzeć.
- **Wyścig: stop w chwili, gdy tura właśnie kończy zapis** → uchwyt jest już usunięty z
  rejestru, trasa odpowiada `204`, transkrypt pokazuje turę zakończoną normalnie. To jest
  zachowanie poprawne, nie kompromis: nie było czego zatrzymywać.
- **Dostawca modelu nie zamyka strumienia od razu po przerwaniu pętli** → połączenie
  zamyka się z kontekstem generatora; koszt to co najwyżej kilka tokenów już wygenerowanych
  po stronie dostawcy, których i tak nie ma jak nie zapłacić.
- **Operator klika Stop dwa razy** → drugie żądanie zastaje rejestr pusty albo `Event`
  już ustawiony; oba przypadki są `204` i żaden nie zapisuje drugiej wypowiedzi.

## Migration Plan

Migracja `agent` dodaje `stopped boolean not null default false` do `messages`. Kolumna z
wartością domyślną nie przepisuje tabeli w PostgreSQL od wersji 11, więc nie ma tu okna
niedostępności; moduł migruje sam w swoim `lifespan`, jak każdy inny (CLAUDE.md,
"Migrations are never the operator's job"), pod własnym kluczem blokady.

Wycofanie: starszy obraz kolumny nie czyta i nie zapisuje, a `default false` sprawia, że
wiersze pisane przez niego są poprawne. Kolumna zostaje — nic nie wymaga jej zdejmowania.

Kolejność wdrożenia bez znaczenia dla poprawności: terminal bez modułu dostanie `404` na
trasie zatrzymania i powie to wprost, moduł bez terminala po prostu nie dostanie żądania.
