## 0. Przed kodem

- [x] 0.1 Odczytać reguły alertów na produkcji; jeśli któraś filtruje `youtube.film.read` po `instruments`, zapisać ją do poprawy przez operatora po wdrożeniu

## 1. Baza

- [x] 1.1 Migracja `0003` w łańcuchu `youtube`: `prompts`, `prompt_versions`, zasiany prompt z nową treścią rynkową, `prompt_id` w `channels`/`topics`/`videos` zamiast `profile`
- [x] 1.2 W tej samej migracji: klucz `readings` `(video_id, prompt_id)` + `prompt_version`, przepisanie dawnych odczytów do `{summary_pl, text, impact_score}`, usunięcie `instruments` z indeksem; `downgrade` odtwarza schemat
- [x] 1.3 Test `-m db` migracji na odczycie z każdym dawnym polem: tekst zawiera tezy, instrumenty i prognozy, ocena i streszczenie bez zmian
- [x] 1.4 `models.py` i `store.py`: prompty (lista z przypisaniami, tworzenie, edycja jako nowa wersja, usunięcie z odmową dla zasianego i przypisanego), odczyty po `prompt_id`, bez `instrument_views` i filtra instrumentu

## 2. Odczyt

- [x] 2.1 `analysis.py`: ramka w kodzie + treść wersji promptu, schemat `{summary_pl, text, impact_score}`, przycięcie `text` do `MAX_TEXT_CHARS`; usunąć `PROFILES`
- [x] 2.2 `ingest.py`: krok odczytu czyta treść wersji promptu filmu i zapisuje `prompt_id` + `prompt_version`
- [x] 2.3 Zamówiony odczyt filmu innym promptem: sprawdzenie transkrypcji i limitu dnia, czytanie w tle pod zamkiem pętli, bez zmiany stanu filmu
- [x] 2.4 `sim/`: scenariusz i `SimAnalyser` w nowym kształcie; prompt-intruz każący odpowiedzieć listą — odpowiedź spoza schematu nie jest zapisana
- [x] 2.5 `watchlist.py`: kanał, temat i film wskazany ręcznie przyjmują prompt (domyślnie zasiany); zmiana promptu kanału/tematu dotyczy tylko nowych filmów

## 3. Powierzchnie

- [x] 3.1 `contract.py` i `routers/prompts.py`: `GET|POST /prompts`, `PATCH|DELETE /prompts/{id}`; `PATCH /channels|topics` z `prompt_id`; `POST /videos` z opcjonalnym promptem; `POST /videos/{id}/readings`
- [x] 3.2 `GET /videos` bez `instrument`, ze streszczeniem i oceną odczytu promptem filmu; `GET /videos/{id}` z listą odczytów
- [x] 3.3 Narzędzia: usunąć `instrument_sentiment` i zawężenie `instrument`; `youtube_archive_status` z nazwami promptów; `follow_channel`, `add_topic`, `analyse_video` z `prompt`; `read_video` z odczytami przyciętymi do 8 000 znaków; test listy narzędzi rozszerzony o „żadne nie pisze promptu”
- [x] 3.4 `alerts.py`: zdarzenie bez `instruments`, z nazwą promptu; publikowany tylko odczyt promptem filmu; treść bez linii instrumentów
- [x] 3.5 README pakietu: tabela zapisów, droga filmu, powierzchnie

## 4. Terminal

- [x] 4.1 `contract-sync`: regeneracja `contract.youtube.generated.ts`
- [x] 4.2 Karta filmu: streszczenie i ocena na liście; szczegół z odczytami (prompt filmu pierwszy) w markdown i akcją „odczytaj innym promptem”; bez instrumentów i filtra instrumentu
- [x] 4.3 Dialogi kanału, tematu i filmu: wybór promptu
- [x] 4.4 Zakładka Prompts w grupie Data: lista z wersją i przypisaniami, tworzenie, edycja, usunięcie (brak dla zasianego), odmowy z powodem — trzy testy widoku

## 5. Wydanie

- [x] 5.1 `uv run pytest` (z `-m db`), `ruff check .`, `pyright` w workbenchu; `pnpm test`, `lint`, `typecheck`, `contract:check` w terminalu
- [ ] 5.2 PR, merge, `deploy-watch`; po wdrożeniu poprawić regułę z 0.1, jeśli była
