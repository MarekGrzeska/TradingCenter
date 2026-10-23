## Why

Obserwowany kanał oddaje do transkrypcji i odczytu **każdy** nowy film. Kanał, z którego operatora interesuje tylko część
materiału (np. analizy makro, a nie Q&A, reklamy czy vlogi), kosztuje dziś pełną cenę Gemini za każdy film — albo nie
jest obserwowany wcale. Operator chce móc powiedzieć własnymi słowami, które filmy danego kanału przetwarzać.

## What Changes

- Kanał dostaje opcjonalny **filtr**: tekst operatora (albo agenta) opisujący, jakie filmy przetwarzać. Kanał bez filtra
  działa jak dziś — przetwarza wszystko; to zostaje domyślne, a kanały już na liście się nie zmieniają.
- Nowy film kanału z filtrem jest oceniany przez model **po samych metadanych** (tytuł, opis, długość, język), zanim
  zostanie wysłany do transkrypcji. Jedno wywołanie na kanał i przebieg, tylko dla filmów jeszcze nieznanych; tokeny
  liczą się do dziennego limitu analizy. Metadane przychodzą już dziś z tego samego wywołania źródła — filtr nie kosztuje
  jednostek YouTube.
- Film przepuszczony idzie znaną drogą. Film odrzucony jest zapisywany w nowym stanie **`filtered_out`** z jednym zdaniem
  modelu, dlaczego — nie jest transkrybowany, czytany ani ogłaszany, i nie jest oceniany drugi raz.
- **Gdy oceny nie da się zrobić** (brak modelu, wyczerpane tokeny, odpowiedź poza schematem), film **czeka** na kolejny
  przebieg — nie jest przepuszczany bez oceny, bo to wydałoby właśnie to, przed czym filtr chroni.
- Zmiana filtra dotyczy filmów wykrytych po niej, tak jak zmiana promptu.
- Terminal: pole filtra przy dodawaniu i edycji kanału; w zakładce Filmy odrzucone filmy są **domyślnie ukryte**, widoczne
  po wybraniu stanu, z powodem i przyciskiem „Analizuj mimo to” (ścieżka filmu wskazanego ręcznie).
- Agent **może** ustawić filtr przy obserwowaniu kanału (`follow_channel`).

Poza zakresem: ponowna ocena odrzuconych filmów po zmianie filtra; filtr słów kluczowych bez modelu; filtr na tematach
(tematy mają już przesiew kandydatów).

`review.md` powstaje przy zamknięciu zmiany. Zdolności `youtube-data-*` zmieniane przez niezarchiwizowane zmiany `youtube-*`
nie są jeszcze w `openspec/specs/`, więc — jak w `youtube-loop-settings` — delta to jedna nowa zdolność.

## Capabilities

### New Capabilities

- `youtube-data-channel-filter`: filtr kanału oceniający nowe filmy po metadanych przed transkrypcją, stan `filtered_out`
  i jego obsługa w REST, narzędziu agenta i terminalu.

### Modified Capabilities

Brak w `openspec/specs/`.

## Impact

- `modules/workbench`: migracja `0006` w łańcuchu `youtube` (kolumna `channels.filter`, stan `filtered_out` w CHECK filmu,
  powód odrzucenia), `youtube_data/screening.py`, `ingest.py`, `store.py`, `watchlist.py`, `models.py`, `contract.py`,
  `routers/watch.py`, `routers/videos.py`, `tools/watch.py`, README.
- `modules/terminal`: `contract.youtube.generated.ts` (skill `contract-sync`), `youtube/WatchPanels.tsx`, lista filmów i
  `present.ts`.
- Produkcja: migracja wykonuje się sama przy starcie; bez nowych sekretów i infrastruktury. Koszt: kilkaset tokenów
  tańszego modelu na nowy film kanału z filtrem.
