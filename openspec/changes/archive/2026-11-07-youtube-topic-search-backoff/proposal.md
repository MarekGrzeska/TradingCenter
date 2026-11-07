## Why

Na produkcji osiem tematów od 22.10 nie zakończyło ani jednego wyszukiwania, a dzienny limit źródła (8000 jednostek) znikał
co dobę w kilka godzin. Wyszukiwanie kosztuje 101 jednostek także wtedy, gdy YouTube je odrzuci (to zamierzone — odrzucone
zapytanie też zjada przydział), a porażka nie przesuwa terminu następnej próby, więc temat, którego wyszukiwanie zawsze
zawodzi, płacił 101 jednostek w każdym przebiegu pętli, co 30 minut. Po wyczerpaniu dnia stawało też odkrywanie filmów
z obserwowanych kanałów. Przyczyny samej porażki jeszcze nie znamy — historia przebiegów zaczęła działać, gdy dzień był już
pusty — ale niezależnie od niej temat, który zawodzi, nie może kosztować więcej niż temat, który działa.

Przy okazji: specyfikacja `youtube-data-topic-runs` nie opisuje dziś tego, co robi kod. Poprawka z przeglądu
`youtube-topic-run-history` (porażka lub pominięcie powtarzające poprzedni wpis tematu zapisuje się raz na dobę) weszła do kodu
i testów, ale nie do specyfikacji ani README — edycja przerwała się w połowie, a jej `review.md` twierdzi inaczej.

## What Changes

- Wyszukiwanie, które źródło **odrzuciło lub na które odpowiedziało czymś bezużytecznym** (zapłacone), odracza temat: następna
  próba nie wcześniej niż po własnym odstępie tematu, licząc od porażki. Wyczerpany limit źródła odracza tak samo.
- Wyszukiwanie, na które źródło **nie odpowiedziało wcale** (błąd sieci — niezapłacone), jest ponawiane w następnym przebiegu,
  jak dotąd.
- Odroczenie nie przesuwa okna wyszukiwania: kolejne udane wyszukiwanie szuka filmów od ostatniego udanego, nie od porażki.
  Udane wyszukiwanie zdejmuje odroczenie.
- `GET /topics` mówi, do kiedy temat jest odroczony; terminal pokazuje to w zakładce Tematy.
- Specyfikacja i README opisują zapisywanie powtórzonej porażki lub pominięcia raz na dobę, tak jak robi to kod.

Poza zakresem: przyczyna porażki wyszukiwania (wyjdzie w historii po wdrożeniu i wznowieniu tematów); błąd Gemini 403;
odroczenie wykładnicze.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `youtube-data-topic-runs`: porażka wyszukiwania odracza temat; powtórzona porażka lub pominięcie zapisuje się raz na dobę
  (sprostowanie); nowe wymaganie — temat mówi, do kiedy jest odroczony.

## Impact

- `modules/workbench`: migracja `0008` (`topics.retry_at`), `youtube_data/providers/base.py` i `data_api.py` (odrzucenie
  odróżnione od braku odpowiedzi), `ingest.py`, `store.py`, `models.py`, `contract.py`, README.
- `modules/terminal`: `contract.youtube.generated.ts`, `youtube/youtubeApi.ts`, `WatchPanels.tsx`.
- `openspec/changes/archive/2026-10-24-youtube-topic-run-history/review.md`: sprostowanie fałszywego „amended”.
- Produkcja: migracja sama przy starcie. Po wdrożeniu operator wznawia tematy; pierwszy przebieg zapisze w historii przyczynę.
