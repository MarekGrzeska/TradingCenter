## 1. Przetwarzanie od razu

- [x] 1.1 `store`: wybór jednego filmu do transkrypcji i do odczytu po identyfikatorze (stany `discovered`/`no_transcript` bez czekania na `next_attempt_at`, `transcribed` do odczytu)
- [x] 1.2 `ingest`: zamek wspólny dla przebiegu i przetwarzania jednego filmu; `process_now(video_id)` = transkrypcja → odczyt → ogłoszenie tego filmu; `start_now` w tle z zachowaniem referencji do zadania i zatrzymaniem przy `stop()`
- [x] 1.3 `watchlist.analyse_film` zwraca, czy film wymaga przetwarzania; trasa `POST /videos` i narzędzie `analyse_video` uruchamiają je w tle i odpowiadają od razu; opisy mówią „przetwarzany teraz”
- [x] 1.4 Testy: film wskazany ręcznie jest odczytany bez `tick()`, inne filmy kolejki nietknięte; ponowne wskazanie omija termin ponowienia; film odczytany nie woła dostawców; przetwarzanie i przebieg nie biegną razem (sufit wydany raz); błąd w tle nie wywraca odpowiedzi
- [x] 1.5 `youtube_data/README.md`, `docs/youtube-jak-dziala.html`; `ruff` · `pyright` · `pytest` (z `-m db`)
