## Why

Temat dziś sam decyduje, co archiwum przeczyta: każde wyszukiwanie wysyła do Gemini i do modelu do `max_videos_per_run`
najnowszych filmów z frazą, od dowolnego autora, bez oceny, czy są warte uwagi. Płacimy sekundami transkrypcji i
tokenami za szum, a operator nie ma wpływu na to, które źródła wchodzą do archiwum. Wartość tematu leży w
**odkrywaniu** nowych autorów i materiałów, nie w autonomicznej analizie — decyzję o analizie i obserwacji ma
podejmować operator.

## What Changes

- **BREAKING — temat przestaje zasilać analizę.** Pętla nadal wyszukuje każdy temat w jego odstępie, ale wyniki nie
  trafiają do archiwum filmów (`videos`): nie są transkrybowane, czytane ani ogłaszane.
- **Model przesiewa wyniki po metadanych.** Jedno wywołanie na wyszukiwanie: model widzi frazę tematu oraz tytuł, opis,
  kanał i długość każdego wyniku. Odrzuca szum i dla każdego zachowanego pisze jedno zdanie po polsku, dlaczego warto
  obejrzeć. Tokeny liczą się w istniejącym `DAILY_TOKEN_LIMIT`.
- **Nowa lista kandydatów.** Wyniki trafiają tam z werdyktem modelu. Odrzucone przez model są zapisane i widoczne na
  żądanie, ale nie są proponowane. Film już w archiwum, film z obserwowanego kanału i film z kanału ignorowanego
  nie stają się kandydatami.
- **Cztery decyzje operatora o kandydacie:**
  - *Obserwuj kanał*: dopisuje kanał z wyborem promptu.
  - *Analizuj ten film*: istniejąca droga filmu wskazanego ręcznie.
  - *Odrzuć*: ten sam film już nie wraca.
  - *Ignoruj kanał*: filmy tego kanału przestają być kandydatami. Operator może to cofnąć.
- **Nowa sekcja Kandydaci** w zakładce YouTube terminala:
  - sortowanie po dacie znalezienia (domyślnie) albo po dacie publikacji;
  - odnośnik do filmu na YouTube;
  - kanał, temat i uzasadnienie modelu;
  - cztery akcje.
- **BREAKING — temat traci prompt.** Nic już nim nie czyta, więc `prompt_id` znika z tematu w kontrakcie, w terminalu,
  w liście „przypisany do” promptu i z narzędzia `add_topic`. Filmy znalezione przez temat przed zmianą zostają w
  archiwum ze swoimi odczytami i pochodzeniem `topic:N`.
- Agent nadal dopisuje tematy (`add_topic`). Nie podejmuje żadnej z czterech decyzji o kandydacie, bo to są decyzje
  operatora.

Poza zakresem: narzędzie agenta czytające kandydatów; propozycje kanałów (nie filmów); przesiew po transkrypcji;
pocket.

## Capabilities

### New Capabilities

- `youtube-data-candidates`: lista kandydatów z tematów. Obejmuje przesiew modelem, tożsamość kandydata, decyzje
  operatora, ignorowane kanały, porządek listy i koszt przesiewu.

### Modified Capabilities

Wszystkie powstały w niezarchiwizowanych zmianach YouTube. Ta zmiana MUST zostać zarchiwizowana po `add-youtube-archive`,
`alerts-package`, `youtube-prompts`, `youtube-named-film-at-once` i `youtube-unwanted-films-are-not-kept`.

- `youtube-data-watchlist`: temat jest źródłem kandydatów, nie filmów do analizy. Jego granica liczy wyniki do
  przesiewu.
- `youtube-data-prompts`: prompt przypisuje się tylko kanałowi i filmowi.
- `youtube-data-ingest`: film trafia do archiwum z kanału albo ze wskazania, nie z tematu.
- `youtube-data-api`: trasy kandydatów i ignorowanych kanałów. Temat bez promptu.
- `youtube-data-tools`: `add_topic` bez promptu. Narzędzia nie podejmują decyzji o kandydacie.
- `terminal-youtube`: sekcja Kandydaci. Temat bez wyboru promptu. Prompty bez przypisania do tematów.

`review.md` powstanie po implementacji, zgodnie ze schematem.

## Impact

- `modules/workbench/youtube_data`:
  - kod: `ingest.py` (gałąź tematów), nowy `screening.py` (wywołanie modelu i schemat odpowiedzi),
    `providers/data_api.py` (opis z wyniku wyszukiwania), `store.py`, `models.py`, `watchlist.py`;
  - powierzchnie: `contract.py`, `routers/` (nowy `candidates.py`), `tools/watch.py`, `views.py`;
  - symulacja: `sim/` (przesiew symulowany) i README;
  - migracja `0004` w łańcuchu `youtube`: tabele `candidates` i `ignored_channels`, zdjęcie `topics.prompt_id`.
- `modules/terminal`: `contract.youtube.generated.ts` (skill `contract-sync`) oraz `youtube/` (nowy `CandidatesPanel`,
  `TopicsPanel` bez promptu, `PromptsPanel` bez tematów). Pocket nie czyta YouTube, więc nie zmienia się.
- Alerty: reguła z filtrem `topic` przestaje dopasowywać nowe filmy, bo film z tematu nie jest już czytany pętlą. To
  skutek zamierzony; istniejących reguł nie migrujemy.
- Koszt: ubywa transkrypcji i odczytów filmów z tematów. Przybywa jedno tanie wywołanie modelu na wyszukiwanie, na
  samych metadanych. Jednostki YouTube API się nie zmieniają.
- Bez zmian infrastruktury i sekretów: przesiew używa istniejącego `YOUTUBE_OPENAI_API_KEY`.
