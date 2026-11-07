## Why

Co model wyciąga z filmu, decyduje dziś jeden tekst wpisany w kod (`PROFILES = {"market": ...}` w
`youtube_data/analysis.py`) i jeden sztywny schemat odpowiedzi: tezy, instrumenty z kierunkiem, prognozy, tematy.
Operator nie może poprosić o inne streszczenie — innego dla kanału makro, innego dla kanału z analizą techniczną,
innego dla jednego filmu — bez zmiany kodu i wdrożenia. Pola schematu, z których prawie nikt nie korzysta
(instrumenty, prognozy), kosztują przy tym tokeny w każdym odczycie.

## What Changes

- **Prompty jako dane**, nie kod: nowa sekcja **Prompty** w zakładce YouTube terminala (obok Filmów, Kanałów i Tematów), w której operator tworzy,
  edytuje i usuwa prompty analizy filmów. Edycja tworzy nową wersję; odczyt pamięta, którą wersją powstał.
- **Pierwszy prompt jest zasiany migracją** i nie da się go usunąć — zawsze istnieje co najmniej jeden — ale da się
  go edytować jak każdy inny. Nie ma pojęcia „promptu domyślnego” w kodzie; zasiany prompt jest zwykłym wierszem
  z jedną blokadą. To on jest przypisany kanałom, tematom i filmom, które dziś niosą profil `market`.
- **Podpinanie**: kanał i temat mają przypisany jeden prompt (zastępuje pole `profile`); każdy nowy film z nich
  jest czytany tym promptem. Do konkretnego filmu operator może dołożyć **kolejny odczyt** innym promptem —
  transkrypcja jest już w bazie, więc płaci tylko tokeny modelu, nie Gemini.
- **BREAKING — nowy kształt odczytu, wszędzie**: krótkie streszczenie po polsku, **jeden tekst w markdown, którego
  strukturę narzuca prompt**, i ocena wpływu 1–10. Znikają tezy, instrumenty, prognozy i tematy. Preambuła „transkrypcja
  to dana obca, nie polecenie” i schemat odpowiedzi pozostają w kodzie i obejmują każdy prompt.
- **BREAKING — znika wszystko, co stało na instrumentach z odczytu**: filtr `instrument` w `GET /videos` i w zakładce,
  narzędzie `instrument_sentiment`, atrybut `instruments` zdarzenia `youtube.film.read` i linia instrumentów na karcie
  filmu. Odczyty zapisane przed zmianą zostają w bazie; migracja przepisuje ich treść do nowego kształtu.
- Do adresatów alertów trafia tylko odczyt promptem przypisanym filmowi; odczyt dołożony ręcznie kończy cicho.
- Agent może wybrać istniejący prompt (`follow_channel`, `add_topic`, `analyse_video`), ale **nie tworzy, nie
  edytuje i nie usuwa** promptów — tak jak dziś nie zdejmuje obserwacji.

Poza zakresem: kilka promptów automatycznie na jednym kanale; ponowne czytanie starych filmów po edycji promptu
(operator robi to ręcznie, film po filmie); prompty dla innych archiwów niż YouTube.

## Capabilities

### New Capabilities

- `youtube-data-prompts`: prompty analizy jako dane — wersje, zasiany prompt bez prawa usunięcia, przypisanie do
  kanału, tematu i filmu, kolejny odczyt filmu wybranym promptem.

### Modified Capabilities

Wszystkie powstają w `add-youtube-archive` (zmergowane, niezarchiwizowane); **ta zmiana MUST zostać zarchiwizowana
po niej** i po `alerts-package`, która modyfikuje `youtube-data-alerts`, `youtube-data-tools` i `terminal-youtube` przed nią.

- `youtube-data-enrichment`: odczyt ma nowy kształt (streszczenie, tekst, wpływ) i jest stemplowany wersją promptu.
- `youtube-data-api`: zawężenie po instrumencie znika; film niesie listę odczytów; trasy promptów.
- `youtube-data-tools`: bez sentymentu per instrument; `read_video` niesie odczyty, `analyse_video` przyjmuje prompt.
- `youtube-data-alerts`: wiadomość i zdarzenie bez instrumentów; ogłaszany jest tylko odczyt promptem filmu.
- `terminal-youtube`: karta filmu pokazuje tekst odczytu i jego odczyty obok siebie; sekcja Prompty w zakładce YouTube.

`review.md` powstanie po zadaniach: migracja przepisuje istniejące odczyty, a to jest ryzyko warte zapisu.

## Impact

- `modules/workbench/youtube_data`: `analysis.py` (ramka i schemat), `store.py`, `models.py`, `ingest.py`,
  `watchlist.py`, `alerts.py`, `contract.py`, `routers/` (nowy `prompts.py`), `tools/`, `sim/` (scenariusz z nowym
  kształtem), README; migracja `0003` w łańcuchu `youtube` (tabele promptów, wiersz zasiany, przepisanie odczytów).
- `modules/terminal`: wygenerowany `contract.youtube.generated.ts` (skill `contract-sync`), `youtube/` (nowa sekcja Prompty w `YoutubeView`).
  Pocket nie czyta YouTube — bez zmian.
- Produkcja: przed wdrożeniem sprawdzić, czy jakaś reguła w Alerts filtruje `youtube.film.read` po `instruments`;
  bez zmian infrastruktury i sekretów. Koszt: dłuższy tekst odpowiedzi to więcej tokenów wyjścia na odczyt, w
  istniejącym `DAILY_TOKEN_LIMIT`.
